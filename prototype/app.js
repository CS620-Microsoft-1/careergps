const D = DATA;
const $app = document.getElementById("app");
const $drawer = document.getElementById("drawer-root");

/* ---------- ICONS ---------- */
const svg = (p, s = 20) => `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const I = {
  target: s => svg('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>', s),
  grid: s => svg('<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/>', s),
  bars: s => svg('<path d="M4 20h16M6 20V11M10 20V6M14 20v-7M18 20V9"/>', s),
  case: s => svg('<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/>', s),
  list: s => svg('<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>', s),
  code: s => svg('<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 6l-3 12"/>', s),
  bell: s => svg('<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>', s),
  gear: s => svg('<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2.5 12h3M18.5 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>', s),
  search: s => svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>', s),
  spark: s => svg('<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M18.5 15l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/><path d="M5.5 15l.5 1.3 1.3.5-1.3.5-.5 1.3-.5-1.3-1.3-.5 1.3-.5z"/>', s),
  chev: s => svg('<path d="M9 6l6 6-6 6"/>', s || 16),
  check: s => svg('<path d="M5 12l5 5 9-10"/>', s),
  up: s => svg('<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>', s),
  book: s => svg('<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M9 7h6"/>', s),
  bank: s => svg('<path d="M3 10l9-6 9 6M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 21h18"/>', s),
  user: s => svg('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>', s),
  swap: s => svg('<path d="M7 7h13l-4-4M17 17H4l4 4"/>', s),
  out: s => svg('<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11"/>', s),
  x: s => svg('<path d="M6 6l12 12M18 6L6 18"/>', s),
  arrowUp: s => svg('<path d="M12 19V5M6 11l6-6 6 6"/>', s || 14)
};
const GOOGLE = `<svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.5l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.6 5.4 2.6 13.3l7.8 6C12.3 13.4 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 7-10.2 7-17.6z"/><path fill="#FBBC05" d="M10.4 28.7c-.5-1.4-.8-3-.8-4.7s.3-3.2.8-4.7l-7.8-6C.9 16.6 0 20.2 0 24s.9 7.4 2.6 10.7z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.9 2.3-8.3 2.3-6.3 0-11.7-3.9-13.6-9.8l-7.8 6C6.6 42.6 14.6 48 24 48z"/></svg>`;
const MSFT = `<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path fill="#1ba1e2" d="M1 1h10.5v10.5H1zM12.5 1H23v10.5H12.5zM1 12.5h10.5V23H1zM12.5 12.5H23V23H12.5z"/></svg>`;

const NAV = [
  ["dashboard", "grid", "Dashboard"], ["analysis", "target", "Career Analysis"], ["gaps", "bars", "Skill Gaps", 3],
  ["opps", "case", "Resources"], ["plan", "list", "Action Plan"]
];
const ROLES = ["Software Engineer", "Data Analyst", "AI Engineer"];

const S = {
  screen: "login",          // login | signup | onboarding | app
  view: "dashboard",
  menu: false,
  copilot: false,
  chat: [],
  marketRole: "AI Engineer",
  resTab: "projects",
  evidenceOpen: {},
  done: new Set(["0-0", "0-1"]),
  onboarded: false,
  resume: null
};
try { const t = JSON.parse(localStorage.getItem("cgps-tasks")); if (t) S.done = new Set(t); } catch (e) {}

const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const totalTasks = () => D.weeks.reduce((n, w) => n + w[1].length, 0);
const cite = k => `<button class="cite" data-a="cite" data-k="${esc(k)}">[${esc(k)}]</button>`;
const cites = ks => `<div class="cites">Sources: ${ks.map(cite).join("")}</div>`;
const tags = (a, cls = "") => `<div class="tags">${a.map(t => `<span class="tag ${cls}">${esc(t)}</span>`).join("")}</div>`;
const initials = n => n.split(/\s+/).filter(Boolean).map(w => w[0]).join("").slice(0, 2).toUpperCase();
function toast(m) { const t = document.createElement("div"); t.className = "toast"; t.textContent = m; document.body.appendChild(t); setTimeout(() => t.remove(), 2200); }

