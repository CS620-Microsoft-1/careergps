import assert from "node:assert/strict";
import test from "node:test";
import { CopilotSession, copilotStorageKey, createCopilotStorage, SAMPLE_ANALYSIS_ID } from "./copilot-session.ts";
import { sampleCopilotReply, respondToMockCopilot, type CopilotReply, type CopilotRequest, type CopilotResponder } from "./copilot-mock.ts";

const answer = { text: "Sample response", sources: [] };
function deferred() {
  let resolve!: (reply: CopilotReply) => void;
  const promise = new Promise<CopilotReply>(r => { resolve = r; });
  return { promise, resolve };
}
function setup(respond: CopilotResponder = async () => answer) {
  let saved: string | null = null;
  let nextId = 0;
  const deps = { read: () => saved, write: (value: string) => { saved = value; }, clear: () => { saved = null; }, respond,
    id: () => `id-${nextId++}`, now: () => "2026-11-10T12:00:00.000Z" };
  const session = new CopilotSession(deps);
  session.initialize();
  return { session, restore: () => { const s = new CopilotSession(deps); s.initialize(); return s; } };
}

test("continuous conversation survives close, refresh, and follow-up with its draft", async () => {
  const { session, restore } = setup();
  const id = session.getSnapshot().conversationId;
  session.setOpen(true);
  await session.send("Why is SQL a gap?");
  session.setDraft("A follow-up draft");
  session.setOpen(false);
  const loaded = restore();
  assert.equal(loaded.getSnapshot().conversationId, id);
  assert.equal(loaded.getSnapshot().messages.length, 2);
  assert.equal(loaded.getSnapshot().draft, "A follow-up draft");
  assert.equal(loaded.getSnapshot().open, false);
  await loaded.send();
  assert.equal(loaded.getSnapshot().messages.length, 4);
  assert.equal(loaded.getSnapshot().conversationId, id);
  assert.ok(loaded.getSnapshot().messages.every(m => m.analysisId === SAMPLE_ANALYSIS_ID));
});

test("duplicate sends are blocked and drafts typed while waiting survive", async () => {
  const d = deferred();
  const { session } = setup(async () => d.promise);
  const pending = session.send("First question");
  await session.send("Duplicate question");
  session.setDraft("Next question");
  session.setOpen(false);
  d.resolve(answer);
  await pending;
  assert.equal(session.getSnapshot().messages.length, 2);
  assert.equal(session.getSnapshot().draft, "Next question");
  assert.equal(session.getSnapshot().open, false);
});

test("cancel ignores late results even if the responder ignores AbortSignal", async () => {
  const d = deferred();
  let attempts = 0;
  const { session } = setup(async () => ++attempts === 1 ? d.promise : answer);
  const pending = session.send("Question");
  session.cancel();
  assert.equal(session.getSnapshot().messages[0].replyState, "cancelled");
  await session.retry();
  d.resolve({ text: "Stale answer", sources: [] });
  await pending;
  assert.deepEqual(session.getSnapshot().messages.map(m => m.text), ["Question", "Sample response"]);
});

test("refresh marks a pending reply interrupted without auto-running it", async () => {
  const d = deferred();
  let calls = 0;
  const { session, restore } = setup(async () => { calls++; return d.promise; });
  const pending = session.send("Question");
  const loaded = restore();
  assert.equal(loaded.getSnapshot().pendingId, null);
  assert.equal(loaded.getSnapshot().messages[0].replyState, "interrupted");
  assert.equal(calls, 1);
  session.cancel(); d.resolve(answer); await pending;
});

test("malformed replies fail safely and retry does not duplicate the question", async () => {
  let calls = 0;
  const { session } = setup(async () => ++calls === 1 ? { text: "", sources: [] } : answer);
  await session.send("Question");
  assert.equal(session.getSnapshot().messages[0].replyState, "failed");
  await session.retry();
  assert.equal(session.getSnapshot().messages.length, 2);
  assert.equal(session.getSnapshot().messages[0].replyState, "completed");
});

test("storage failure keeps live messages usable", async () => {
  const session = new CopilotSession({ read: () => null, write: () => { throw new Error("Quota"); }, clear: () => {}, respond: async () => answer });
  session.initialize(); await session.send("Question");
  assert.equal(session.getSnapshot().messages.length, 2);
  assert.match(session.getSnapshot().storageWarning!, /could not be saved/);
});

test("corrupt stored history is not overwritten", async () => {
  let writes = 0;
  const session = new CopilotSession({ read: () => '{"version":1}', write: () => { writes++; }, clear: () => {}, respond: async () => answer });
  session.initialize(); await session.send("Question");
  assert.equal(writes, 0);
  assert.match(session.getSnapshot().storageWarning!, /could not be loaded/);
});

test("keys separate accounts and the local preview", () => {
  assert.notEqual(copilotStorageKey("user:alice"), copilotStorageKey("user:bob"));
  assert.notEqual(copilotStorageKey("user:local-preview"), copilotStorageKey("local-preview"));
});

test("retains over 100 messages while bounding responder context", async () => {
  let request: CopilotRequest | undefined;
  const { session, restore } = setup(async r => { request = r; return answer; });
  for (let i = 0; i < 55; i++) await session.send(`Question ${i}`);
  assert.equal(restore().getSnapshot().messages.length, 110);
  assert.equal(request!.history.length, 20);
});

test("empty or oversized input does not send", async () => {
  const { session } = setup();
  await session.send("  "); await session.send("a".repeat(2001));
  assert.equal(session.getSnapshot().messages.length, 0);
  assert.ok(session.getSnapshot().error);
});

