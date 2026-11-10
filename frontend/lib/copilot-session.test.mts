import assert from "node:assert/strict";
import test from "node:test";
import { CopilotSession, copilotStorageKey, SAMPLE_ANALYSIS_ID } from "./copilot-session.ts";
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
  const deps = { read: () => saved, write: (value: string) => { saved = value; }, respond,
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
  const session = new CopilotSession({ read: () => null, write: () => { throw new Error("Quota"); }, respond: async () => answer });
  session.initialize(); await session.send("Question");
  assert.equal(session.getSnapshot().messages.length, 2);
  assert.match(session.getSnapshot().storageWarning!, /could not be saved/);
});

test("corrupt stored history is not overwritten", async () => {
  let writes = 0;
  const session = new CopilotSession({ read: () => '{"version":1}', write: () => { writes++; }, respond: async () => answer });
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
