/* eslint-disable @typescript-eslint/no-require-imports -- Exercise the public streaming client with a mocked fetch. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const ts = require("typescript");

function load(relative, requireModule) {
  const source = fs.readFileSync(path.join(__dirname, relative), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  } }).outputText;
  const target = { exports: {} };
  new Function("module", "exports", "require", code)(target, target.exports, requireModule);
  return target.exports;
}

function clients() {
  const client = load("api/client.ts");
  client.setAccessTokenGetter(async () => "fictional-stream-test-token");
  const api = load("api/resumes.ts", (name) => {
    assert.equal(name, "@/lib/api/client");
    return client;
  });
  return { client, api };
}

const STEP = { type: "step", step: "extract", status: "started", detail: {} };
const RESULT = { filename: "r\u00e9sum\u00e9.pdf", classification: { technical_skills: ["Python"] } };
const file = () => new File(["fictional test upload"], "example.pdf", { type: "application/pdf" });

function response(events) {
  const bytes = new TextEncoder().encode(events.map((event) => JSON.stringify(event)).join("\n") + "\n");
  const multibyte = bytes.findIndex((value) => value >= 128);
  const cuts = multibyte > 3 ? [3, multibyte + 1, multibyte + 2, bytes.length] : [3, 11, bytes.length];
  let offset = 0;
  return new Response(new ReadableStream({ start(controller) {
    for (const end of cuts) {
      controller.enqueue(bytes.slice(offset, end));
      offset = end;
    }
    controller.close();
  } }), { status: 200, headers: { "Content-Type": "application/x-ndjson" } });
}

test("resume streaming decodes split NDJSON and UTF-8 with one authenticated request", async () => {
  const { api } = clients();
  const prior = global.fetch, requests = [], steps = [];
  global.fetch = async (url, options) => {
    requests.push({ url, options });
    return response([STEP, { type: "step", step: "classify", status: "done", detail: { validated: true } },
      { type: "result", data: RESULT }]);
  };
  try {
    const result = await api.streamResumeAnalysis(file(), (event) => steps.push(event));
    assert.deepEqual(result, RESULT);
    assert.deepEqual(steps.map((event) => [event.step, event.status]), [["extract", "started"], ["classify", "done"]]);
    assert.equal(requests.length, 1);
    assert.match(requests[0].url, /\/resumes\/analyze\/stream$/);
    assert.equal(requests[0].options.method, "POST");
    assert.equal(requests[0].options.headers.get("Authorization"), "Bearer fictional-stream-test-token");
    assert.equal(requests[0].options.headers.has("Content-Type"), false);
    assert.equal(requests[0].options.body.get("file").name, "example.pdf");
  } finally { global.fetch = prior; }
});

test("an in-stream error rejects with the backend detail and never retries", async () => {
  const { api, client } = clients();
  const prior = global.fetch, steps = [];
  let calls = 0;
  global.fetch = async () => { calls++; return response([STEP,
    { type: "error", status: 503, detail: "The fictional analysis failed." }]); };
  try {
    await assert.rejects(api.streamResumeAnalysis(file(), (event) => steps.push(event)), (error) => {
      assert.ok(error instanceof client.ApiError);
      assert.equal(error.status, 503);
      assert.equal(error.detail, "The fictional analysis failed.");
      return true;
    });
    assert.deepEqual(steps, [STEP]);
    assert.equal(calls, 1);
  } finally { global.fetch = prior; }
});

test("a stream ending without a result is rejected without a fallback request", async () => {
  const { api, client } = clients();
  const prior = global.fetch;
  let calls = 0;
  global.fetch = async () => { calls++; return response([STEP]); };
  try {
    await assert.rejects(api.streamResumeAnalysis(file(), () => {}), (error) => {
      assert.ok(error instanceof client.ApiError);
      assert.equal(error.status, 0);
      assert.match(error.message, /stopped before it finished/);
      return true;
    });
    assert.equal(calls, 1);
  } finally { global.fetch = prior; }
});

test("cancelling an active stream propagates AbortError without restarting it", { timeout: 2000 }, async () => {
  const { api } = clients();
  const prior = global.fetch, controller = new AbortController();
  let calls = 0, started;
  const requestStarted = new Promise((resolve) => { started = resolve; });
  global.fetch = async (_url, options) => {
    calls++;
    const body = new ReadableStream({ start(stream) {
      options.signal.addEventListener("abort", () => stream.error(options.signal.reason), { once: true });
    } });
    started();
    return new Response(body, { status: 200 });
  };
  try {
    const pending = api.streamResumeAnalysis(file(), () => {}, controller.signal);
    await requestStarted;
    controller.abort(new DOMException("Cancelled by the caller", "AbortError"));
    await assert.rejects(pending, (error) => error.name === "AbortError");
    assert.equal(calls, 1);
  } finally { global.fetch = prior; }
});

test("HTTP 401 uses the shared unauthorized handler before reading a stream", async () => {
  const { api, client } = clients();
  const prior = global.fetch;
  let calls = 0, unauthorized = 0, steps = 0;
  client.setUnauthorizedHandler(() => { unauthorized++; });
  global.fetch = async () => { calls++; return new Response(JSON.stringify({ detail: "Not authenticated" }),
    { status: 401, headers: { "Content-Type": "application/json" } }); };
  try {
    await assert.rejects(api.streamResumeAnalysis(file(), () => { steps++; }), (error) => {
      assert.ok(error instanceof client.ApiError);
      assert.equal(error.status, 401);
      return true;
    });
    assert.equal(unauthorized, 1);
    assert.equal(steps, 0);
    assert.equal(calls, 1);
  } finally { global.fetch = prior; }
});
