import assert from "node:assert/strict";
import test from "node:test";
import { CopilotSession, copilotStorageKey, createCopilotStorage, SAMPLE_ANALYSIS_ID } from "./copilot-session.ts";
import type { CopilotReply, CopilotRequest, CopilotResponder } from "./copilot-types.ts";
import { ApiError } from "./api/client.ts";

const answer: CopilotReply = { text: "Test response", sources: [], mode: "foundry_chat" };
function initialize(session: CopilotSession) {
  session.initialize();
  session.setResumeContext(firstResume);
}

function deferred() {
  let resolve!: (reply: CopilotReply) => void;
  const promise = new Promise<CopilotReply>(r => { resolve = r; });
  return { promise, resolve };
}
function setup(respond: CopilotResponder = async () => answer, initialSaved: string | null = null) {
  let saved = initialSaved;
  let nextId = 0;
  const deps = { read: () => saved, write: (value: string) => { saved = value; }, clear: () => { saved = null; }, respond,
    id: () => `id-${nextId++}`, now: () => "2026-11-10T12:00:00.000Z" };
  const session = new CopilotSession(deps);
  initialize(session);
  return { session, restore: () => { const s = new CopilotSession(deps); initialize(s); return s; } };
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
  assert.ok(loaded.getSnapshot().messages.every(m => m.mode === "foundry_chat" && !m.analysisId));
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
  assert.deepEqual(session.getSnapshot().messages.map(m => m.text), ["Question", "Test response"]);
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
  initialize(session); await session.send("Question");
  assert.equal(session.getSnapshot().messages.length, 2);
  assert.match(session.getSnapshot().storageWarning!, /could not be saved/);
});

test("corrupt stored history is not overwritten", async () => {
  let writes = 0;
  const session = new CopilotSession({ read: () => '{"version":1}', write: () => { writes++; }, clear: () => {}, respond: async () => answer });
  initialize(session); await session.send("Question");
  assert.equal(writes, 0);
  assert.match(session.getSnapshot().storageWarning!, /could not be loaded/);
});

test("keys separate accounts and legacy storage owners", () => {
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
  initialize(alice); initialize(bob);
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
  initialize(session); await session.send("Keep this question"); session.setDraft("Keep this draft");
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
  initialize(session);
  assert.ok(session.getSnapshot().storageWarning);
  assert.equal(session.clear(), true);
  assert.equal(session.getSnapshot().storageWarning, null);
  await session.send("Fresh question");
  const restored = new CopilotSession({ ...createCopilotStorage("user:alice", () => storage), respond: async () => answer });
  initialize(restored);
  assert.deepEqual(restored.getSnapshot().messages.map(m => m.text), ["Fresh question", answer.text]);
});

const firstResume = { jobFamily: "software_engineer" as const, resumeId: "bca169cb-5f2c-4c4d-9133-c9a2edf408cb", confirmedAt: "2026-11-13T12:00:00.000Z" };
const secondResume = { jobFamily: "ai_engineer" as const, resumeId: "f60ca650-9a77-4013-8705-020d68236ff3", confirmedAt: "2026-11-13T13:00:00.000Z" };
const chatReply: CopilotReply = { text: "Here is a shorter version of your sentence.", sources: [], mode: "foundry_chat" };

const setupChat = (respond: CopilotResponder = async () => chatReply, initialSaved: string | null = null) => setup(respond, initialSaved);