/* ---------- AUTH ---------- */
const logo = () => `<div class="logo"><i>${I.target(18)}</i>CareerGPS</div>`;
function authLeft(title, text, extra = "") {
  return `<div class="auth-left">${logo()}
    <div class="mid"><h1>${title}</h1><p>${text}</p>${extra}</div>
    <p class="foot">Built for students at UW–Madison</p></div>`;
}
const flow = `<div class="flow">${["Your Profile", "Job Market", "Skill Gaps", "Action Plan"].map((t, i) => `<span><em>${i + 1}</em>${t}</span>`).join("<b>→</b>")}</div>`;
const loginLeft = () => authLeft("Become a stronger candidate.", "Understand where you stand, what employers are looking for, and what to do next.", flow);
const uwBtn = (cls = "") => `<button type="button" class="btn lg ${cls}" data-a="sso"><span class="uw">UW</span>Continue with UW–Madison</button>`;

function loginView() {
  return `<div class="auth">${loginLeft()}<div class="auth-right"><form class="auth-card" data-form="login">
    <h2>Welcome back</h2><p class="sub">Sign in to continue your career journey.</p>
    <div class="field"><label for="em">Email</label><input id="em" type="email" placeholder="student@wisc.edu" required></div>
    <div class="field"><label for="pw">Password</label><input id="pw" type="password" placeholder="Enter your password" required></div>
    <div class="between"><label class="check"><input type="checkbox"> Remember me</label><button type="button" class="link" data-a="toast" data-m="Password reset link sent (demo)">Forgot password?</button></div>
    <button class="btn primary lg block" type="submit">Sign In</button>
    <div class="divider">or</div>
    <div class="social">
      <button type="button" class="btn lg" data-a="sso">${GOOGLE}Google</button>
      <button type="button" class="btn lg" data-a="sso">${MSFT}Microsoft</button>
      ${uwBtn("wide")}
    </div>
    <p class="switch">Don't have an account? <button type="button" class="link" data-a="screen" data-s="signup">Create Account</button></p>
  </form></div></div>`;
}
function signupView() {
  const y = new Date().getFullYear();
  return `<div class="auth">${loginLeft()}<div class="auth-right"><form class="auth-card" data-form="signup">
    <h2>Create your account</h2><p class="sub">It takes less than a minute.</p>
    <div class="field"><label for="n">Full Name</label><input id="n" placeholder="Alex Johnson" required></div>
    <div class="field"><label for="ue">University Email</label><input id="ue" type="email" placeholder="student@wisc.edu" required></div>
    <div class="row2">
      <div class="field"><label for="p1">Password</label><input id="p1" type="password" required minlength="6"></div>
      <div class="field"><label for="p2">Confirm Password</label><input id="p2" type="password" required></div>
    </div>
    <div class="row2">
      <div class="field"><label for="tr">Target Role</label><select id="tr">${ROLES.map(r => `<option ${r === "AI Engineer" ? "selected" : ""}>${r}</option>`).join("")}</select></div>
      <div class="field"><label for="gy">Graduation Year</label><select id="gy">${[0, 1, 2, 3, 4].map(i => `<option ${i === 1 ? "selected" : ""}>${y + i}</option>`).join("")}</select></div>
    </div>
    <div class="field"><label for="un">University</label><input id="un" value="University of Wisconsin–Madison"></div>
    <div class="field"><span class="lbl">Experience Level</span><div class="seg"><label><input type="radio" name="lvl" value="Internship">Internship</label><label><input type="radio" name="lvl" value="Full-time" checked>Full-time</label></div></div>
    <label class="check"><input type="checkbox" id="terms"> <span>I agree to the <a href="#" data-a="toast" data-m="Terms (demo)">Terms</a> and <a href="#" data-a="toast" data-m="Privacy Policy (demo)">Privacy Policy</a>.</span></label>
    <div class="err" id="err"></div>
    <button class="btn primary lg block" type="submit">Create Account</button>
    <p class="switch">Already have an account? <button type="button" class="link" data-a="screen" data-s="login">Sign In</button></p>
  </form></div></div>`;
}

