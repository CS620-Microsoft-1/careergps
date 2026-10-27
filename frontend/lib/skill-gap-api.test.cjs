/* eslint-disable @typescript-eslint/no-require-imports -- Exercise the real API client with mocked fetch only. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const ts = require("typescript");

function load(relative, requireModule) {
  const source = fs.readFileSync(path.join(__dirname, relative), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS } }).outputText;
  const target = { exports: {} };
  new Function("module", "exports", "require", code)(target, target.exports, requireModule);
  return target.exports;
}

test("start, latest and poll share the authenticated client and never send resume content", async () => {
  const client = load("api/client.ts");
  const api = load("api/skill-gaps.ts", (name) => { assert.equal(name, "@/lib/api/client"); return client; });
  const requests = [], prior = global.fetch;
  client.setAccessTokenGetter(async () => "synthetic-test-token");
  global.fetch = async (url, options) => { requests.push({ url, options });
    return new Response(JSON.stringify({ id: "fake-run" }), { status: 200 }); };
  try {
    await api.startSkillGapRun({ job_family: "software_engineer", force: true });
    await api.getLatestSkillGapRun("software_engineer");
    await api.getSkillGapRun("fake-run");
    assert.deepEqual(requests.map(({ options }) => options.method), ["POST", "GET", "GET"]);
    for (const { options } of requests) assert.equal(options.headers.get("Authorization"), "Bearer synthetic-test-token");
    assert.deepEqual(JSON.parse(requests[0].options.body), { job_family: "software_engineer", force: true });
    assert.equal(requests[1].options.body, undefined);
    assert.match(requests[1].url, /\/runs\/latest\?job_family=software_engineer$/);
    assert.match(requests[2].url, /\/runs\/fake-run$/);
  } finally { global.fetch = prior; }
});