test("read-only chat accepts and restores backend sources while follow-up history remains conversation text", async () => {
  const source = { id: "resume:confirmed:technical_skills", label: "Saved résumé · Technical skills", excerpt: "Python, SQL" };
  const calls: CopilotRequest[] = [];
  const reportId = "a".repeat(32);
  const readReply = { text: "Your saved résumé lists Python and SQL.", sources: [source], mode: "foundry_chat" as const };
  const { session, restore } = setupChat(async request => { calls.push(request); return readReply; });
  session.setResumeContext({ ...firstResume, reportId });
  await session.send("What skills are on my saved résumé?");
  assert.equal(session.getSnapshot().error, null);
  assert.equal(session.getSnapshot().messages[0].replyState, "completed");
  assert.deepEqual(session.getSnapshot().messages[1].sources, [source]);
  assert.deepEqual(restore().getSnapshot().messages[1].sources, [source]);
  assert.equal(restore().getSnapshot().messages[1].resumeContext?.reportId, reportId);
  assert.equal(calls[0].reportId, reportId);
  await session.send("Summarize that");
  assert.deepEqual(calls[1].history, [
    { role: "user", text: "What skills are on my saved résumé?" },
    { role: "assistant", text: readReply.text },
  ]);
  assert.equal(JSON.stringify(calls[1].history).includes(source.id), false);
});

test("authenticated chat still rejects missing mode and malformed or excessive evidence", async () => {
  const source = { id: "report:source", label: "Skill gap report", excerpt: "Saved result" };
  for (const invalid of [
    { text: "Missing chat mode", sources: [] },
    { ...chatReply, sources: [{ ...source, id: "" }] },
    { ...chatReply, sources: [{ ...source, excerpt: "x".repeat(4001) }] },
    { ...chatReply, sources: [{ ...source, invented: true }] },
    { ...chatReply, sources: Array.from({ length: 9 }, () => source) },
  ]) {
    const { session } = setupChat(async () => invalid);
    session.setResumeContext(firstResume);
    await session.send("Read my report");
    assert.equal(session.getSnapshot().messages.length, 1);
    assert.equal(session.getSnapshot().messages[0].replyState, "failed");
    assert.ok(session.getSnapshot().error);
  }
});

test("changing the displayed report cancels stale work and preserves one conversation with the new selector", async () => {
  const d = deferred();
  const calls: CopilotRequest[] = [];
  let oldSignal: AbortSignal | undefined;
  const { session, restore } = setupChat(async (request, signal) => {
    calls.push(request);
    if (calls.length === 2) { oldSignal = signal; return d.promise; }
    return chatReply;
  });
  session.setResumeContext({ ...firstResume, reportId: "a".repeat(32) });
  const conversationId = session.getSnapshot().conversationId;
  await session.send("Hello");
  const pending = session.send("Summarize my report");
  session.setDraft("Keep my draft");
  session.setResumeContext({ ...firstResume, reportId: "b".repeat(32) });
  assert.equal(oldSignal?.aborted, true);
  assert.equal(session.getSnapshot().messages[2].replyState, "cancelled");
  d.resolve({ ...chatReply, text: "Stale report response" });
  await pending;
  assert.equal(session.getSnapshot().messages.length, 3);
  await session.retry();
  assert.equal(calls[2].reportId, "b".repeat(32));
  assert.deepEqual(calls[2].history, [{ role: "user", text: "Hello" }, { role: "assistant", text: chatReply.text }]);
  assert.equal(session.getSnapshot().conversationId, conversationId);
  assert.equal(session.getSnapshot().messages[2].replyState, "completed");
  assert.equal(session.getSnapshot().draft, "Keep my draft");
  assert.equal(restore().getSnapshot().messages[3].resumeContext?.reportId, "b".repeat(32));
});