test("mock carries forward topic and declines unsupported actions", () => {
  const reply = sampleCopilotReply({ question: "Which project should I build first?", history: [{ role: "user", text: "Why is deployment a gap?" }] });
  assert.match(reply.text, /Deploy the task tracker/);
  assert.ok(reply.sources.every(s => s.id.endsWith("deployment")));
  const action = sampleCopilotReply({ question: "Save this plan and rerun analysis", history: [] });
  assert.match(action.text, /haven’t changed/);
  assert.equal(action.sources.length, 0);
  assert.match(sampleCopilotReply({ question: "What is the weather?", history: [] }).text, /scripted examples/);
});

test("mock adapter honors abort", async () => {
  const controller = new AbortController();
  const pending = respondToMockCopilot({ question: "Why SQL?", history: [] }, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
});

test("clear removes messages and draft across refresh and starts with empty responder context", async () => {
  let request: CopilotRequest | undefined;
  const { session, restore } = setup(async r => { request = r; return answer; });
  session.setOpen(true);
  await session.send("Old question");
  session.setDraft("Old draft");
  const previousId = session.getSnapshot().conversationId;
  assert.equal(session.clear(), true);
  assert.notEqual(session.getSnapshot().conversationId, previousId);
  assert.equal(session.getSnapshot().open, true);
  assert.deepEqual(restore().getSnapshot().messages, []);
  assert.equal(restore().getSnapshot().draft, "");
  await session.send("New question");
  assert.deepEqual(request!.history, []);
  assert.deepEqual(restore().getSnapshot().messages.map(m => m.text), ["New question", answer.text]);
});

test("clear aborts a pending reply and discards late results after a new question", async () => {
  const d = deferred();
  let calls = 0;
  let signal: AbortSignal | undefined;
  const { session, restore } = setup(async (_, s) => { signal ??= s; return ++calls === 1 ? d.promise : answer; });
  const pending = session.send("Old pending question");
  session.setDraft("Old draft");
  assert.equal(session.clear(), true);
  assert.equal(signal!.aborted, true);
  assert.equal(session.getSnapshot().pendingId, null);
  await session.send("New question");
  d.resolve({ text: "Stale response", sources: [] });
  await pending;
  assert.deepEqual(restore().getSnapshot().messages.map(m => m.text), ["New question", answer.text]);
});

function memoryStorage() {
  const values = new Map<string, string>();
  return { values, getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); } };
}

test("browser adapter clears only the selected account, preserving other accounts and site data", async () => {
  const storage = memoryStorage();
  storage.setItem("unrelated-setting", "keep");
  const alice = new CopilotSession({ ...createCopilotStorage("user:alice", () => storage), respond: async () => answer });
  const bob = new CopilotSession({ ...createCopilotStorage("user:bob", () => storage), respond: async () => answer });
  alice.initialize(); bob.initialize();
  await alice.send("Alice question"); await bob.send("Bob question");
  alice.setDraft("Alice draft"); bob.setDraft("Bob draft");
  const beforeBob = storage.getItem(copilotStorageKey("user:bob"));
  assert.equal(alice.clear(), true);
  assert.equal(storage.getItem(copilotStorageKey("user:alice")), null);
  assert.equal(storage.getItem(copilotStorageKey("user:bob")), beforeBob);
  assert.equal(storage.getItem("unrelated-setting"), "keep");
});

test("a stale browser tab cannot write deleted history back to storage", () => {
  const storage = memoryStorage();
  const active = createCopilotStorage("user:alice", () => storage);
  const stale = createCopilotStorage("user:alice", () => storage);
  active.read(); active.write("old history"); stale.read();
  active.clear();
  assert.throws(() => stale.write("resurrected history"), /changed in another tab/);
  assert.equal(storage.getItem(copilotStorageKey("user:alice")), null);
  active.write("new history");
  assert.equal(storage.getItem(copilotStorageKey("user:alice")), "new history");
});

test("failed deletion retains the conversation and draft and reports failure", async () => {
  const storage = memoryStorage();
  const session = new CopilotSession({ ...createCopilotStorage("user:alice", () => ({ ...storage,
    removeItem: () => { throw new Error("Storage blocked"); } })), respond: async () => answer });
  session.initialize(); await session.send("Keep this question"); session.setDraft("Keep this draft");
  const before = session.getSnapshot();
  const saved = storage.getItem(copilotStorageKey("user:alice"));
  assert.equal(session.clear(), false);
  assert.deepEqual(session.getSnapshot().messages, before.messages);
  assert.equal(session.getSnapshot().draft, before.draft);
  assert.equal(session.getSnapshot().conversationId, before.conversationId);
  assert.equal(storage.getItem(copilotStorageKey("user:alice")), saved);
  assert.match(session.getSnapshot().error!, /Nothing was cleared/);
});

test("confirmed clear can recover from corrupt saved history", async () => {
  const storage = memoryStorage();
  storage.setItem(copilotStorageKey("user:alice"), "corrupt");
  const deps = { ...createCopilotStorage("user:alice", () => storage), respond: async () => answer };
  const session = new CopilotSession(deps);
  session.initialize();
  assert.ok(session.getSnapshot().storageWarning);
  assert.equal(session.clear(), true);
  assert.equal(session.getSnapshot().storageWarning, null);
  await session.send("Fresh question");
  const restored = new CopilotSession({ ...createCopilotStorage("user:alice", () => storage), respond: async () => answer });
  restored.initialize();
  assert.deepEqual(restored.getSnapshot().messages.map(m => m.text), ["Fresh question", answer.text]);
});
