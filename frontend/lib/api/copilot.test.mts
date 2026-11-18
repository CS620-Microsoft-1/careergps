import assert from "node:assert/strict";
import { afterEach, beforeEach, it } from "node:test";
import { boundedCopilotRequest, createCopilotResponder, getCopilotCapabilities } from "./copilot.ts";
import { ApiError, setAuthSessionGetter } from "./client.ts";
import { selectedCopilotReportId } from "../copilot-types.ts";
import { CopilotSession, createCopilotStorage, copilotStorageKey } from "../copilot-session.ts";

const realFetch = globalThis.fetch;
const userId = "alice";
const respondToCopilot = createCopilotResponder(userId);
beforeEach(() => { setAuthSessionGetter(async () => ({ accessToken: "test-token", userId })); });
afterEach(() => { globalThis.fetch = realFetch; setAuthSessionGetter(async () => ({ accessToken: null, userId: null })); });
const jobFamily = "software_engineer" as const;
const reply = { text: "  Hello. How can I help?\n", sources: [], mode: "foundry_chat", jobFamily };

it("sends authenticated conversation turns with only question, history and selected direction", async () => {
  setAuthSessionGetter(async () => ({ accessToken: "test-token", userId }));
  globalThis.fetch = (async (url, options) => {
    assert.ok(String(url).endsWith("/copilot/chat"));
    assert.equal(new Headers(options?.headers).get("Authorization"), "Bearer test-token");
    assert.equal(options?.method, "POST");
    assert.deepEqual(JSON.parse(String(options?.body)), { question: "Hello", history: [], jobFamily });
    return Response.json(reply);
  }) as typeof fetch;
  const request = { question: "Hello", history: [], jobFamily,
    analysisId: "a".repeat(32), accountId: "untrusted-account", resumeId: "untrusted-resume" };
  const result = await respondToCopilot(request, new AbortController().signal);
  assert.equal(result.text, reply.text);
  assert.equal(result.mode, "foundry_chat");
  assert.equal("resume" in result, false);
  assert.equal("intent" in result, false);
});

it("keeps recent context within the backend budget without mutating saved history", () => {
  const history = Array.from({ length: 30 }, (_, index) => ({
    role: index % 2 ? "assistant" as const : "user" as const, text: String(index).padEnd(4000, "x"),
  }));
  const request = boundedCopilotRequest({ question: "Next?", history, jobFamily });
  assert.equal(request.history.length, 4);
  assert.equal(request.history[0].role, "user");
  assert.equal(request.history.at(-1)?.role, "assistant");
  assert.equal(request.history.at(-1)?.text, history.at(-1)?.text);
  assert.equal(request.jobFamily, jobFamily);
  assert.equal(history.length, 30);
});

it("forwards the visible report selector while discarding caller-provided identity fields", async () => {
  const reportId = "a".repeat(32);
  globalThis.fetch = (async (_url, options) => {
    assert.deepEqual(JSON.parse(String(options?.body)), { question: "Summarize my report", history: [], jobFamily, reportId });
    return Response.json(reply);
  }) as typeof fetch;
  const request = { question: "Summarize my report", history: [], jobFamily, reportId,
    userId: "untrusted-user", resumeId: "untrusted-resume" };
  await respondToCopilot(request, new AbortController().signal);
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json(reply); };
  for (const invalid of ["", "../other-report", "b".repeat(33)]) {
    await assert.rejects(respondToCopilot({ ...request, reportId: invalid }, new AbortController().signal));
  }
  assert.equal(calls, 0);
});

it("only selects a visible report matching the signed-in user, direction and current resume", () => {
  const resume = { user_id: "alice", resume_id: "resume-a", job_family: jobFamily };
  const run = { ...resume, id: "a".repeat(32) };
  assert.equal(selectedCopilotReportId("alice", jobFamily, resume, run), run.id);
  for (const candidate of [{ ...run, user_id: "bob" }, { ...run, resume_id: "resume-b" },
    { ...run, job_family: "ai_engineer" as const }, { ...run, id: "invalid" }, null]) {
    assert.equal(selectedCopilotReportId("alice", jobFamily, resume, candidate), undefined);
  }
  assert.equal(selectedCopilotReportId(null, jobFamily, resume, run), undefined);
  assert.equal(selectedCopilotReportId("alice", jobFamily, null, run), undefined);
  assert.equal(selectedCopilotReportId("alice", jobFamily, { ...resume, user_id: "bob" }, run), undefined);
});

