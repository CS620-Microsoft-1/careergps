import assert from "node:assert/strict";
import { afterEach, it } from "node:test";

import { ACTION_PLAN_TIMEOUT_MS, getActionPlanSuggestions } from "./action-plans.ts";
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
