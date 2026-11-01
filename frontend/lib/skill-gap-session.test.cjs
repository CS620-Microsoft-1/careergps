/* eslint-disable @typescript-eslint/no-require-imports -- Node tests transpile the actual controller without a browser or network. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const ts = require("typescript");

function load(name, requireModule) {
  const source = fs.readFileSync(path.join(__dirname, name), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020,
    module: ts.ModuleKind.CommonJS } }).outputText;
  const target = { exports: {} };
  new Function("module", "exports", "require", code)(target, target.exports, requireModule);
  return target.exports;
}
const { SkillGapSession } = load("skill-gap-session.ts");
const flush = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };
const missing = Object.assign(new Error("missing"), { status: 404 });
const profile = { user_id: "user-a", resume_id: "resume-a", filename: "Fictional.pdf",
  confirmed_at: "2026-10-26T10:00:00Z", job_family: "software_engineer" };
const run = (extra = {}) => ({ id: "run-a", user_id: profile.user_id, resume_id: profile.resume_id,
  status: "completed", phase: "completed", job_family: profile.job_family, filename: profile.filename,
  resume_hash: "server-hash", created_at: "2026-10-26T10:00:00Z", completed_at: "2026-10-26T10:01:00Z",
  elapsed_seconds: 60, model_calls: 1, report: null, error: null, reused: false, ...extra });

function fixture(options = {}) {
  const starts = [], latest = [], gets = [], loads = [], timers = new Map();
  let intent = Boolean(options.intent), consumed = 0;
  const deps = {
    loadProfile: async (family) => { loads.push(family); return family ? { ...profile, job_family: family } : profile; },
    consumeIntent: () => { consumed++; const value = intent; intent = false; return value; },
    getLatest: async (family) => { latest.push(family); if (options.latestError) throw options.latestError;
      return options.latestRun ?? run({ job_family: family }); },
    getRun: async (id) => { gets.push(id); return run(); },
    startRun: async (family, force) => { starts.push({ family, force });
      return run({ status: "queued", phase: "queued", completed_at: null, job_family: family }); },
    isNotFound: (error) => error.status === 404,
    errorMessage: (error) => error.message,
    now: () => Date.parse("2026-10-26T10:01:00Z"),
    setTimer: (callback) => { const key = {}; timers.set(key, callback); return key; },
    clearTimer: (key) => timers.delete(key),
    ...options.deps,
  };
  const session = new SkillGapSession(deps);
  let disconnect = session.connect();
  return { session, starts, latest, gets, loads, timers, deps, consumed: () => consumed,
    disconnect: () => disconnect(), reconnect: () => { disconnect = session.connect(); } };
}

test("restoring the server's latest run is read-only across initialize and effect remounts", async () => {
  const f = fixture(); await f.session.initialize();
  f.disconnect(); f.reconnect(); await f.session.initialize();
  assert.equal(f.latest.length, 1); assert.equal(f.starts.length, 0);
  assert.equal(f.session.getSnapshot().run.id, "run-a"); f.disconnect();
});
test("a successful save intent starts once only after latest returns 404", async () => {
  const f = fixture({ intent: true, latestError: missing });
  await Promise.all([f.session.initialize(), f.session.initialize()]);
  f.disconnect(); f.reconnect(); await f.session.initialize();
  assert.deepEqual(f.starts, [{ family: "software_engineer", force: false }]);
  assert.equal(f.consumed(), 1); f.disconnect();
});
test("a refresh without a save intent never turns a missing run into inference", async () => {
  const f = fixture({ latestError: missing }); await f.session.initialize();
  assert.equal(f.starts.length, 0); assert.equal(f.session.getSnapshot().run, null); f.disconnect();
});
test("a restore transport error consumes the intent but does not retry a paid request", async () => {
  const f = fixture({ intent: true, latestError: new Error("offline") }); await f.session.initialize();
  assert.equal(f.starts.length, 0); assert.equal(f.consumed(), 1);
  assert.equal(f.session.getSnapshot().error, "offline"); f.disconnect();
});
test("existing results satisfy the save intent without another model request", async () => {
  const f = fixture({ intent: true }); await f.session.initialize();
  assert.equal(f.starts.length, 0); assert.equal(f.consumed(), 1); f.disconnect();
});
test("owner or resume mismatch is rejected without starting a replacement", async () => {
  for (const extra of [{ user_id: "other" }, { resume_id: "other" }, { job_family: "ai_engineer" }]) {
    const f = fixture({ intent: true, latestRun: run(extra) }); await f.session.initialize();
    assert.equal(f.session.getSnapshot().run, null); assert.match(f.session.getSnapshot().error, /different résumé/);
    assert.equal(f.starts.length, 0); f.disconnect();
  }
});
test("explicit Analyze again passes force once and locks while a run is active", async () => {
  const f = fixture(); await f.session.initialize();
  await Promise.all([f.session.analyze(true), f.session.analyze(true)]);
  await f.session.analyze(false);
  assert.deepEqual(f.starts, [{ family: "software_engineer", force: true }]); f.disconnect();
});
test("switching direction restores via GET and requires an explicit analysis click", async () => {
  const f = fixture({ latestError: missing }); await f.session.initialize();
  f.session.changeFamily("ai_engineer"); await flush();
  assert.deepEqual(f.loads, [undefined, "ai_engineer"]);
  assert.equal(f.session.getSnapshot().snapshot.job_family, "ai_engineer");
  assert.deepEqual(f.latest, ["software_engineer", "ai_engineer"]);
  assert.equal(f.session.getSnapshot().family, "ai_engineer"); assert.equal(f.starts.length, 0); f.disconnect();
});
test("polling failure keeps the selected run without restarting it", async () => {
  const f = fixture({ latestRun: run({ status: "running", phase: "extracting" }),
    deps: { getRun: async () => { throw new Error("offline"); } } });
  await f.session.initialize();
  const callback = f.timers.values().next().value; callback(); await flush();
  assert.equal(f.session.getSnapshot().run.id, "run-a"); assert.equal(f.starts.length, 0);
  assert.match(f.session.getSnapshot().error, /not been restarted/); f.disconnect();
});
test("disconnect while loading cannot submit; reconnect finishes the one-time restoration", async () => {
  let resolve; const pending = new Promise((yes) => { resolve = yes; });
  const f = fixture({ intent: true, latestError: missing, deps: { loadProfile: () => pending } });
  f.disconnect(); resolve(profile); await f.session.initialize();
  assert.equal(f.starts.length, 0); f.reconnect(); await f.session.initialize();
  assert.equal(f.starts.length, 1); f.disconnect();
});

/** The profile on the server can change while the app is hidden (a new résumé or destination in setup). */
function changing(first = profile, options = {}) {
  const server = { profile: first, failLoad: options.failLoad ?? 0, intent: null };
  const forProfile = (extra) => run({ user_id: server.profile.user_id, resume_id: server.profile.resume_id,
    job_family: server.profile.job_family, ...extra });
  const f = fixture({ deps: {
    loadProfile: async () => { if (server.failLoad-- > 0) throw new Error("offline"); return server.profile; },
    consumeIntent: (p) => { const queued = server.intent; server.intent = null;
      return Boolean(queued && queued.resume_id === p.resume_id && queued.job_family === p.job_family); },
    getLatest: async (family) => { f.latest.push(family); if (options.missing?.(server.profile)) throw missing;
      return forProfile({ id: `run-${server.profile.resume_id}` }); },
    startRun: async (family, force) => { f.starts.push({ family, force });
      return forProfile({ id: "run-new", status: "queued", phase: "queued", completed_at: null }); },
    getRun: async () => forProfile({ id: "run-new" }),
  } });
  const remount = async () => { f.disconnect(); f.reconnect(); await f.session.initialize(); };
  return { ...f, server, remount };
}