/* ---------- ONBOARDING ---------- */
function onboardingView() {
  const s = D.student, y = new Date().getFullYear();
  return `<div class="auth">${authLeft("Where do you want your career to go?", "Tell us your goal. We'll compare your experience with real job-market data and map the clearest path forward.")}
  <div class="auth-right"><form class="auth-card" data-form="onboard">
    <h2>Your career goal</h2><p class="sub">You can change this anytime.</p>
    <div class="field"><label for="o1">Target Role</label><select id="o1">${ROLES.map(r => `<option ${r === s.role ? "selected" : ""}>${r}</option>`).join("")}</select></div>
    <div class="row2">
      <div class="field"><label for="o2">Graduation Year</label><select id="o2">${[0, 1, 2, 3, 4].map(i => `<option ${String(y + i) === s.gradYear ? "selected" : ""}>${y + i}</option>`).join("")}</select></div>
      <div class="field"><label for="o3">Preferred Location</label><input id="o3" value="${esc(s.location)}" placeholder="United States"></div>
    </div>
    <div class="field"><span class="lbl">Experience Level</span><div class="seg">${["Internship", "Full-time"].map(l => `<label><input type="radio" name="lvl2" value="${l}" ${l === s.level ? "checked" : ""}>${l}</label>`).join("")}</div></div>
    <div class="field"><span class="lbl">Résumé</span><label class="upload ${S.resume ? "done" : ""}" id="up">${I.up(20)}<b id="upt">${S.resume ? "✓ " + esc(S.resume) : "Upload your résumé"}</b>PDF or DOCX, up to 10 MB<input type="file" id="resume" accept=".pdf,.doc,.docx" hidden></label></div>
    <button class="btn primary lg block" type="submit">Analyze My Career Profile ${I.chev()}</button>
  </form></div></div>`;
}

/* ---------- SHELL ---------- */
function shell(body) {
  const s = D.student;
  return `<div class="shell">
    <aside class="side">${logo()}
      <nav class="nav">${NAV.map(n => `<button class="${S.view === n[0] ? "on" : ""}" data-a="nav" data-v="${n[0]}">${I[n[1]](18)}${n[2]}${n[3] ? `<span class="badge">${n[3]}</span>` : ""}</button>`).join("")}</nav>
      <div class="strength"><div class="r"><span>Profile strength</span><b>72%</b></div><div class="track"><div class="fill" style="width:72%"></div></div>
        <p>Upload your latest résumé to improve accuracy.</p><button class="link" data-a="nav" data-v="profile">Complete profile ${I.chev(14)}</button></div>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="search">${I.search(18)}<span>Search CareerGPS</span></div>
        <button class="iconbtn" aria-label="Notifications" data-a="toast" data-m="You're all caught up">${I.bell(19)}<span class="dot"></span></button>
        <button class="iconbtn" aria-label="Settings" data-a="toast" data-m="Settings (demo)">${I.gear(19)}</button>
        <button class="userbtn ${S.view === "profile" ? "on" : ""}" data-a="usermenu" aria-label="Student menu"><span class="avatar">${initials(s.name)}</span><span class="who-t"><b>${esc(s.name)}</b><small>UW–Madison · ${esc(s.gradYear)}</small></span></button>
        ${S.menu ? `<div class="pop"><div class="who">${esc(s.email)}</div><button data-a="nav" data-v="profile">${I.user(16)}My Profile</button><button data-a="screen" data-s="login">${I.swap(16)}Switch Account</button><button data-a="screen" data-s="login">${I.out(16)}Sign Out</button></div>` : ""}
      </header>
      <div class="mobile-nav">${NAV.map(n => `<button class="${S.view === n[0] ? "on" : ""}" data-a="nav" data-v="${n[0]}">${n[2]}</button>`).join("")}</div>
      <div class="page">${body}</div>
    </div>
  </div>
  <button class="fab" data-a="copilot">${I.spark(18)}Ask CareerGPS</button>`;
}
const head = (t, p, right = "") => `<div class="page-h"><div><h1>${t}</h1>${p ? `<p>${p}</p>` : ""}</div>${right}</div>`;
const cardHead = (t, sub, right = "") => `<div class="card-h"><h3>${t}${sub ? `<small>${sub}</small>` : ""}</h3>${right}</div>`;
const barRow = (label, v, warn) => `<div class="bar"><div class="t"><span>${label}</span><b>${v}%</b></div><div class="track"><div class="fill ${warn ? "warn" : ""}" style="width:${v}%"></div></div></div>`;
const highGaps = () => D.gaps.filter(g => g.pri === "High");

