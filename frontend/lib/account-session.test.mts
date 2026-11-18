import assert from "node:assert/strict";
import { test } from "node:test";
import { AccountSession, type AccountState, type AuthUser } from "./account-session.ts";
import { ApiError } from "./api/client.ts";

type Profile = { id: string; name: string };
type Changes = { name: string };
const tick = () => new Promise<void>(resolve => setImmediate(resolve));
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function harness() {
  const initial = deferred<AuthUser | null>();
  const profiles = new Map<string, ReturnType<typeof deferred<Profile | null>>>();
  const updates: { owner: string; changes: Changes; pending: ReturnType<typeof deferred<Profile>> }[] = [];
  const published: AccountState<Profile>[] = [];
  const timeline: string[] = [];
  const scheduled: (() => void)[] = [];
  let changed: (user: AuthUser | null) => void = () => {};
  let unsubscribed = false;
  const session = new AccountSession<Profile, Changes>({
    currentUser: () => initial.promise,
    subscribe: listener => { changed = listener; return () => { unsubscribed = true; }; },
    loadProfile: async owner => {
      const pending = deferred<Profile | null>();
      profiles.set(owner, pending);
      return pending.promise;
    },
    updateProfile: (changes, owner) => {
      const pending = deferred<Profile>();
      updates.push({ owner, changes, pending });
      return pending.promise;
    },
    publish: state => { timeline.push("publish:" + state.authUserId); published.push(state); },
    ownerChanged: () => { timeline.push("invalidate"); },
    defer: work => { scheduled.push(work); },
  });
  return { session, initial, profiles, updates, published, scheduled, timeline,
    change: (user: AuthUser | null) => changed(user),
    state: () => published.at(-1)!, run: () => { while (scheduled.length) scheduled.shift()!(); },
    unsubscribed: () => unsubscribed };
}

test("auth changes invalidate old identity before profile work and discard stale initial lookup", async () => {
  const h = harness();
  h.session.start();
  h.change({ id: "b", email: "b@example.invalid" });
  assert.deepEqual(h.state(), { status: "loading", authUserId: "b", email: "b@example.invalid", user: null });
  assert.equal(h.profiles.size, 0); // No API/auth re-entry inside the event callback.
  h.initial.resolve({ id: "a", email: "a@example.invalid" });
  await tick();
  assert.equal(h.state().authUserId, "b");
  h.run();
  h.profiles.get("b")!.resolve({ id: "b", name: "B" });
  await tick();
  assert.equal(h.state().status, "ready");
  assert.equal(h.state().user?.id, "b");
  h.session.stop();
});

test("a profile response from the previous account cannot populate the new account", async () => {
  const h = harness(); h.session.start();
  h.change({ id: "a" }); h.run();
  h.change({ id: "b" }); h.run();
  h.profiles.get("a")!.resolve({ id: "a", name: "A private profile" });
  await tick();
  assert.equal(h.state().authUserId, "b");
  assert.equal(h.state().user, null);
  h.profiles.get("b")!.resolve({ id: "b", name: "B" });
  await tick();
  assert.equal(h.state().user?.name, "B");
  h.session.stop();
});

test("same-user token refresh does not clear the ready profile or republish an identity change", async () => {
  const h = harness(); h.session.start();
  h.change({ id: "a", email: "a@example.invalid" }); h.run();
  h.profiles.get("a")!.resolve({ id: "a", name: "A" });
  await tick();
  const before = h.state(); const count = h.published.length;
  h.change({ id: "a", email: "a@example.invalid" });
  assert.equal(h.state(), before);
  assert.equal(h.published.length, count);
  assert.equal(h.scheduled.length, 0);
  h.session.stop();
});

test("sign-out clears only active identity state and rejects late work", async () => {
  const h = harness(); h.session.start();
  h.change({ id: "a" }); h.run();
  h.change(null);
  assert.deepEqual(h.state(), { status: "ready", email: null, authUserId: null, user: null });
  h.profiles.get("a")!.resolve({ id: "a", name: "Old A" });
  await tick();
  assert.equal(h.state().user, null);
  h.session.stop();
  const count = h.published.length;
  h.change({ id: "b" });
  assert.equal(h.published.length, count);
  assert.equal(h.unsubscribed(), true);
});

test("a delayed account update cannot replace the newly signed-in account", async () => {
  const h = harness(); h.session.start();
  h.change({ id: "a" }); h.run();
  h.profiles.get("a")!.resolve({ id: "a", name: "A" });
  await tick();
  const update = h.session.update({ name: "Updated A" }, "a");
  const checked = assert.rejects(update, error => error instanceof ApiError && error.status === 409);
  assert.equal(h.updates[0].owner, "a");
  h.change({ id: "b" });
  h.updates[0].pending.resolve({ id: "a", name: "Updated A" });
  await checked;
  assert.equal(h.state().authUserId, "b");
  assert.equal(h.state().user, null);
  h.session.stop();
});

test("a mismatched profile ID is never accepted as the current user's profile", async () => {
  const h = harness(); h.session.start(); h.change({ id: "a" }); h.run();
  h.profiles.get("a")!.resolve({ id: "b", name: "Foreign B" });
  await tick();
  assert.equal(h.state().status, "ready");
  assert.equal(h.state().authUserId, "a");
  assert.equal(h.state().user, null);
  h.session.stop();
});

test("identity changes invalidate shared reads before publishing, same-owner refresh does not", async () => {
  const h = harness(); h.session.start();
  h.change({ id: "a" });
  assert.deepEqual(h.timeline, ["invalidate", "publish:a"]);
  h.change({ id: "a" });
  assert.deepEqual(h.timeline, ["invalidate", "publish:a"]);
  h.change({ id: "b" });
  assert.deepEqual(h.timeline.slice(-2), ["invalidate", "publish:b"]);
  h.session.stop();
});

test("an old account's delayed form callback cannot start an update for the new account", async () => {
  const h = harness(); h.session.start(); h.change({ id: "b" }); h.run();
  h.profiles.get("b")!.resolve({ id: "b", name: "B" });
  await tick();
  await assert.rejects(h.session.update({ name: "Old A form" }, "a"), error => error instanceof ApiError && error.status === 409);
  assert.equal(h.updates.length, 0);
  h.session.stop();
});