test("showing the app again with an unchanged profile keeps its run without another restore", async () => {
  const f = changing(); await f.session.initialize();
  await f.remount(); await f.remount();
  assert.equal(f.latest.length, 1); assert.equal(f.starts.length, 0);
  assert.equal(f.session.getSnapshot().run.id, "run-resume-a"); f.disconnect();
});
test("a new résumé saved while hidden is restored on reconnect and can be analyzed again", async () => {
  const f = changing(); await f.session.initialize();
  f.server.profile = { ...profile, resume_id: "resume-b" };
  await f.remount();
  const state = f.session.getSnapshot();
  assert.equal(state.snapshot.resume_id, "resume-b"); assert.equal(state.run.id, "run-resume-b");
  assert.equal(state.error, undefined);
  await f.session.analyze(true);
  assert.deepEqual(f.starts, [{ family: "software_engineer", force: true }]);
  assert.equal(f.session.getSnapshot().error, undefined); f.disconnect();
});
test("a destination queued while hidden starts its analysis once after reconnect", async () => {
  const f = changing(profile, { missing: (p) => p.job_family === "data_analyst" }); await f.session.initialize();
  f.server.profile = { ...profile, job_family: "data_analyst" };
  f.server.intent = f.server.profile;
  await f.remount();
  assert.equal(f.session.getSnapshot().family, "data_analyst");
  assert.deepEqual(f.starts, [{ family: "data_analyst", force: false }]);
  await f.remount();
  assert.equal(f.starts.length, 1); assert.equal(f.session.getSnapshot().run.id, "run-new"); f.disconnect();
});
test("a failed first profile load recovers on reconnect", async () => {
  const f = changing(profile, { failLoad: 1 }); await f.session.initialize();
  assert.equal(f.session.getSnapshot().error, "offline"); assert.equal(f.session.getSnapshot().snapshot, null);
  await f.remount();
  const state = f.session.getSnapshot();
  assert.equal(state.error, undefined); assert.equal(state.snapshot.resume_id, "resume-a");
  assert.equal(state.run.id, "run-resume-a"); assert.equal(f.latest.length, 1); f.disconnect();
});
test("a failed reload keeps the profile and run already shown", async () => {
  const f = changing(); await f.session.initialize();
  f.server.failLoad = 1; f.server.profile = { ...profile, resume_id: "resume-b" };
  await f.remount();
  const state = f.session.getSnapshot();
  assert.equal(state.snapshot.resume_id, "resume-a"); assert.equal(state.run.id, "run-resume-a");
  assert.equal(state.error, undefined); assert.equal(f.latest.length, 1); f.disconnect();
});