it("preserves the backend request-error explanation", async () => {
  let called = false;
  globalThis.fetch = async () => { called = true; return Response.json({ detail: "The conversation request could not be completed." }, { status: 404 }); };
  await assert.rejects(respondToCopilot({ question: "Hello", history: [], jobFamily }, new AbortController().signal),
    (error: unknown) => error instanceof ApiError && error.status === 404 && error.detail === "The conversation request could not be completed.");
  assert.equal(called, true);
});

it("propagates backend errors rather than substituting scripted replies", async () => {
  globalThis.fetch = async () => Response.json({ detail: "Not configured" }, { status: 503 });
  await assert.rejects(respondToCopilot({ question: "Hello", history: [], jobFamily }, new AbortController().signal),
    (error: unknown) => error instanceof ApiError && error.status === 503);
});

it("rejects malformed replies and legacy résumé/report response contracts", async () => {
  for (const invalid of [
    { ...reply, mode: "foundry_resume" }, { ...reply, mode: "foundry_report" },
    { ...reply, intent: "read_resume" }, { ...reply, resume: {} },
    { ...reply, sources: [{ id: "", label: "Evidence", excerpt: "Missing source identity" }] },
    { ...reply, sources: [{ id: "resume:source", label: "Evidence", excerpt: "Text", userId: "untrusted" }] },
    { ...reply, text: "" }, { ...reply, jobFamily: "unsupported" },
  ]) {
    globalThis.fetch = async () => Response.json(invalid);
    await assert.rejects(respondToCopilot({ question: "Hello", history: [], jobFamily }, new AbortController().signal));
  }
});

it("retains the backend's evidence for a read-only conversation answer", async () => {
  const source = { id: "resume:confirmed:technical_skills", label: "Saved résumé · Technical skills", excerpt: "Python, SQL" };
  globalThis.fetch = async () => Response.json({ ...reply, text: "Your saved résumé lists Python and SQL.", sources: [source] });
  const result = await respondToCopilot({ question: "What skills are on my résumé?", history: [], jobFamily }, new AbortController().signal);
  assert.deepEqual(result.sources, [source]);
  assert.equal(result.mode, "foundry_chat");
});

it("rejects evidence outside the bounded response contract", async () => {
  const source = { id: "resume:source", label: "Saved résumé", excerpt: "Python" };
  for (const sources of [
    Array.from({ length: 9 }, () => source),
    [{ ...source, id: "x".repeat(201) }],
    [{ ...source, label: "x".repeat(201) }],
    [{ ...source, excerpt: "x".repeat(4001) }],
    [{ ...source, excerpt: "" }],
  ]) {
    globalThis.fetch = async () => Response.json({ ...reply, sources });
    await assert.rejects(respondToCopilot({ question: "What skills are on my résumé?", history: [], jobFamily }, new AbortController().signal));
  }
});

it("loads advertised capabilities with the existing authenticated API client", async () => {
  setAuthSessionGetter(async () => ({ accessToken: "test-token", userId }));
  let calls = 0;
  globalThis.fetch = (async (url, options) => {
    assert.ok(String(url).endsWith("/copilot/capabilities"));
    assert.equal(options?.method, "GET");
    assert.equal(options?.body, undefined);
    assert.equal(new Headers(options?.headers).get("Authorization"), "Bearer test-token");
    return Response.json({ dataReadsEnabled: calls++ === 1 });
  }) as typeof fetch;
  assert.deepEqual(await getCopilotCapabilities(userId), { dataReadsEnabled: false });
  assert.deepEqual(await getCopilotCapabilities(userId), { dataReadsEnabled: true });
});