/* ---------- PAGES ---------- */
function dashboard() {
  const s = D.student, done = S.done.size, total = totalTasks();
  const goal = `<div class="goal">${I.target(16)}<b>${esc(s.role)} · ${s.level === "Internship" ? "Internship" : "New Grad"} ${esc(s.gradYear)}</b><button class="btn" data-a="screen" data-s="onboarding">Edit</button></div>`;
  return head(`Good morning, ${esc(s.first)}`, `Here's how you compare with the current ${esc(s.role)} market.`, goal) +
  `<div class="grid g4">
    <div class="card stat"><div class="k">Career readiness</div><div class="num">72%</div><div class="s up">↑ 6% since last analysis</div></div>
    <div class="card stat"><div class="k">Jobs analyzed</div><div class="num">64</div><div class="s">Entry-level, last 90 days</div></div>
    <div class="card stat"><div class="k">High-priority gaps</div><div class="num">${highGaps().length}</div><div class="s">${highGaps().map(g => g.skill).join(", ")}</div></div>
    <div class="card stat"><div class="k">Plan progress</div><div class="num">${done}<small>/ ${total} tasks</small></div><div class="track" style="margin-top:10px"><div class="fill" style="width:${Math.round(done / total * 100)}%"></div></div></div>
  </div>
  <div class="next"><span class="ic">${I.spark(18)}</span><div><small>Recommended next step</small><b>Build a production-ready RAG application</b></div><button class="btn" data-a="nav" data-v="plan">View Action Plan ${I.chev(14)}</button></div>
  <div class="grid g-main mt">
    <div class="card">${cardHead("Readiness breakdown", "Last analyzed today", `<button class="link" data-a="reanalyze">Re-run</button>`)}
      <div class="bars">${D.readiness.cats.map(c => barRow(c[0], c[1], c[1] < 60)).join("")}</div></div>
    <div class="card">${cardHead("Priority skill gaps", "Ranked by career impact", `<button class="link" data-a="nav" data-v="gaps">View all ${I.chev(14)}</button>`)}
      <div class="rows">${D.gaps.slice(0, 4).map((g, i) => `<div><span class="n">${i + 1}</span><div class="grow"><b>${g.skill}</b><small>${g.demand}% of postings</small></div><span class="tag ${g.pri === "High" ? "red" : "amber"}">${g.pri}</span></div>`).join("")}</div></div>
  </div>`;
}

function analysis() {
  const filters = `<div class="filters">
    <select aria-label="Role" data-a="role">${ROLES.map(r => `<option ${r === S.marketRole ? "selected" : ""}>${r}</option>`).join("")}</select>
    <select aria-label="Experience"><option>New grad / Entry level</option></select>
    <select aria-label="Location"><option>United States</option></select>
    <select aria-label="Posting date"><option>Last 90 days</option></select></div>`;
  const steps = [["Profile", "Résumé analyzed"], ["Market", "64 jobs · 21 skills"], ["Gap analysis", "3 high-priority gaps"], ["Action", "Roadmap generated"]];
  return head("Career Analysis", "What employers are looking for, based on 64 entry-level postings.", filters) +
  `<div class="grid g-main" style="align-items:start">
    <div class="card">${cardHead("Skill demand", "Share of postings that mention each skill")}
      <div class="bars">${D.market.map(m => barRow(m[0], m[1])).join("")}</div>${cites(["Job 12", "Job 24", "Job 31", "O*NET"])}</div>
    <div style="display:grid;gap:16px;align-content:start">
      <div class="card">${cardHead("Common responsibilities")}
        <ul class="resp">${D.responsibilities.map(r => `<li>${r}</li>`).join("")}</ul>${cites(["Job 18", "Job 40", "O*NET"])}</div>
      <div class="card">${cardHead("How this was generated", "Four agents, run in sequence", `<button class="link" data-a="details">Details ${I.chev(14)}</button>`)}
        <div class="pipeline">${steps.map(p => `<div><span class="ic">${I.check(12)}</span><div><b>${p[0]} Agent</b><small>${p[1]}</small></div></div>`).join("")}</div></div>
    </div>
  </div>`;
}