test("new conversations preserve legacy messages and drafts without sending old sample, report or résumé receipts", async () => {
  const calls: CopilotRequest[] = [];
  const legacyMessages = [
    { id: "legacy-sample", role: "assistant", text: "Old sample reply", createdAt: "2026-11-10T12:00:00.000Z", analysisId: SAMPLE_ANALYSIS_ID },
    { id: "legacy-report", role: "assistant", text: "Old report reply", createdAt: "2026-11-10T12:00:00.000Z", analysisId: "a".repeat(32) },
    { id: "legacy-question", role: "user", text: "Read my résumé", createdAt: "2026-11-10T12:00:00.000Z", resumeContext: firstResume, replyState: "completed" },
    { id: "legacy-resume", role: "assistant", text: "Old fixed résumé receipt: SQL", createdAt: "2026-11-10T12:00:00.000Z", resumeContext: firstResume, sources: [] },
  ];
  const saved = JSON.stringify({ version: 1, open: true, conversationId: "old-conversation", createdAt: "2026-11-10T12:00:00.000Z",
    draft: "Existing draft", messages: legacyMessages });
  const { session, restore } = setupChat(async request => { calls.push(request); return chatReply; }, saved);
  assert.equal(session.getSnapshot().draft, "Existing draft");
  assert.deepEqual(session.getSnapshot().messages, legacyMessages);
  session.setResumeContext(firstResume);
  await session.send("Please shorten this sentence: I built a useful application.");
  assert.deepEqual(calls[0], { question: "Please shorten this sentence: I built a useful application.", history: [], jobFamily: firstResume.jobFamily });
  await session.send("Make it even shorter");
  assert.equal(calls[1].history.length, 2);
  assert.equal(calls[1].history[1].text, chatReply.text);
  assert.ok(!calls[1].history.some(turn => /Old|Read my résumé/.test(turn.text)));
  session.setResumeContext(secondResume);
  await session.send("Hello in this direction");
  assert.deepEqual(calls[2].history, []);
  session.setDraft("Keep this draft");
  const restored = restore();
  assert.equal(restored.getSnapshot().messages.length, 10);
  assert.equal(restored.getSnapshot().draft, "Keep this draft");
  assert.equal(restored.getSnapshot().conversationId, "old-conversation");
  assert.deepEqual(restored.getSnapshot().messages.slice(0, 4), legacyMessages);
  assert.ok(restored.getSnapshot().messages.slice(4).every(message => message.mode === "foundry_chat"));
  restored.setResumeContext(firstResume);
  await restored.send("Continue rewriting");
  assert.equal(calls[3].history.length, 4);
  assert.ok(!calls[3].history.some(turn => /Old|Read my résumé|this direction/.test(turn.text)));
});

test("switching directions or known résumé contexts cancels pending replies and rejects old retries", async () => {
  for (const next of [secondResume, { ...firstResume, resumeId: secondResume.resumeId },
    { ...firstResume, confirmedAt: "2026-11-14T12:00:00.000Z" }]) {
    const d = deferred();
    let calls = 0;
    let signal: AbortSignal | undefined;
    const { session } = setupChat(async (_, requestSignal) => { calls++; signal = requestSignal; return d.promise; });
    session.setResumeContext(firstResume);
    const pending = session.send("Hello");
    session.setDraft("Next draft");
    session.setResumeContext(next);
    assert.equal(signal?.aborted, true);
    assert.equal(session.getSnapshot().messages[0].replyState, "cancelled");
    await session.retry();
    assert.match(session.getSnapshot().error!, /another résumé or direction/);
    d.resolve(chatReply);
    await pending;
    assert.equal(calls, 1);
    assert.equal(session.getSnapshot().messages.length, 1);
    assert.equal(session.getSnapshot().draft, "Next draft");
  }
});

test("real mode without an account or selected direction retains its draft", async () => {
  let calls = 0;
  const { session } = setupChat(async () => { calls++; return chatReply; });
  session.setResumeContext(null, "Sign in to use Copilot.");
  session.setDraft("Hello");
  await session.send();
  assert.equal(calls, 0);
  assert.equal(session.getSnapshot().messages.length, 0);
  assert.equal(session.getSnapshot().draft, "Hello");
  assert.equal(session.getSnapshot().error, "Sign in to use Copilot.");
});

