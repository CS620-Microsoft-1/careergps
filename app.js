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
  ["opps", "case", "Opportunities"], ["plan", "list", "Action Plan"], ["projects", "code", "Projects"]
];
const ROLES = ["Software Engineer", "Data Analyst", "AI Engineer"];

const S = {
  screen: "login",          // login | signup | onboarding | app
  view: "dashboard",
  menu: false,
  copilot: false,
  chat: [],
  marketRole: "AI Engineer",
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
const priTag = p => `<span class="tag ${p === "High" ? "red" : p === "Medium" ? "amber" : ""}">${p} Priority</span>`;
const initials = n => n.split(/\s+/).filter(Boolean).map(w => w[0]).join("").slice(0, 2).toUpperCase();
function toast(m) { const t = document.createElement("div"); t.className = "toast"; t.textContent = m; document.body.appendChild(t); setTimeout(() => t.remove(), 2200); }

/* ---------- AUTH ---------- */
const logo = () => `<div class="logo"><i>${I.target(24)}</i>CareerGPS</div>`;
function authLeft() {
  const steps = ["Your Profile", "Job Market", "Skill Gaps", "Action Plan"];
  return `<div class="auth-left">
    ${logo()}
    <div class="intro">
      <p class="tagline">Your AI-powered career intelligence platform</p>
      <blockquote>"Understand where you stand, what employers are looking for, and what you should do next to become a stronger candidate."</blockquote>
    </div>
    <div class="steps">${steps.map((t, i) => `<span class="step"><em>${i + 1}</em>${t}</span>${i < 3 ? "<b>›</b>" : ""}`).join("")}</div>
    <ul class="perks">
      <li><i>${I.check(18)}</i>Understand your career readiness</li>
      <li><i>${I.bars(18)}</i>Discover high-priority skill gaps</li>
      <li><i>${I.list(18)}</i>Get personalized projects, courses, and action plans</li>
    </ul>
    <div class="rd"><div class="top"><span>Career Readiness</span><b>72%</b></div><div class="pbar"><div></div></div>
      <div class="chips"><span class="ok">Python ✓</span><span>Docker ○</span><span>CI/CD ○</span></div></div>
  </div>`;
}
const uwBtn = () => `<button type="button" class="btn sso" data-a="sso"><span class="uw">UW</span>Continue with UW–Madison</button>`;
function loginView() {
  return `<div class="auth">${authLeft()}<div class="auth-right"><form class="auth-card" data-form="login">
    <h2>Welcome back</h2><p class="sub">Sign in to continue your career journey.</p>
    <div class="field"><label for="em">Email</label><input id="em" type="email" placeholder="student@wisc.edu" required></div>
    <div class="field"><label for="pw">Password</label><input id="pw" type="password" placeholder="Enter your password" required></div>
    <div class="between"><label class="check"><input type="checkbox"> Remember me</label><button type="button" class="linkbtn" data-a="toast" data-m="Password reset link sent (demo)">Forgot password?</button></div>
    <button class="btn primary block" type="submit">Sign In</button>
    <div class="divider">or</div>
    <div class="social">
      <button type="button" class="btn" data-a="sso">${GOOGLE}Continue with Google</button>
      <button type="button" class="btn" data-a="sso">${MSFT}Continue with Microsoft</button>
    </div>
    <p class="sso-l">UNIVERSITY SINGLE SIGN-ON</p>${uwBtn()}
    <p class="switch">Don't have an account? <button type="button" class="linkbtn" data-a="screen" data-s="signup">Create Account</button></p>
  </form></div></div>`;
}
function signupView() {
  const y = new Date().getFullYear();
  return `<div class="auth">${authLeft()}<div class="auth-right"><form class="auth-card" data-form="signup">
    <h2>Create your CareerGPS account</h2><p class="sub">Start building a stronger candidate profile.</p>
    <div class="field"><label for="n">Full Name</label><input id="n" placeholder="Alex Johnson" required></div>
    <div class="field"><label for="ue">University Email</label><input id="ue" type="email" placeholder="student@wisc.edu" required></div>
    <div class="row2">
      <div class="field"><label for="p1">Password</label><input id="p1" type="password" required minlength="6"></div>
      <div class="field"><label for="p2">Confirm Password</label><input id="p2" type="password" required></div>
    </div>
    <div class="row2">
      <div class="field"><label for="gy">Graduation Year</label><select id="gy">${[0, 1, 2, 3, 4].map(i => `<option ${i === 1 ? "selected" : ""}>${y + i}</option>`).join("")}</select></div>
      <div class="field"><label for="tr">Target Role</label><select id="tr">${ROLES.map(r => `<option ${r === "AI Engineer" ? "selected" : ""}>${r}</option>`).join("")}</select></div>
    </div>
    <div class="field"><label for="un">University</label><input id="un" value="University of Wisconsin–Madison"></div>
    <div class="field"><span class="lbl">Experience Level</span><div class="seg"><label><input type="radio" name="lvl" value="Internship">Internship</label><label><input type="radio" name="lvl" value="Full-time" checked>Full-time</label></div></div>
    <label class="check" style="margin-bottom:8px"><input type="checkbox" id="terms"> <span>I agree to the <a href="#" data-a="toast" data-m="Terms (demo)">Terms of Service</a> and <a href="#" data-a="toast" data-m="Privacy Policy (demo)">Privacy Policy</a>.</span></label>
    <div class="err" id="err"></div>
    <button class="btn primary block" type="submit">Create Account</button>
    <p class="sso-l">UNIVERSITY SINGLE SIGN-ON</p>${uwBtn()}
    <p class="switch">Already have an account? <button type="button" class="linkbtn" data-a="screen" data-s="login">Sign In</button></p>
  </form></div></div>`;
}

/* ---------- ONBOARDING ---------- */
function onboardingView() {
  const s = D.student, y = new Date().getFullYear();
  return `<div class="auth"><div class="auth-left onb-left">
    ${logo()}
    <span class="pill-badge">Career goal setup</span>
    <h1 class="big-h">Where do you want your career to go?</h1>
    <p class="lead">Tell us where you're headed. We'll compare your experience against real labor-market data and map the clearest path forward.</p>
    <ul class="checks-l">
      <li><i>${I.check(16)}</i>Understand what you already demonstrate</li>
      <li><i>${I.check(16)}</i>See what employers are asking for</li>
      <li><i>${I.check(16)}</i>Turn skill gaps into concrete next steps</li>
    </ul>
  </div><div class="auth-right"><form class="auth-card" data-form="onboard">
    <div class="field"><label for="o1">Target Role</label><select id="o1">${ROLES.map(r => `<option ${r === s.role ? "selected" : ""}>${r}</option>`).join("")}</select></div>
    <div class="row2">
      <div class="field"><label for="o2">Graduation Year</label><select id="o2">${[0, 1, 2, 3, 4].map(i => `<option ${String(y + i) === s.gradYear ? "selected" : ""}>${y + i}</option>`).join("")}</select></div>
      <div class="field"><label for="o3">Preferred Location</label><input id="o3" value="${esc(s.location)}" placeholder="United States"></div>
    </div>
    <div class="field"><span class="lbl">Experience Level</span><div class="seg">${["Internship", "Full-time"].map(l => `<label><input type="radio" name="lvl2" value="${l}" ${l === s.level ? "checked" : ""}>${l}</label>`).join("")}</div></div>
    <div class="field"><label class="upload ${S.resume ? "done" : ""}" id="up">${I.up(24)}<b id="upt">${S.resume ? "✓ " + esc(S.resume) : "Upload your résumé"}</b><small>PDF or DOCX · up to 10 MB</small><input type="file" id="resume" accept=".pdf,.doc,.docx" hidden></label></div>
    <button class="btn primary block" type="submit">Analyze My Career Profile ${I.chev()}</button>
    <p class="hint">CareerGPS compares your experience against real labor-market data to identify what you demonstrate, what employers want, and what to work on next.</p>
  </form></div></div>`;
}

/* ---------- SHELL ---------- */
function shell(body) {
  const s = D.student;
  return `<div class="shell">
    <aside class="side">${logo()}
      <nav class="nav">${NAV.map(n => `<button class="${S.view === n[0] ? "on" : ""}" data-a="nav" data-v="${n[0]}">${I[n[1]](22)}${n[2]}${n[3] ? `<span class="badge">${n[3]}</span>` : ""}</button>`).join("")}</nav>
      <div class="strength"><div class="r"><span>Profile strength</span><b>72%</b></div><div class="pbar"><div></div></div>
        <p>Upload your latest résumé to improve your analysis.</p><button class="linkbtn" data-a="nav" data-v="profile">Complete profile ${I.chev()}</button></div>
      <div class="help"><i>?</i><div><b>Need help?</b><small>Visit the student guide</small></div></div>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="search">${I.search(20)}<span>Search CareerGPS</span><kbd>⌘ K</kbd></div>
        <button class="iconbtn" aria-label="Notifications" data-a="toast" data-m="You're all caught up">${I.bell(22)}<span class="dot"></span></button>
        <button class="iconbtn" aria-label="Settings" data-a="toast" data-m="Settings (demo)">${I.gear(22)}</button>
        <button class="userbtn ${S.view === "profile" ? "on" : ""}" data-a="usermenu" aria-label="Student menu"><span class="avatar">${initials(s.name)}</span><span class="who-t"><b>${esc(s.name)}</b><small>UW–Madison · ${esc(s.gradYear)}</small></span></button>
        ${S.menu ? `<div class="pop"><div class="who">${esc(s.email)}</div><button data-a="nav" data-v="profile">${I.user(18)}My Profile</button><button data-a="screen" data-s="login">${I.swap(18)}Switch Account</button><button data-a="screen" data-s="login">${I.out(18)}Sign Out</button></div>` : ""}
      </header>
      <div class="mobile-nav">${NAV.map(n => `<button class="${S.view === n[0] ? "on" : ""}" data-a="nav" data-v="${n[0]}">${n[2]}</button>`).join("")}</div>
      <div class="page">${body}</div>
    </div>
  </div>
  <button class="fab" data-a="copilot">${I.spark(20)}Ask CareerGPS</button>`;
}
const head = (tag, t, p) => `<div class="page-h">${tag ? `<span class="etag">${tag}</span>` : ""}<h1>${t}</h1>${p ? `<p>${p}</p>` : ""}</div>`;
const secHead = (icon, t, sub, link) => `<div class="sec-h"><span class="chip-i">${I[icon](22)}</span><div><h2>${t}</h2><small>${sub}</small></div>${link ? `<button class="linkbtn" data-a="toast" data-m="${link} (demo)">${link} ${I.chev()}</button>` : ""}</div>`;

/* ---------- PAGES ---------- */
function ring(p) { return `<div class="ring" style="--p:${p}"><div><div><b>${p}%</b><small>Ready</small></div></div></div>`; }
function readinessCard() {
  const r = D.readiness;
  return `<div class="card"><div class="card-h"><div><h3>${esc(D.student.role)} Career Readiness</h3><p class="desc">Based on your evidence and 64 current job postings</p></div><span class="tag brand">Last analyzed: Today</span></div>
    <div class="readiness">${ring(r.overall)}<div class="bars">
      ${r.cats.map(c => `<div class="row"><div class="t"><span>${c[0]}</span><b>${c[1]}%</b></div><div class="track"><div class="fill ${c[1] < 60 ? "warn" : ""}" style="width:${c[1]}%"></div></div></div>`).join("")}
    </div></div>
    <p class="desc" style="margin-bottom:16px">You demonstrate strong software engineering and AI experience, but your profile currently has limited evidence of production infrastructure and deployment skills.</p>
    <button class="btn" data-a="reanalyze">Run Analysis Again</button></div>`;
}
function priorityCard() {
  return `<div class="card"><div class="card-h"><div><h3>Priority Skill Gaps</h3><p class="desc">Ranked by career impact</p></div><button class="linkbtn" data-a="nav" data-v="gaps">View all ${I.chev()}</button></div>
    <div style="margin-top:14px">${D.gaps.slice(0, 4).map((g, i) => `<div class="prow"><span class="n">${i + 1}</span><div><b>${g.skill}</b><small>${g.demand}% market demand · ${g.evidence === "No demonstrated experience" ? "No evidence" : g.evidence}</small></div><span class="tag ${g.pri === "High" ? "red" : "amber"}">${g.pri}</span></div>`).join("")}</div></div>`;
}
function agentCard() {
  return `<div class="card"><h3>How CareerGPS Generated This Analysis</h3><p class="desc">Four agents worked in sequence, and every step is inspectable.</p>
    <div class="agents"><span class="agent">Student Profile Agent</span><span class="arr">→</span><span class="agent">Market Intelligence Agent</span><span class="arr">→</span><span class="agent">Gap Analysis Agent</span><span class="arr">→</span><span class="agent">Action Agent</span></div>
    <ul class="checks"><li>Resume analyzed</li><li>64 relevant jobs retrieved</li><li>21 recurring skills identified</li><li>Student evidence compared</li><li>3 high-priority gaps detected</li><li>Personalized roadmap generated</li></ul>
    <button class="btn sm" data-a="details">View Analysis Details</button></div>`;
}
function dashboard() {
  const s = D.student, today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  return `<div class="dash-h"><div class="page-h"><p class="eyebrow">${today}</p><h1>Good morning, ${esc(s.first)}</h1><p>Here's how your profile compares with the current ${esc(s.role)} job market.</p></div>
    <div class="goal"><div><small>CAREER GOAL</small><b>${esc(s.role)} • ${s.level === "Internship" ? "Internship" : "New Grad"} ${esc(s.gradYear)}</b></div><button class="btn" data-a="screen" data-s="onboarding">Edit</button></div></div>
  <div class="grid g4">
    <div class="card stat"><div class="hd"><span class="k">Career Readiness</span><span class="chip-i ci-g">${I.target(22)}</span></div><div class="num">72%</div><div class="s">Overall readiness for ${esc(s.role)} roles</div><span class="ft">${I.arrowUp()} 6% since last analysis</span></div>
    <div class="card stat"><div class="hd"><span class="k">Jobs Analyzed</span><span class="chip-i ci-b">${I.case(22)}</span></div><div class="num">64</div><div class="s">Relevant entry-level positions</div><button class="ft muted" data-a="nav" data-v="analysis">Updated today ${I.chev()}</button></div>
    <div class="card stat"><div class="hd"><span class="k">High-Priority Skill Gaps</span><span class="chip-i ci-a">${I.bars(22)}</span></div><div class="num">3</div><div style="margin-top:10px">${tags(["Docker", "CI/CD", "Vector DBs"], "amber")}</div><button class="ft muted" data-a="nav" data-v="gaps">View all gaps ${I.chev()}</button></div>
    <div class="card stat dark"><div class="hd"><span class="k">Recommended Next Action</span><span class="chip-i">${I.spark(22)}</span></div><div class="big-t">Build a production-ready RAG application</div><div class="s">Addresses 3 high-priority gaps</div><button class="btn" data-a="nav" data-v="plan">View Action Plan ${I.chev()}</button></div>
  </div>
  <div class="grid g21" style="margin-top:24px;align-items:start">${readinessCard()}${priorityCard()}</div>
  <div style="margin-top:24px">${agentCard()}</div>`;
}

function analysis() {
  return head("Market intelligence", "What Employers Are Looking For", "Based on 64 entry-level AI / ML engineering positions.") +
  `<div class="filters">
    <select aria-label="Role" data-a="role">${ROLES.map(r => `<option ${r === S.marketRole ? "selected" : ""}>Role: ${r}</option>`).join("")}</select>
    <select aria-label="Experience"><option>Experience: New Graduate / Entry Level</option></select>
    <select aria-label="Location"><option>Location: United States</option></select>
    <select aria-label="Posting date"><option>Posting Date: Last 90 Days</option></select>
  </div>
  <div class="grid g21" style="align-items:start">
    <div class="card"><h3>Skill demand</h3><p class="desc">Share of analyzed postings that mention each skill.</p><div class="bars" style="margin-top:22px">
      ${D.market.map(m => `<div class="row"><div class="t"><span>${m[0]}</span><b>${m[1]}%</b></div><div class="track"><div class="fill" style="width:${m[1]}%"></div></div></div>`).join("")}</div>
      ${cites(["Job 12", "Job 24", "Job 31", "O*NET"])}</div>
    <div class="card"><h3>Common Responsibilities</h3><p class="desc">Recurring across retrieved postings</p><ul class="resp">${D.responsibilities.map(r => `<li>${r}</li>`).join("")}</ul>
      <p class="desc">Market insights generated from retrieved job postings and occupational data.</p>${cites(["Job 18", "Job 40", "O*NET"])}</div>
  </div>
  <div class="grid g21" style="margin-top:24px;align-items:start">${readinessCard()}${agentCard()}</div>`;
}

function profile() {
  const s = D.student;
  const col = (title, cls, ic, list, key) => `<div class="card"><div class="col-h"><span class="ic ${cls}">${ic}</span>${title}</div>
    ${list.map((k, i) => { const id = key + i, open = S.evidenceOpen[id]; return `<div class="sk"><span class="ic ${cls}">${ic}</span><span>${k[0]}</span><button class="linkbtn" style="font-size:13px" data-a="evidence" data-id="${id}">${open ? "Hide" : "View Evidence"}</button></div>
      ${open ? `<div class="evid">“${esc(k[1])}”<div class="cites" style="margin-top:6px">${k[2].map(cite).join("")}</div></div>` : ""}`; }).join("")}</div>`;
  return head("Evidence-based", "Your Career Profile", "Your account details and the evidence CareerGPS extracted from your résumé.") +
  `<div class="card" style="display:flex;gap:22px;align-items:center;flex-wrap:wrap;margin-bottom:24px"><div class="avatar lg">${initials(s.name)}</div>
    <div style="flex:1;min-width:220px"><h3>${esc(s.name)}</h3><p class="desc">${esc(s.email)} · ${esc(s.university)}</p>
    <div class="tags" style="margin-top:10px"><span class="tag brand">${esc(s.role)}</span><span class="tag">Class of ${esc(s.gradYear)}</span><span class="tag">${esc(s.level)}</span><span class="tag">${esc(s.location)}</span></div></div>
    <button class="btn" data-a="screen" data-s="onboarding">Update Résumé</button></div>
  <div class="callout">${I.spark(22)}<div><b>Evidence, not keywords.</b>CareerGPS evaluates demonstrated evidence, not simply whether a keyword appears on your résumé.</div></div>
  <div class="grid g3" style="align-items:start">
    ${col("Strong", "g", "✓", D.skills.strong, "s")}${col("Some Experience", "y", "•", D.skills.some, "m")}${col("No Demonstrated Experience", "n", "✕", D.skills.none, "n")}
  </div>`;
}

function gaps() {
  return head("3 high priority", "Your Skill Gaps", "CareerGPS prioritizes gaps based on market demand and your demonstrated experience.") +
  `<div class="callout">${I.spark(22)}<div><b>Not every missing skill matters equally.</b>Priority combines employer demand, role relevance, prerequisites, and evidence already in your profile.</div></div>
  <div class="grid g2">${D.gaps.map(g => `<div class="card"><div class="gap-top">${priTag(g.pri)}${cite(g.cites[0])}</div>
    <h3 class="gap-title">${g.skill}</h3>
    <div class="cols2"><div><small>Market demand</small><div class="v">${g.demand}%</div><div class="track"><div class="fill" style="width:${g.demand}%"></div></div></div>
      <div><small>Your evidence</small><div class="e ${g.evidence === "Some experience" ? "some" : ""}">${g.evidence}</div></div></div>
    <p class="desc">${g.why}</p>
    <div class="reco"><small>Recommended action</small>${g.action}</div>
    <button class="btn" data-a="addgap" data-s="${esc(g.skill)}">Add to Action Plan ${I.chev()}</button></div>`).join("")}</div>`;
}

function plan() {
  const total = totalTasks(), done = S.done.size, pct = Math.round(done / total * 100);
  return head("Personalized roadmap", "Your Career Action Plan", "A focused roadmap built from your highest-impact career gaps.") +
  `<div class="hero"><div><span class="tag violet">Highest-Impact Next Step</span><h2>Build a Production-Ready RAG Application</h2>
    <p>This project addresses three important gaps in your current profile: Docker, vector databases, and CI/CD.</p>
    ${tags(["Docker", "Vector Database", "CI/CD", "RAG", "Cloud Deployment"])}</div>
    <div class="cnt"><b>${done}</b> <span>/ ${total}</span><p>tasks completed</p><div class="track"><div class="fill" style="width:${pct}%"></div></div></div></div>
  <div class="grid g5 weeks">${D.weeks.map((w, wi) => {
    const n = w[1].filter((_, ti) => S.done.has(wi + "-" + ti)).length;
    const st = n === w[1].length ? '<span class="tag green">Done</span>' : n > 0 ? '<span class="tag brand">In progress</span>' : `<span class="tag">Week ${wi + 1}</span>`;
    return `<div class="card"><div class="wk-h">${st}<span class="num-c">${wi + 1}</span></div><h3 class="wk-t">${w[0]}</h3>
    ${w[1].map((t, ti) => { const k = wi + "-" + ti, d = S.done.has(k); return `<label class="task ${d ? "done" : ""}"><input type="checkbox" data-a="task" data-k="${k}" ${d ? "checked" : ""}><span>${t}</span></label>`; }).join("")}</div>`; }).join("")}</div>
  <div class="card cta-bar"><div><b>Ready to start building?</b><small>Your project can be synced with GitHub.</small></div>
    <div style="display:flex;gap:10px"><button class="btn" data-a="toast" data-m="GitHub issues created (demo)">Create GitHub Issues ${I.chev()}</button><button class="btn primary" data-a="toast" data-m="Project started. Good luck!">Start Project</button></div></div>`;
}

function projects() {
  const colors = ["#2f5f59", "#56657a", "#7a6a55", "#665a7a"], icons = ["spark", "code", "bars", "search"];
  const gapTag = p => { const n = parseInt(p.impact.match(/\d+/)); return `<span class="tag ${n >= 2 ? "red" : "brand"}">${n} high-priority gap${n > 1 ? "s" : ""}</span>`; };
  return head("Built for your goal", "Projects Worth Building", "Every recommendation is tied to the career gaps it helps you close.") +
  `<div class="banner"><div><span class="tag violet">Top recommendation</span><h2>Build evidence employers can see.</h2><p class="p">The best next project is not the trendiest. It's the one that adds credible evidence where your profile needs it most.</p></div>
    <div class="plus"><b>+11</b><small>estimated readiness points</small></div></div>
  <div class="grid g2">${D.projects.map((p, i) => `<div class="card proj"><div class="pl" style="background:${colors[i]}">${I[icons[i]](30)}<span>0${i + 1}</span></div>
    <div class="pr">${gapTag(p)}<h3>${p.name}</h3><p class="mini-l" style="margin-bottom:8px">Skills demonstrated</p>${tags(p.skills)}
      <div class="meta"><div>Estimated duration<b>${p.weeks} weeks</b></div><div>Difficulty<b>${p.diff}</b></div></div>
      <button class="btn" data-a="roadmap" data-n="${esc(p.name)}">Generate Project Roadmap ${I.chev()}</button></div></div>`).join("")}</div>`;
}

function opps() {
  const course = c => { const [code, name] = c[0].split(" — "); return `<div class="card ccard"><span><span class="tag red">${code}</span></span><h3>${name}</h3><p class="desc">${c[1]}</p>
    <div class="tags"><span class="tag">Spring 2027</span><span class="tag">3 credits</span></div><button class="linkbtn lk" data-a="toast" data-m="Opening ${code} in the course guide (demo)">View course ${I.chev()}</button></div>`; };
  const club = c => `<div class="card ccard"><span class="init">${initials(c.name)}</span><h3>${c.name}</h3>
    <div><p class="mini-l">Skills you can develop</p><p style="font-size:14px">${c.skills.join(" · ")}</p></div>
    <div><p class="mini-l">Upcoming</p><p style="font-size:14px">${c.event}</p></div>
    <p class="desc"><b style="color:var(--ink)">Why CareerGPS recommends it:</b> ${c.why}</p></div>`;
  const hack = h => `<div class="card row-c"><div><span class="tag ${h.status === "Open" ? "green" : "amber"}">${h.status}</span><h4>${h.title}</h4><small>${h.name} · Team of ${h.team} · ${h.skills.join(" · ")}</small></div><span class="d">${h.date}</span></div>`;
  const learn = l => `<div class="card row-c"><div><h4 style="margin-top:0">${l[0]}</h4><small>${l[1]} · Recommended because ${l[2]} is ${D.gaps.some(g => g.skill === l[2] && g.pri === "High") ? "one of your highest-priority gaps" : "worth strengthening"}</small></div><span class="cite">[Free]</span></div>`;
  return head("UW–Madison", "Opportunities Around You", "Courses, communities, and experiences that can turn your gaps into demonstrated skills.") +
  secHead("book", "Recommended Courses", "Available through your university catalog", "View course catalog") +
  `<div class="grid g3">${D.courses.map(course).join("")}</div>` +
  secHead("bank", "Clubs &amp; Student Organizations", "Build with peers and create evidence outside the classroom") +
  `<div class="grid g4">${D.clubs.map(club).join("")}</div>
  <div class="grid g2" style="align-items:start"><div>${secHead("spark", "Hackathons &amp; Competitions", "Practice under real constraints")}${D.hacks.map(hack).join("")}</div>
    <div>${secHead("book", "Free Learning Resources", "Mapped to your gaps")}${D.learning.map(learn).join("")}</div></div>`;
}

const PAGES = { dashboard, analysis, profile, gaps, plan, projects, opps };

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

render();