function profile() {
  const s = D.student;
  const col = (title, color, list, key) => `<div class="card"><div class="col-h"><span class="dotc" style="background:${color}"></span>${title}<span class="muted" style="font-weight:400;margin-left:auto">${list.length}</span></div>
    ${list.map((k, i) => { const id = key + i, open = S.evidenceOpen[id]; return `<button class="sk-row ${open ? "open" : ""}" data-a="evidence" data-id="${id}" aria-expanded="${!!open}"><span>${k[0]}</span>${I.chev(14)}</button>
      ${open ? `<div class="evid">${esc(k[1])}<div class="cites" style="margin-top:6px">${k[2].map(cite).join("")}</div></div>` : ""}`; }).join("")}</div>`;
  return head("Your Profile", "What CareerGPS found in your résumé.") +
  `<div class="card" style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:16px"><div class="avatar lg">${initials(s.name)}</div>
    <div style="flex:1;min-width:200px"><h3 style="font-size:16px">${esc(s.name)}</h3><p class="muted">${esc(s.email)}</p>
    <div class="tags" style="margin-top:8px"><span class="tag brand">${esc(s.role)}</span><span class="tag">Class of ${esc(s.gradYear)}</span><span class="tag">${esc(s.level)}</span></div></div>
    <button class="btn" data-a="screen" data-s="onboarding">Update résumé</button></div>
  <div class="note">${I.check(16)}Skills are rated by demonstrated evidence, not keywords.</div>
  <div class="grid g3" style="align-items:start">
    ${col("Strong", "var(--green)", D.skills.strong, "s")}${col("Some experience", "#d19a36", D.skills.some, "m")}${col("Not yet demonstrated", "var(--red)", D.skills.none, "n")}
  </div>`;
}

function gaps() {
  return head("Skill Gaps", "Prioritized by market demand and your demonstrated experience.") +
  `<div class="card gtable">
    <div class="grow-r hd"><span>Skill</span><span>Market demand</span><span>Your evidence</span><span>Recommended action</span><span></span></div>
    ${D.gaps.map((g, i) => `<div class="grow-r">
      <div class="sk"><b>${g.skill}</b><span class="tag ${g.pri === "High" ? "red" : g.pri === "Medium" ? "amber" : ""}">${g.pri}</span></div>
      <div class="dm">${g.demand}%<div class="track"><div class="fill" style="width:${g.demand}%"></div></div></div>
      <div class="ev ${g.evidence === "Some experience" ? "some" : ""}">${g.evidence === "No demonstrated experience" ? "None yet" : g.evidence}</div>
      <div class="ac">${g.action} <button class="cite" data-a="why" data-i="${i}">Why?</button></div>
      <button class="btn" data-a="addgap" data-s="${esc(g.skill)}">Add to plan</button>
    </div>`).join("")}
  </div>`;
}

function plan() {
  const total = totalTasks(), done = S.done.size;
  return head("Action Plan", "A five-week roadmap built from your highest-impact gaps.", `<div style="display:flex;gap:8px"><button class="btn" data-a="toast" data-m="GitHub issues created (demo)">Create GitHub Issues</button><button class="btn primary" data-a="toast" data-m="Project started. Good luck!">Start Project</button></div>`) +
  `<div class="card plan-h"><div><span class="tag brand">Highest-impact next step</span><h2>Build a Production-Ready RAG Application</h2>
      <p>Closes three gaps in your profile: Docker, vector databases, and CI/CD.</p></div>
    <div class="prog"><b>${done}</b> <span>/ ${total} tasks done</span><div class="track"><div class="fill" style="width:${Math.round(done / total * 100)}%"></div></div></div></div>
  <div class="card weeks">${D.weeks.map((w, wi) => {
    const n = w[1].filter((_, ti) => S.done.has(wi + "-" + ti)).length;
    const st = n === w[1].length ? '<span class="tag green">Done</span>' : n > 0 ? '<span class="tag brand">In progress</span>' : "";
    return `<div class="week"><div><div class="wn">Week ${wi + 1} ${st}</div><h4>${w[0]}</h4></div>
      <div class="tasks">${w[1].map((t, ti) => { const k = wi + "-" + ti, d = S.done.has(k); return `<label class="task ${d ? "done" : ""}"><input type="checkbox" data-a="task" data-k="${k}" ${d ? "checked" : ""}><span>${t}</span></label>`; }).join("")}</div></div>`; }).join("")}</div>`;
}