test("saved profile pairs the selected role (the target role by default) with its résumé", () => {
  const { profileForAnalysis } = load("skill-gap-profile.ts");
  const user = { id: "u", target_role: "Data Analyst" };
  const resume = { id: "r", original_filename: "Fictional.pdf", created_at: "now" };
  assert.equal(profileForAnalysis(user, resume).job_family, "data_analyst");
  assert.equal(profileForAnalysis(user, resume, "ai_engineer").job_family, "ai_engineer");
  assert.throws(() => profileForAnalysis({ ...user, target_role: "unknown" }, resume), /supported target role/);
});
test("save intent stores only identifiers and cannot transfer across users or resumes", () => {
  const api = load("skill-gap-profile.ts"), values = new Map();
  const prior = global.sessionStorage;
  global.sessionStorage = { getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) };
  try {
    api.queueSkillGapAnalysis({ ...profile, classification: { private: "never store" } });
    assert.deepEqual(Object.keys(JSON.parse([...values.values()][0])).sort(), ["job_family", "resume_id", "user_id"]);
    assert.equal(api.consumeSkillGapIntent({ ...profile, user_id: "other" }), false);
    api.queueSkillGapAnalysis(profile);
    assert.equal(api.consumeSkillGapIntent(profile), true);
    assert.equal(api.consumeSkillGapIntent(profile), false);
  } finally { global.sessionStorage = prior; }
});
