import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { ApiError, apiGet } from "./client.ts";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

/** A fetch whose responses resolve only when the test says so. */
function fakeFetch() {
  const calls: { url: string; resolve: (response: Response) => void }[] = [];
  globalThis.fetch = ((url: string) => new Promise<Response>((resolve) => { calls.push({ url, resolve }); })) as typeof fetch;
  return calls;
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("apiGet", () => {
  it("shares one request between overlapping identical GETs and gives each caller its own copy", async () => {
    const calls = fakeFetch();
    const first = apiGet<{ user: { id: string } }>("/me");
    const second = apiGet<{ user: { id: string } }>("/me");
    await Promise.resolve();
    assert.equal(calls.length, 1);
    calls[0].resolve(json({ user: { id: "a" } }));
    const [a, b] = await Promise.all([first, second]);
    assert.deepEqual(a, b);
    a.user.id = "changed";
    assert.equal(b.user.id, "a");
  });

  it("sends a new request once the previous one finished", async () => {
    const calls = fakeFetch();
    const first = apiGet("/me");
    await Promise.resolve();
    calls[0].resolve(json({}));
    await first;
    const second = apiGet("/me");
    await Promise.resolve();
    assert.equal(calls.length, 2);
    calls[1].resolve(json({}));
    await second;
  });

  it("keeps different paths and callers with their own signal or timeout separate", async () => {
    const calls = fakeFetch();
    const pending = [apiGet("/me"), apiGet("/me/resume"), apiGet("/me", { signal: new AbortController().signal }),
      apiGet("/me", { timeoutMs: 1000 })];
    await Promise.resolve();
    assert.equal(calls.length, 4);
    calls.forEach((call) => call.resolve(json({})));
    await Promise.all(pending);
  });

  it("rejects every sharer when the request fails, then retries", async () => {
    const calls = fakeFetch();
    const results = Promise.allSettled([apiGet("/me"), apiGet("/me")]);
    await Promise.resolve();
    calls[0].resolve(json({ detail: "down" }, 503));
    const settled = await results;
    assert.ok(settled.every((r) => r.status === "rejected" && r.reason instanceof ApiError && r.reason.status === 503));
    void apiGet("/me");
    await Promise.resolve();
    assert.equal(calls.length, 2);
    calls[1].resolve(json({}));
  });
});