function opps() {
  const tabs = [["projects", "Projects", D.projects.length], ["courses", "Courses", D.courses.length], ["clubs", "Clubs", D.clubs.length], ["events", "Events", D.hacks.length], ["learning", "Free learning", D.learning.length]];
  const gapHit = skills => skills.filter(k => highGaps().some(g => k.toLowerCase().startsWith(g.skill.toLowerCase().slice(0, 6)))).length;
  let body = "";
  if (S.resTab === "projects") body = `<div class="grid g2">${D.projects.map(p => { const n = gapHit(p.skills); return `<div class="card proj ${p.best ? "best" : ""}">
      <div class="tags"><span class="tag ${n ? "red" : ""}">Closes ${n} high-priority gap${n === 1 ? "" : "s"}</span>${p.best ? '<span class="tag green">Best fit</span>' : ""}</div>
      <h3>${p.name}</h3><p class="meta">${p.weeks} weeks · ${p.diff}</p>
      ${tags(p.skills.slice(0, 4))}
      <div class="ft"><span></span><button class="link" data-a="roadmap" data-n="${esc(p.name)}">Generate roadmap ${I.chev(14)}</button></div></div>`; }).join("")}</div>`;
  if (S.resTab === "courses") body = `<div class="grid g3">${D.courses.map(c => { const [code, name] = c[0].split(" — "); return `<div class="card res"><span class="tag brand">${code}</span><h3>${name}</h3><p>${c[1].replace(/^Recommended (because|to) /, "").replace(/^./, m => m.toUpperCase())}</p>
      <div class="ft"><span>Spring 2027 · 3 credits</span><button class="link" data-a="toast" data-m="Opening ${code} (demo)">View ${I.chev(14)}</button></div></div>`; }).join("")}</div>`;
  if (S.resTab === "clubs") body = `<div class="grid g2">${D.clubs.map(c => `<div class="card res"><div style="display:flex;gap:12px;align-items:center"><span class="init">${initials(c.name)}</span><div><h3 style="margin:0">${c.name}</h3><p>${c.skills.join(" · ")}</p></div></div>
      <div class="ft"><span>Next: ${c.event}</span><button class="link" data-a="toast" data-m="Joined ${c.name} (demo)">Join ${I.chev(14)}</button></div></div>`).join("")}</div>`;
  if (S.resTab === "events") body = `<div class="card"><div class="rows">${D.hacks.map(h => `<div><div class="grow"><b>${h.title}</b><small>${h.name} · Team of ${h.team} · ${h.skills.join(", ")}</small></div><span class="muted" style="font-size:13px;min-width:110px">${h.date}</span><span class="tag ${h.status === "Open" ? "green" : "amber"}">${h.status}</span><button class="btn" data-a="toast" data-m="Registration saved (demo)">Register</button></div>`).join("")}</div></div>`;
  if (S.resTab === "learning") body = `<div class="card"><div class="rows">${D.learning.map(l => `<div><div class="grow"><b>${l[1]}</b><small>${l[0]} · Free</small></div><span class="tag ${highGaps().some(g => g.skill === l[2]) ? "red" : ""}">${l[2]}</span><button class="btn" data-a="toast" data-m="Opening ${l[0]} (demo)">Open</button></div>`).join("")}</div></div>`;
  return head("Resources", "Projects, courses, and communities that turn your gaps into demonstrated skills.") +
  `<div class="tabs">${tabs.map(t => `<button class="${S.resTab === t[0] ? "on" : ""}" data-a="restab" data-t="${t[0]}">${t[1]}<span class="cnt">${t[2]}</span></button>`).join("")}</div>${body}`;
}

