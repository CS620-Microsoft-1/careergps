import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { ApiError, apiGet, apiPost, clearPendingApiGets, setAccessTokenGetter, setAuthSessionGetter } from "./client.ts";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
  clearPendingApiGets();
  setAccessTokenGetter(async () => null);
});
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const tick = () => new Promise<void>(resolve => setImmediate(resolve));
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const changed = (error: unknown) => error instanceof ApiError && error.status === 409;

test("an old conversation cannot send its text with another account's token", async () => {
  setAuthSessionGetter(async () => ({ accessToken: "token-b", userId: "b" }));
  let calls = 0;
  globalThis.fetch = (async () => { calls++; return json({}); }) as typeof fetch;
  await assert.rejects(apiPost("/copilot/chat", { expectedUserId: "a", json: { question: "private a" } }), changed);
  assert.equal(calls, 0);
});

test("a response is discarded if the shared login switches while the request is in flight", async () => {
  let owner = "a";
  setAuthSessionGetter(async () => ({ accessToken: `token-${owner}`, userId: owner }));
  const pending = deferred<Response>();
  globalThis.fetch = ((_, options) => {
    assert.equal(new Headers(options?.headers).get("Authorization"), "Bearer token-a");
    return pending.promise;
  }) as typeof fetch;
  const result = apiPost("/copilot/chat", { expectedUserId: "a", json: { question: "private a" } });
  const checked = assert.rejects(result, changed);
  await tick();
  owner = "b";
  pending.resolve(json({ text: "late private data" }));
  await checked;
});

test("an account switch during JSON body delivery cannot return personal data", async () => {
  let owner = "a";
  setAuthSessionGetter(async () => ({ accessToken: `token-${owner}`, userId: owner }));
  const body = deferred<unknown>();
  const response = json({});
  response.json = () => body.promise;
  globalThis.fetch = (async () => response) as typeof fetch;
  const result = apiGet("/copilot/capabilities", { expectedUserId: "a" });
  const checked = assert.rejects(result, changed);
  await tick();
  owner = "b";
  body.resolve({ private: "a" });
  await checked;
});

test("sign-out invalidates a pending response", async () => {
  let active = true;
  setAuthSessionGetter(async () => active ? { accessToken: "token-a", userId: "a" } : { accessToken: null, userId: null });
  const pending = deferred<Response>();
  globalThis.fetch = (() => pending.promise) as typeof fetch;
  const checked = assert.rejects(apiGet("/me", { expectedUserId: "a" }), changed);
  await tick();
  active = false;
  pending.resolve(json({ detail: "Expired" }, 401));
  await checked;
  assert.equal(active, false);
});

test("same-account token refresh preserves a successful pending request", async () => {
  let token = "old-token";
  setAuthSessionGetter(async () => ({ accessToken: token, userId: "a" }));
  const pending = deferred<Response>();
  globalThis.fetch = (() => pending.promise) as typeof fetch;
  const result = apiGet<{ user: string }>("/me", { expectedUserId: "a" });
  await tick();
  token = "refreshed-token";
  pending.resolve(json({ user: "a" }));
  assert.deepEqual(await result, { user: "a" });
});

test("a delayed old-token 401 does not sign out the refreshed same-account session", async () => {
  let token = "old-token";
  setAuthSessionGetter(async () => ({ accessToken: token, userId: "a" }));
  const pending = deferred<Response>();
  globalThis.fetch = (() => pending.promise) as typeof fetch;
  const checked = assert.rejects(apiGet("/me", { expectedUserId: "a" }), changed);
  await tick();
  token = "refreshed-token";
  pending.resolve(json({ detail: "Old token expired" }, 401));
  await checked;
  assert.equal(token, "refreshed-token");
});

test("guarded GETs never share an in-flight result across account owners", async () => {
  let owner = "a";
  setAuthSessionGetter(async () => ({ accessToken: `token-${owner}`, userId: owner }));
  const pending = [deferred<Response>(), deferred<Response>()];
  let calls = 0;
  globalThis.fetch = (() => pending[calls++].promise) as typeof fetch;
  const first = apiGet("/me", { expectedUserId: "a" });
  const rejected = assert.rejects(first, changed);
  await tick();
  owner = "b";
  const second = apiGet("/me", { expectedUserId: "b" });
  await tick();
  assert.equal(calls, 2);
  pending[0].resolve(json({ user: "a" }));
  pending[1].resolve(json({ user: "b" }));
  await rejected;
  assert.deepEqual(await second, { user: "b" });
});

test("a delayed anonymous 401 cannot log out a newly signed-in account", async () => {
  let owner: string | null = null;
  setAuthSessionGetter(async () => ({ accessToken: owner ? "token-b" : null, userId: owner }));
  const pending = deferred<Response>();
  globalThis.fetch = (() => pending.promise) as typeof fetch;
  const checked = assert.rejects(apiGet("/me"), changed);
  await tick();
  owner = "b";
  pending.resolve(json({ detail: "Not authenticated" }, 401));
  await checked;
  assert.equal(owner, "b");
});

test("a current session's expired token returns 401 without clearing the session", async () => {
  const session = { accessToken: "expired-token", userId: "a" };
  setAuthSessionGetter(async () => session);
  globalThis.fetch = (async () => json({ detail: "Expired" }, 401)) as typeof fetch;
  await assert.rejects(apiGet("/me", { expectedUserId: "a" }), (error: unknown) =>
    error instanceof ApiError && error.status === 401 && error.detail === "Expired");
  assert.deepEqual(session, { accessToken: "expired-token", userId: "a" });
});

for (const guarded of [true, false]) test(`a login after the last 401 snapshot remains signed in (${guarded ? "guarded" : "shared API"})`, async () => {
  let owner = "a";
  let snapshots = 0;
  setAuthSessionGetter(async () => {
    const session = { accessToken: `token-${owner}`, userId: owner };
    if (++snapshots === 3) queueMicrotask(() => { owner = "b"; });
    return session;
  });
  globalThis.fetch = (async () => json({ detail: "Expired" }, 401)) as typeof fetch;
  await assert.rejects(apiGet("/me", guarded ? { expectedUserId: "a" } : undefined), (error: unknown) =>
    error instanceof ApiError && error.status === 401);
  assert.equal(snapshots, 3);
  assert.equal(owner, "b");
});

test("old-account GET cleanup cannot remove a new account's shared request", async () => {
  let owner = "a";
  setAuthSessionGetter(async () => ({ accessToken: `token-${owner}`, userId: owner }));
  const pending = [deferred<Response>(), deferred<Response>()];
  let calls = 0;
  globalThis.fetch = (() => pending[calls++].promise) as typeof fetch;
  const old = apiGet("/me");
  const rejected = assert.rejects(old, changed);
  await tick();
  owner = "b";
  clearPendingApiGets();
  const current = apiGet("/me");
  await tick();
  pending[0].resolve(json({ user: "a" }));
  await rejected;
  const shared = apiGet("/me");
  await tick();
  assert.equal(calls, 2);
  pending[1].resolve(json({ user: "b" }));
  assert.deepEqual(await current, { user: "b" });
  assert.deepEqual(await shared, { user: "b" });
});