test("a new conversation needs no saved résumé and never labels its reply as a read", async () => {
  const calls: CopilotRequest[] = [];
  const { session, restore } = setupChat(async request => { calls.push(request); return chatReply; });
  session.setResumeContext({ jobFamily: firstResume.jobFamily });
  await session.send("Hello");
  assert.deepEqual(calls[0], { question: "Hello", history: [], jobFamily: firstResume.jobFamily });
  assert.deepEqual(session.getSnapshot().resumeContext, { jobFamily: firstResume.jobFamily });
  const reply = session.getSnapshot().messages[1];
  assert.equal(reply.text, chatReply.text);
  assert.equal(reply.mode, "foundry_chat");
  assert.equal(reply.analysisId, undefined);
  assert.equal(reply.resumeContext?.resumeId, undefined);
  assert.deepEqual(reply.sources, []);
  assert.equal(restore().getSnapshot().messages[1].mode, "foundry_chat");
  await session.send("Please rephrase that");
  assert.equal(calls[1].history.length, 2);
});

test("equivalent context timestamps do not interrupt a new conversation", async () => {
  const calls: CopilotRequest[] = [];
  const { session } = setupChat(async request => { calls.push(request); return chatReply; });
  session.setResumeContext(firstResume);
  await session.send("Hello");
  session.setResumeContext({ ...firstResume, confirmedAt: "2026-11-13T12:00:00+00:00" });
  await session.send("Continue");
  assert.equal(calls[1].history.length, 2);
});

test("failed and cancelled questions stay visible but are excluded from completed conversation history", async () => {
  const calls: CopilotRequest[] = [];
  const d = deferred();
  const { session } = setupChat(async request => {
    calls.push(request);
    if (calls.length === 1) throw new ApiError(429, "Rate limited", "Please wait before sending another message.");
    if (calls.length === 3) return d.promise;
    return chatReply;
  });
  session.setResumeContext(firstResume);
  await session.send("Failed question");
  assert.equal(session.getSnapshot().error, "Please wait before sending another message.");
  assert.equal(session.getSnapshot().messages.length, 1);
  await session.send("Completed question");
  assert.deepEqual(calls[1].history, []);
  const pending = session.send("Cancelled question");
  session.cancel();
  d.resolve(chatReply); await pending;
  await session.send("New question");
  assert.deepEqual(calls[3].history, [{ role: "user", text: "Completed question" }, { role: "assistant", text: chatReply.text }]);
  assert.equal(session.getSnapshot().messages[0].replyState, "failed");
  assert.equal(session.getSnapshot().messages[3].replyState, "cancelled");
});

test("manual retry makes a new conversation request without duplicating the saved question", async () => {
  const calls: CopilotRequest[] = [];
  const { session } = setupChat(async request => {
    calls.push(request);
    if (calls.length === 1) throw new Error("Temporary failure");
    return chatReply;
  });
  session.setResumeContext(firstResume);
  await session.send("Hello");
  await session.retry();
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1], calls[0]);
  assert.equal(session.getSnapshot().messages.length, 2);
  assert.equal(session.getSnapshot().messages[0].replyState, "completed");
});

test("replacing an account conversation discards its late reply and preserves separate drafts", async () => {
  const storage = memoryStorage();
  const d = deferred();
  const alice = new CopilotSession({ ...createCopilotStorage("user:alice", () => storage), respond: async () => d.promise });
  initialize(alice); alice.setResumeContext(firstResume);
  const pending = alice.send("Alice's question");
  alice.setDraft("Alice's draft");
  // Provider cleanup cancels the old instance when its account key changes.
  alice.cancel();
  const bob = new CopilotSession({ ...createCopilotStorage("user:bob", () => storage), respond: async () => chatReply });
  initialize(bob); bob.setResumeContext(firstResume); bob.setDraft("Bob's draft");
  d.resolve(chatReply); await pending;
  assert.equal(alice.getSnapshot().messages.length, 1);
  assert.equal(alice.getSnapshot().messages[0].replyState, "cancelled");
  assert.deepEqual(bob.getSnapshot().messages, []);
  assert.equal(bob.getSnapshot().draft, "Bob's draft");
  const restoredAlice = new CopilotSession({ ...createCopilotStorage("user:alice", () => storage), respond: async () => answer });
  initialize(restoredAlice);
  assert.equal(restoredAlice.getSnapshot().draft, "Alice's draft");
});