const PAGES = { dashboard, analysis, profile, gaps, plan, opps };

/* ---------- COPILOT & DRAWERS ---------- */
const closeBtn = a => `<button class="iconbtn" data-a="${a}" aria-label="Close">${I.x(20)}</button>`;
function copilotHTML() {
  return `<div class="overlay" data-a="closecopilot"></div><aside class="drawer" role="dialog" aria-label="CareerGPS Copilot">
    <header><h3>CareerGPS Copilot</h3>${closeBtn("closecopilot")}</header>
    <div class="body" id="chatbody">${S.chat.length ? "" : `<p class="desc" style="color:var(--muted)">Ask me about your gaps, jobs, projects, or courses.</p>` + Object.keys(D.copilot).map(q => `<button class="sugg" data-a="ask" data-q="${esc(q)}">${q}</button>`).join("")}
    ${S.chat.map(m => m.u ? `<div class="msg u">${esc(m.t)}</div>` : `<div class="msg a">${esc(m.t)}${cites(m.c || [])}</div>`).join("")}</div>
    <form class="cinput" data-form="chat"><input id="cq" placeholder="Ask CareerGPS…" aria-label="Ask CareerGPS"><button class="btn primary" type="submit">Send</button></form></aside>`;
}
function ask(q) {
  S.chat.push({ u: true, t: q });
  const r = D.copilot[q] || { a: "Based on the 64 AI Engineer roles in your market dataset, your highest-impact move right now is to close Docker, CI/CD and vector database gaps through a single deployed RAG project.", c: ["Job 24", "O*NET"] };
  S.chat.push({ t: r.a, c: r.c });
  renderDrawer(); const b = document.getElementById("chatbody"); if (b) b.scrollTop = b.scrollHeight;
}
function sourceDrawer(k) {
  const s = D.sources[k]; if (!s) return "";
  return `<div class="overlay" data-a="closedrawer"></div><aside class="drawer" role="dialog" aria-label="Source"><header><h3>Source · ${esc(k)}</h3>${closeBtn("closedrawer")}</header>
    <div class="body"><div class="card"><span class="tag brand">${s.org}</span><h3 style="margin:10px 0 6px">${s.title}</h3><p class="desc">${s.text}</p></div>
    <p class="desc" style="color:var(--muted)">CareerGPS shows the evidence behind each recommendation so you can verify it.</p></div></aside>`;
}
function detailsDrawer() {
  return `<div class="overlay" data-a="closedrawer"></div><aside class="drawer" role="dialog" aria-label="Analysis details"><header><h3>Analysis Details</h3>${closeBtn("closedrawer")}</header>
  <div class="body">${[["Student Profile Agent", "Extracted 10 skills from your résumé and rated each by demonstrated evidence."], ["Market Intelligence Agent", "Retrieved 64 entry-level postings from the last 90 days; found 21 recurring skills."], ["Gap Analysis Agent", "Compared demand with your evidence; ranked 3 gaps as high priority."], ["Action Agent", "Built a 5-week roadmap around one project that closes multiple gaps."]].map(a => `<div class="card"><h3>${a[0]}</h3><p class="desc">${a[1]}</p></div>`).join("")}</div></aside>`;
}
function whyDrawer(g) {
  return `<div class="overlay" data-a="closedrawer"></div><aside class="drawer" role="dialog" aria-label="Why ${esc(g.skill)}"><header><h3>Why ${esc(g.skill)}?</h3>${closeBtn("closedrawer")}</header>
    <div class="body"><p>${g.why}</p><div class="bars">${barRow("Market demand", g.demand)}</div><p class="muted">Your evidence: ${g.evidence}</p>${cites(g.cites)}</div></aside>`;
}
let drawerHTML = "";
function renderDrawer() { $drawer.innerHTML = S.copilot ? copilotHTML() : drawerHTML; }
function openDrawer(h) { S.copilot = false; drawerHTML = h; renderDrawer(); }

/* ---------- RENDER ---------- */
function render() {
  const sc = S.screen;
  $app.innerHTML = sc === "login" ? loginView() : sc === "signup" ? signupView() : sc === "onboarding" ? onboardingView() : shell(PAGES[S.view]());
  renderDrawer();
}

