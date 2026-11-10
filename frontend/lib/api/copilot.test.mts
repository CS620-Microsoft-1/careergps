import assert from "node:assert/strict";
import { afterEach, it } from "node:test";
import { boundedCopilotRequest, respondToCopilot } from "./copilot.ts";
import { ApiError, setAccessTokenGetter } from "./client.ts";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; setAccessTokenGetter(async () => null); });
const reply = { text: "Sample explanation", sources: [], intent: "general", mode: "foundry_mock", analysisId: "sample-swe-v1" };

it("sends authenticated chat input without browser account identifiers", async () => {
  setAccessTokenGetter(async () => "test-token");
  globalThis.fetch = (async (url, options) => {
    assert.ok(String(url).endsWith("/copilot/chat"));
    assert.equal(new Headers(options?.headers).get("Authorization"), "Bearer test-token");
    assert.equal(options?.method, "POST");
    assert.deepEqual(JSON.parse(String(options?.body)), { question: "Why SQL?", history: [] });
    return Response.json(reply);
  }) as typeof fetch;
  assert.equal((await respondToCopilot({ question: "Why SQL?", history: [] }, new AbortController().signal)).text, reply.text);
});

it("keeps recent context within the backend budget without mutating saved history", () => {
  const history = Array.from({ length: 25 }, (_, index) => ({ role: "user" as const, text: String(index).padEnd(4000, "x") }));
  const request = boundedCopilotRequest({ question: "Next?", history });
  assert.equal(request.history.length, 5);
  assert.equal(request.history.at(-1)?.text, history.at(-1)?.text);
  assert.equal(history.length, 25);
});

it("propagates backend errors rather than substituting scripted replies", async () => {
  globalThis.fetch = async () => Response.json({ detail: "Not configured" }, { status: 503 });
  await assert.rejects(respondToCopilot({ question: "Why SQL?", history: [] }, new AbortController().signal),
    (error: unknown) => error instanceof ApiError && error.status === 503);
});

it("rejects invalid response contracts", async () => {
  globalThis.fetch = async () => Response.json({ ...reply, mode: "real_user_data" });
  await assert.rejects(respondToCopilot({ question: "Hi", history: [] }, new AbortController().signal));
});

it("passes cancellation through to the authenticated request", async () => {
  const controller = new AbortController();
  globalThis.fetch = (async (_url, options) => {
    controller.abort();
    options?.signal?.throwIfAborted();
    throw new Error("Expected an aborted request");
  }) as typeof fetch;
  await assert.rejects(respondToCopilot({ question: "Hi", history: [] }, controller.signal), { name: "AbortError" });
});
