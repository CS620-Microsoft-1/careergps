import assert from "node:assert/strict";
import { afterEach, it } from "node:test";

import { ACTION_PLAN_TIMEOUT_MS, getActionPlanSuggestions, streamActionPlanSuggestions } from "./action-plans.ts";
import { ApiError } from "./client.ts";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

function recordFetch(status = 200, body: unknown = { plans: [] }) {
  const calls: { url: string; init: RequestInit }[] = [];
  globalThis.fetch = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify(body), { status });
  }) as typeof fetch;
  return calls;
}

it("posts the role and mode to the suggestions route", async () => {
  const calls = recordFetch();
  assert.deepEqual(await getActionPlanSuggestions("data_analyst"), { plans: [] });
  assert.equal(calls.length, 1);
  assert.ok(calls[0].url.endsWith("/action-plans/suggestions"));
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), { job_family: "data_analyst", mode: "full" });
});

it("waits longer than the backend's Agent timeout", () => {
  assert.ok(ACTION_PLAN_TIMEOUT_MS > 90_000);
});

it("passes the backend's detail on errors", async () => {
  recordFetch(409, { detail: "The skill gap analysis has not finished yet" });
  await assert.rejects(getActionPlanSuggestions("software_engineer"), (error: unknown) =>
    error instanceof ApiError && error.status === 409 && error.detail === "The skill gap analysis has not finished yet");
});

/** A fetch answering with NDJSON, split into chunks that cut lines in half, as a network can. */
function streamFetch(events: unknown[]) {
  const text = events.map((event) => JSON.stringify(event)).join("\n") + "\n";
  const middle = Math.floor(text.length / 2);
  const calls: { url: string; init: RequestInit }[] = [];
  globalThis.fetch = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    const body = new ReadableStream({ start(controller) {
      const encoder = new TextEncoder();
      controller.enqueue(encoder.encode(text.slice(0, middle)));
      controller.enqueue(encoder.encode(text.slice(middle)));
      controller.close();
    } });
    return new Response(body, { status: 200, headers: { "content-type": "application/x-ndjson" } });
  }) as typeof fetch;
  return calls;
}

it("streams each build stage, then resolves with the plan", async () => {
  const calls = streamFetch([
    { type: "stage", stage: "gaps", gaps: [{ skill_id: "sql", skill_name: "SQL" }] },
    { type: "stage", stage: "agent" },
    { type: "result", suggestions: { plans: [] } },
  ]);
  const stages: string[] = [];
  const result = await streamActionPlanSuggestions("data_analyst", (stage) => stages.push(stage.stage));
  assert.deepEqual(stages, ["gaps", "agent"]);
  assert.deepEqual(result, { plans: [] });
  assert.ok(calls[0].url.endsWith("/action-plans/suggestions/stream"));
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), { job_family: "data_analyst", mode: "full" });
});

it("rejects with the backend's detail on an error line", async () => {
  streamFetch([{ type: "stage", stage: "agent" }, { type: "error", status: 503, detail: "Action plans are unavailable" }]);
  await assert.rejects(streamActionPlanSuggestions("data_analyst", () => {}), (error: unknown) =>
    error instanceof ApiError && error.status === 503 && error.detail === "Action plans are unavailable");
});

it("rejects when the stream ends without a plan", async () => {
  streamFetch([{ type: "stage", stage: "gaps", gaps: [] }]);
  await assert.rejects(streamActionPlanSuggestions("data_analyst", () => {}), ApiError);
});