it("rejects failed or malformed capability lookups rather than claiming reads are enabled", async () => {
  for (const body of [{}, { dataReadsEnabled: "true" }, { dataReadsEnabled: true, version: "internal" }]) {
    globalThis.fetch = async () => Response.json(body);
    await assert.rejects(getCopilotCapabilities(userId));
  }
  globalThis.fetch = async () => Response.json({ detail: "Unavailable" }, { status: 503 });
  await assert.rejects(getCopilotCapabilities(userId), (error: unknown) => error instanceof ApiError && error.status === 503);
});

it("passes cancellation through to the authenticated request", async () => {
  const controller = new AbortController();
  globalThis.fetch = (async (_url, options) => {
    controller.abort();
    options?.signal?.throwIfAborted();
    throw new Error("Expected an aborted request");
  }) as typeof fetch;
  await assert.rejects(respondToCopilot({ question: "Hi", history: [], jobFamily }, controller.signal), { name: "AbortError" });
});

it("rejects a missing direction without making a request", async () => {
  let called = false;
  globalThis.fetch = async () => { called = true; return Response.json(reply); };
  await assert.rejects(respondToCopilot({ question: "Hello", history: [] }, new AbortController().signal),
    (error: unknown) => error instanceof ApiError && error.status === 409);
  assert.equal(called, false);
});

it("rejects a conversation reply for a different direction", async () => {
  globalThis.fetch = async () => Response.json({ ...reply, jobFamily: "ai_engineer" });
  await assert.rejects(respondToCopilot({ question: "Hello", history: [], jobFamily }, new AbortController().signal),
    /different career direction/);
});

it("does not send an old-owner conversation with another account's current token", async () => {
  setAuthSessionGetter(async () => ({ accessToken: "bob-token", userId: "bob" }));
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json(reply); };
  await assert.rejects(respondToCopilot({ question: "Read my résumé", history: [], jobFamily }, new AbortController().signal),
    (error: unknown) => error instanceof ApiError && error.status === 409);
  await assert.rejects(getCopilotCapabilities(userId), (error: unknown) => error instanceof ApiError && error.status === 409);
  assert.equal(calls, 0);
});

it("discards a valid personal-data response if the account changes while it is in flight", async () => {
  globalThis.fetch = async () => {
    setAuthSessionGetter(async () => ({ accessToken: "bob-token", userId: "bob" }));
    return Response.json({ ...reply, text: "Private saved data from the previous request." });
  };
  await assert.rejects(respondToCopilot({ question: "Read my résumé", history: [], jobFamily }, new AbortController().signal),
    (error: unknown) => error instanceof ApiError && error.status === 409);
});

it("a token refresh for the same owner keeps its conversation usable", async () => {
  globalThis.fetch = async () => {
    setAuthSessionGetter(async () => ({ accessToken: "refreshed-alice-token", userId }));
    return Response.json(reply);
  };
  assert.equal((await respondToCopilot({ question: "Hello", history: [], jobFamily }, new AbortController().signal)).text, reply.text);
});

it("a stale tab cannot save another account's reply into its old owner's history", async () => {
  const values = new Map<string, string>();
  const storage = { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); } };
  const session = new CopilotSession({ ...createCopilotStorage("user:alice", () => storage), respond: respondToCopilot });
  session.initialize(); session.setResumeContext({ jobFamily });
  setAuthSessionGetter(async () => ({ accessToken: "bob-token", userId: "bob" }));
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ ...reply, text: "BOB_PRIVATE_REPLY" }); };
  await session.send("What skills are on my saved résumé?");
  assert.equal(calls, 0);
  assert.equal(session.getSnapshot().messages.length, 1);
  assert.equal(session.getSnapshot().messages[0].replyState, "failed");
  assert.ok(!values.get(copilotStorageKey("user:alice"))?.includes("BOB_PRIVATE_REPLY"));
  assert.equal(values.has(copilotStorageKey("user:bob")), false);
});