/* ---------- EVENTS ---------- */
document.addEventListener("click", e => {
  const el = e.target.closest("[data-a]");
  if (!el) { if (S.menu) { S.menu = false; render(); } return; }
  const a = el.dataset.a;
  if (a === "task" || a === "role") return;
  if (a !== "usermenu" && S.menu) S.menu = false;
  switch (a) {
    case "screen": S.screen = el.dataset.s; S.menu = false; S.copilot = false; drawerHTML = ""; render(); window.scrollTo(0, 0); break;
    case "sso": S.onboarded = true; S.screen = "app"; S.view = "dashboard"; render(); break;
    case "nav": S.view = el.dataset.v; S.menu = false; render(); window.scrollTo(0, 0); break;
    case "usermenu": S.menu = !S.menu; render(); e.stopPropagation(); break;
    case "toast": e.preventDefault(); toast(el.dataset.m); break;
    case "cite": openDrawer(sourceDrawer(el.dataset.k)); break;
    case "details": openDrawer(detailsDrawer()); break;
    case "closedrawer": drawerHTML = ""; renderDrawer(); break;
    case "copilot": S.copilot = true; renderDrawer(); break;
    case "closecopilot": S.copilot = false; renderDrawer(); break;
    case "ask": ask(el.dataset.q); break;
    case "evidence": S.evidenceOpen[el.dataset.id] = !S.evidenceOpen[el.dataset.id]; render(); break;
    case "restab": S.resTab = el.dataset.t; render(); break;
    case "why": openDrawer(whyDrawer(D.gaps[el.dataset.i])); break;
    case "reanalyze": toast("Re-analyzing… readiness is up to date"); break;
    case "addgap": toast(el.dataset.s + " added to your Action Plan"); break;
    case "roadmap": toast("Roadmap for " + el.dataset.n + " generated"); break;
  }
});
document.addEventListener("change", e => {
  const t = e.target;
  if (t.dataset.a === "task") {
    t.checked ? S.done.add(t.dataset.k) : S.done.delete(t.dataset.k);
    try { localStorage.setItem("cgps-tasks", JSON.stringify([...S.done])); } catch (x) {}
    render();
  } else if (t.dataset.a === "role") { S.marketRole = t.value.replace("Role: ", ""); render(); }
  else if (t.id === "resume" && t.files[0]) { S.resume = t.files[0].name; document.getElementById("up").classList.add("done"); document.getElementById("upt").textContent = "✓ " + S.resume; }
});
document.addEventListener("submit", e => {
  e.preventDefault();
  const f = e.target.dataset.form, v = id => document.getElementById(id).value;
  if (f === "login") { if (S.onboarded) { S.screen = "app"; S.view = "dashboard"; } else S.screen = "onboarding"; render(); }
  else if (f === "signup") {
    const err = document.getElementById("err");
    if (v("p1") !== v("p2")) return err.textContent = "Passwords don't match.";
    if (!document.getElementById("terms").checked) return err.textContent = "Please accept the Terms of Service and Privacy Policy.";
    Object.assign(D.student, { name: v("n"), first: v("n").split(" ")[0], email: v("ue"), university: v("un"), gradYear: v("gy"), role: v("tr"),
      level: document.querySelector("input[name=lvl]:checked").value });
    S.screen = "onboarding"; render();
  } else if (f === "onboard") {
    Object.assign(D.student, { role: v("o1"), gradYear: v("o2"), location: v("o3"), level: document.querySelector("input[name=lvl2]:checked").value });
    S.onboarded = true; S.screen = "app"; S.view = "dashboard"; render(); window.scrollTo(0, 0);
  } else if (f === "chat") {
    const i = document.getElementById("cq"); if (i.value.trim()) ask(i.value.trim());
  }
});

// Deep links: #login, #signup, #onboarding, or a page name such as #dashboard
const h = location.hash.slice(1);
if (["login", "signup", "onboarding"].includes(h)) S.screen = h;
else if (PAGES[h]) { S.screen = "app"; S.view = h; S.onboarded = true; }
render();
