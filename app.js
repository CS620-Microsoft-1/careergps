const D = DATA;
const $app = document.getElementById("app");
const $drawer = document.getElementById("drawer-root");

const NAV = [
  ["dashboard", "▦", "Dashboard"], ["analysis", "◎", "Career Analysis"], ["gaps", "△", "Skill Gaps"],
  ["opps", "✦", "Opportunities"], ["plan", "☑", "Action Plan"], ["projects", "⌘", "Projects"]
];
const ROLES = ["Software Engineer", "Data Analyst", "AI Engineer"];

const S = {
  screen: "login",          // login | signup | onboarding | analyzing | app
  view: "dashboard",
  menu: false,
  copilot: false,
  chat: [],
  oppTab: "courses",
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
const barCls = v => v < 40 ? "bad" : v < 60 ? "warn" : "";
function toast(m) { const t = document.createElement("div"); t.className = "toast"; t.textContent = m; document.body.appendChild(t); setTimeout(() => t.remove(), 2200); }

/* ---------- AUTH ---------- */
function authLeft() {
  return `<div class="auth-left">
    <div class="logo"><i>➤</i>CareerGPS</div>
    <h1>Know where you stand.<br>Know what to do next.</h1>
    <p class="sub">Your AI-powered career intelligence platform.</p>
  </div>`;
}
function loginView() {
  return `<div class="auth">${authLeft()}<div class="auth-right"><form class="auth-card" data-form="login">
    <h2>Welcome back</h2><p class="sub">Sign in to continue your career journey.</p>
    <div class="field"><label for="em">Email</label><input id="em" type="email" placeholder="student@wisc.edu" required></div>
    <div class="field"><label for="pw">Password</label><input id="pw" type="password" placeholder="Enter your password" required></div>
    <div class="between"><label class="check"><input type="checkbox"> Remember me</label><button type="button" class="linkbtn" data-a="toast" data-m="Password reset link sent (demo)">Forgot password?</button></div>
    <button class="btn primary block" type="submit">Sign In</button>
    <div class="divider">or</div>
    <div class="social">
      <button type="button" class="btn" data-a="sso">Continue with Google</button>
      <button type="button" class="btn" data-a="sso">Continue with Microsoft</button>
      <button type="button" class="btn" data-a="sso">🎓 Continue with UW–Madison</button>
    </div>
    <p class="switch">Don't have an account? <button type="button" class="linkbtn" data-a="screen" data-s="signup">Create Account</button></p>
  </form></div></div>`;
}
function signupView() {
  const y = new Date().getFullYear();
  return `<div class="auth">${authLeft()}<div class="auth-right"><form class="auth-card" data-form="signup">
    <h2>Create your CareerGPS account</h2><p class="sub">Start building a stronger candidate profile.</p>
    <div class="field"><label for="n">Full Name</label><input id="n" required></div>
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
    <div class="divider">or</div>
    <button type="button" class="btn block" data-a="sso">🎓 Continue with UW–Madison</button>
    <p class="switch">Already have an account? <button type="button" class="linkbtn" data-a="screen" data-s="login">Sign In</button></p>
  </form></div></div>`;
}

/* ---------- ONBOARDING ---------- */
function onboardingView() {
  const s = D.student;
  return `<div class="center-page"><form class="onb" data-form="onboard">
    <div class="logo" style="margin-bottom:18px"><i style="background:var(--brand);color:#fff">➤</i>CareerGPS</div>
    <h1>Where do you want your career to go?</h1>
    <p class="desc" style="color:var(--muted);margin-bottom:20px">Tell us your goal and we'll build your personalized analysis.</p>
    <div class="field"><label for="o1">Target Role</label><select id="o1">${ROLES.map(r => `<option ${r === s.role ? "selected" : ""}>${r}</option>`).join("")}</select></div>
    <div class="row2">
      <div class="field"><label for="o2">Graduation Year</label><input id="o2" value="${s.gradYear}" placeholder="2027"></div>
      <div class="field"><label for="o3">Preferred Location</label><input id="o3" value="${s.location}" placeholder="United States"></div>
    </div>
    <div class="field"><span class="lbl">Experience Level</span><div class="seg"><label><input type="radio" name="lvl2" value="Internship">Internship</label><label><input type="radio" name="lvl2" value="Full-time" checked>Full-time</label></div></div>
    <div class="field"><span class="lbl">Upload Résumé</span>
      <label class="upload ${S.resume ? "done" : ""}" id="up">${S.resume ? "✓ " + esc(S.resume) : "Click to upload your résumé (PDF or DOCX)"}<input type="file" id="resume" accept=".pdf,.doc,.docx" hidden></label></div>
    <div class="field"><label for="o4">Add coursework <span style="color:var(--muted);font-weight:400">(optional)</span></label><textarea id="o4" rows="2" placeholder="CS 540, CS 544, STAT 324…"></textarea></div>
    <div class="field"><label for="o5">Add projects <span style="color:var(--muted);font-weight:400">(optional)</span></label><textarea id="o5" rows="2" placeholder="Describe a project you've built…"></textarea></div>
    <div class="note">CareerGPS compares your experience against real labor-market data to identify what you already demonstrate, what employers are looking for, and what you should work on next.</div>
    <button class="btn primary block" type="submit">Analyze My Career Profile</button>
  </form></div>`;
}
function analyzingView() {
  const steps = ["Resume analyzed", "64 relevant jobs retrieved", "21 recurring skills identified", "Student evidence compared", "3 high-priority gaps detected", "Personalized roadmap generated"];
  return `<div class="center-page"><div class="onb"><h1>Analyzing your career profile…</h1><p style="color:var(--muted)">Four agents are working on your results.</p>
  <ul class="analyzing">${steps.map((t, i) => `<li id="st${i}">${t}</li>`).join("")}</ul></div></div>`;
}
function runAnalyzing(next) {
  S.screen = "analyzing"; render();
  for (let i = 0; i < 6; i++) setTimeout(() => { const el = document.getElementById("st" + i); if (el) el.classList.add("on"); }, 350 * (i + 1));
  setTimeout(() => { S.onboarded = true; S.screen = "app"; S.view = "dashboard"; render(); }, 350 * 7 + 200);
}

/* ---------- SHELL ---------- */
function shell(body) {
  const s = D.student;
  return `<div class="shell">
    <aside class="side"><div class="logo"><i>➤</i>CareerGPS</div>
      <nav class="nav">${NAV.map(n => `<button class="${S.view === n[0] ? "on" : ""}" data-a="nav" data-v="${n[0]}"><span>${n[1]}</span>${n[2]}</button>`).join("")}</nav>
      <div class="loop"><b>The loop:</b><br>Profile → Market → Skill Gaps → Action → New Experience → Updated Profile</div>
    </aside>
    <div class="main">
      <header class="topbar">
        <button class="iconbtn" aria-label="Notifications" data-a="toast" data-m="You're all caught up">🔔<span class="dot"></span></button>
        <button class="iconbtn" aria-label="Settings" data-a="toast" data-m="Settings (demo)">⚙</button>
        <button class="userbtn ${S.view === "profile" ? "on" : ""}" data-a="usermenu" aria-label="Student menu"><span class="avatar">AJ</span><span style="text-align:left;font-size:13px;line-height:1.2"><b>${s.name}</b><br><span style="color:var(--muted)">${s.role} track</span></span></button>
        ${S.menu ? `<div class="pop"><div class="who">${s.email}</div><button data-a="nav" data-v="profile">👤 My Profile</button><button data-a="screen" data-s="login">⇄ Switch Account</button><button data-a="screen" data-s="login">⏻ Sign Out</button></div>` : ""}
      </header>
      <div class="mobile-nav">${NAV.map(n => `<button class="pill ${S.view === n[0] ? "on" : ""}" data-a="nav" data-v="${n[0]}">${n[2]}</button>`).join("")}</div>
      <div class="page">${body}</div>
    </div>
  </div>
  <button class="fab" data-a="copilot">✦ Copilot</button>`;
}
const head = (t, p) => `<div class="page-h"><h1>${t}</h1>${p ? `<p>${p}</p>` : ""}</div>`;

/* ---------- PAGES ---------- */
function ring(p) { return `<div class="ring" style="--p:${p}"><div><div><b>${p}%</b><small>ready</small></div></div></div>`; }
function readinessCard() {
  const r = D.readiness;
  return `<div class="card"><h3>AI Engineer Career Readiness</h3><p class="desc">Last analyzed: Today</p>
    <div class="readiness" style="margin-top:16px">${ring(r.overall)}<div>
      ${r.cats.map(c => `<div class="bar"><span>${c[0]}</span><div class="track"><div class="fill ${barCls(c[1])}" style="width:${c[1]}%"></div></div><b>${c[1]}%</b></div>`).join("")}
    </div></div>
    <div class="callout" style="margin:16px 0">You demonstrate strong software engineering and AI experience, but your profile currently has limited evidence of production infrastructure and deployment skills.</div>
    <button class="btn" data-a="reanalyze">Run Analysis Again</button></div>`;
}
function agentCard() {
  return `<div class="card"><h3>How CareerGPS Generated This Analysis</h3><p class="desc">Four agents worked in sequence, and every step is inspectable.</p>
    <div class="agents"><span class="agent">Student Profile Agent</span><span class="arr">↓</span><span class="agent">Market Intelligence Agent</span><span class="arr">↓</span><span class="agent">Gap Analysis Agent</span><span class="arr">↓</span><span class="agent">Action Agent</span></div>
    <ul class="checks"><li>Resume analyzed</li><li>64 relevant jobs retrieved</li><li>21 recurring skills identified</li><li>Student evidence compared</li><li>3 high-priority gaps detected</li><li>Personalized roadmap generated</li></ul>
    <button class="btn sm" data-a="details">View Analysis Details</button></div>`;
}
function dashboard() {
  return head(`Good morning, ${D.student.first}`, "Here's how your profile compares with the current AI engineering job market.") +
  `<p class="tag brand" style="margin:-10px 0 18px">AI Engineer — New Grad 2027</p>
  <div class="grid g4">
    <div class="card stat"><div class="k">Career Readiness</div><div class="num">72%</div><div class="s">Overall readiness for AI Engineer roles</div></div>
    <div class="card stat"><div class="k">Jobs Analyzed</div><div class="num">64</div><div class="s">Relevant entry-level positions</div></div>
    <div class="card stat"><div class="k">High-Priority Skill Gaps</div><div class="num">3</div>${tags(["Docker", "CI/CD", "Vector Databases"], "red")}</div>
    <div class="card stat"><div class="k">Recommended Next Action</div><div style="font-weight:700;margin:8px 0 12px">Build a production-ready RAG application</div><button class="btn primary sm" data-a="nav" data-v="plan">View Action Plan</button></div>
  </div>
  <div class="grid g2" style="margin-top:18px;align-items:start">${readinessCard()}<div class="stack">${agentCard()}
    <div class="card"><h3>Your feedback loop</h3><p class="desc" style="margin-bottom:10px">CareerGPS is a system for becoming a stronger candidate.</p>
    <div class="flow" style="color:var(--ink)"><span style="background:var(--brand-l)">Profile</span><b>→</b><span style="background:var(--brand-l)">Market</span><b>→</b><span style="background:var(--brand-l)">Skill Gaps</span><b>→</b><span style="background:var(--brand-l)">Action</span><b>→</b><span style="background:var(--brand-l)">New Experience</span><b>→</b><span style="background:var(--brand-l)">Updated Profile</span></div></div></div></div>`;
}

function analysis() {
  return head("Career Analysis", "How you compare with the market for AI Engineer roles.") +
  `<div class="grid g2" style="align-items:start">${readinessCard()}${agentCard()}</div>
  <h2 class="section-t">What Employers Are Looking For</h2>
  <p class="desc" style="color:var(--muted);margin:-8px 0 14px">Based on 64 entry-level AI / ML engineering positions.</p>
  <div class="filters">
    <select aria-label="Role" data-a="role">${ROLES.map(r => `<option ${r === S.marketRole ? "selected" : ""}>Role: ${r}</option>`).join("")}</select>
    <select aria-label="Experience"><option>Experience: New Graduate / Entry Level</option></select>
    <select aria-label="Location"><option>Location: United States</option></select>
    <select aria-label="Posting date"><option>Posting Date: Last 90 Days</option></select>
  </div>
  <div class="grid g2" style="align-items:start">
    <div class="card"><h3>Skill demand</h3><p class="desc">Share of analyzed postings that mention each skill.</p><div style="margin-top:8px">
      ${D.market.map(m => `<div class="bar"><span>${m[0]}</span><div class="track"><div class="fill" style="width:${m[1]}%"></div></div><b>${m[1]}%</b></div>`).join("")}</div>
      ${cites(["Job 12", "Job 24", "Job 31", "O*NET"])}</div>
    <div class="card"><h3>Common Responsibilities</h3><ul style="padding-left:18px;margin:10px 0">${D.responsibilities.map(r => `<li style="margin:6px 0">${r}</li>`).join("")}</ul>
      <div class="callout">Market insights generated from retrieved job postings and occupational data.</div>${cites(["Job 18", "Job 40", "O*NET"])}</div>
  </div>`;
}

function profile() {
  const s = D.student;
  const col = (title, cls, ic, list, key) => `<div class="card"><div class="col-h"><span class="ic ${cls}" style="width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:12px">${ic}</span>${title}</div>
    ${list.map((k, i) => { const id = key + i, open = S.evidenceOpen[id]; return `<div class="sk"><span class="ic ${cls}">${ic}</span><span>${k[0]}</span><button class="linkbtn" style="font-size:13px" data-a="evidence" data-id="${id}">${open ? "Hide" : "View Evidence"}</button></div>
      ${open ? `<div class="evid">“${esc(k[1])}”<div class="cites" style="margin-top:6px">${k[2].map(cite).join("")}</div></div>` : ""}`; }).join("")}</div>`;
  return head("Your Career Profile", "Your account details and the evidence CareerGPS extracted from your résumé.") +
  `<div class="card" style="display:flex;gap:20px;align-items:center;flex-wrap:wrap;margin-bottom:18px"><div class="avatar lg">AJ</div>
    <div style="flex:1;min-width:220px"><h3 style="font-size:20px">${s.name}</h3><p class="desc">${s.email} · ${s.university}</p>
    <div class="tags" style="margin-top:8px"><span class="tag brand">${s.role}</span><span class="tag">Class of ${s.gradYear}</span><span class="tag">${s.level}</span><span class="tag">${s.location}</span></div></div>
    <button class="btn" data-a="toast" data-m="Résumé replaced (demo)">Update Résumé</button></div>
  <div class="callout" style="margin-bottom:18px">CareerGPS evaluates <b>demonstrated evidence</b>, not simply whether a keyword appears on your résumé.</div>
  <div class="grid g3" style="align-items:start">
    ${col("Strong", "g", "✓", D.skills.strong, "s")}${col("Some Experience", "y", "•", D.skills.some, "m")}${col("No Demonstrated Experience", "n", "✕", D.skills.none, "n")}
  </div>`;
}

function gaps() {
  return head("Your Skill Gaps", "CareerGPS prioritizes gaps based on market demand and your demonstrated experience.") +
  `<div class="grid g2">${D.gaps.map(g => `<div class="card"><div class="gap-top">${priTag(g.pri)}</div>
    <h3 style="font-size:22px">${g.skill}</h3>
    <div class="kv"><b>Market Demand</b>${g.demand}% of postings</div><div class="track" style="margin:4px 0 8px"><div class="fill ${barCls(100 - g.demand * 1.6)}" style="width:${g.demand}%"></div></div>
    <div class="kv"><b>Your Evidence</b>${g.evidence}</div>
    <p class="desc" style="margin-top:10px">${g.why}</p>
    <div class="reco"><b>Recommended action:</b> ${g.action}</div>
    <button class="btn primary sm" data-a="addgap" data-s="${esc(g.skill)}">Add to Action Plan</button>${cites(g.cites)}</div>`).join("")}</div>`;
}

function plan() {
  const total = totalTasks(), done = S.done.size, pct = Math.round(done / total * 100);
  return head("Your Career Action Plan") +
  `<div class="hero"><span class="tag">Highest-Impact Next Step</span><h2>Build a Production-Ready RAG Application</h2>
    <p style="opacity:.9;max-width:640px">This project addresses three important gaps in your current profile: Docker, vector databases, and CI/CD.</p>
    <div class="tags" style="margin-top:14px">${["Docker", "Vector Database", "CI/CD", "RAG", "Cloud Deployment"].map(t => `<span class="tag">${t}</span>`).join("")}</div>
    <div style="margin-top:16px;max-width:420px"><b>${done} / ${total} tasks completed</b><div class="track" style="background:rgba(255,255,255,.25);margin-top:6px"><div class="fill" style="width:${pct}%;background:#fff"></div></div></div>
    <button class="btn primary" data-a="toast" data-m="GitHub issues created (demo)">Create GitHub Issues</button> <button class="btn" data-a="toast" data-m="Project started. Good luck!">Start Project</button></div>
  <h2 class="section-t">Five-week roadmap</h2>
  <div class="grid g2">${D.weeks.map((w, wi) => `<div class="card"><div class="wk-h"><h3>Week ${wi + 1}</h3><b>${w[1].filter((_, ti) => S.done.has(wi + "-" + ti)).length}/${w[1].length}</b></div><p style="font-weight:600;margin-bottom:8px">${w[0]}</p>
    ${w[1].map((t, ti) => { const k = wi + "-" + ti, d = S.done.has(k); return `<label class="task ${d ? "done" : ""}"><input type="checkbox" data-a="task" data-k="${k}" ${d ? "checked" : ""}><span>${t}</span></label>`; }).join("")}</div>`).join("")}</div>`;
}

function projects() {
  return head("Projects Worth Building", "Each project is chosen for the career gaps it closes.") +
  `<div class="grid g2">${D.projects.map(p => `<div class="card"><div class="gap-top"><h3 style="font-size:19px">${p.name}</h3>${p.best ? '<span class="tag green">Best fit</span>' : ""}</div>
    <p class="lbl" style="margin:10px 0 6px">Skills demonstrated</p>${tags(p.skills, "brand")}
    <div class="kv" style="margin-top:12px"><b>Career impact</b>${p.impact}</div><div class="kv"><b>Estimated duration</b>${p.weeks} weeks</div><div class="kv"><b>Difficulty</b>${p.diff}</div>
    <button class="btn primary sm" style="margin-top:12px" data-a="roadmap" data-n="${esc(p.name)}">Generate Project Roadmap</button></div>`).join("")}</div>`;
}

function opps() {
  const tabs = [["courses", "Courses"], ["clubs", "Clubs & Organizations"], ["hacks", "Hackathons & Competitions"], ["learning", "Free Learning"]];
  let body = "";
  if (S.oppTab === "courses") body = `<div class="grid g3">${D.courses.map(c => `<div class="card"><h3>${c[0]}</h3><p class="desc" style="margin:8px 0">${c[1]}</p>${tags(c[2], "brand")}</div>`).join("")}</div>`;
  if (S.oppTab === "clubs") body = `<div class="grid g2">${D.clubs.map(c => `<div class="card"><h3>${c.name}</h3>
    <p class="lbl" style="margin:10px 0 6px">Skills you can develop</p>${tags(c.skills, "brand")}
    <div class="kv" style="margin-top:10px"><b>Upcoming</b>${c.event}</div><p class="desc" style="margin-top:8px"><b>Why CareerGPS recommends it:</b> ${c.why}</p></div>`).join("")}</div>`;
  if (S.oppTab === "hacks") body = `<div class="grid g2">${D.hacks.map(h => `<div class="card"><div class="gap-top"><span class="tag">${h.name}</span><span class="tag ${h.status === "Open" ? "green" : "amber"}">${h.status}</span></div>
    <h3>${h.title}</h3><div class="kv"><b>Date</b>${h.date}</div><div class="kv"><b>Team size</b>${h.team}</div><div class="kv"><b>Skills practiced</b></div>${tags(h.skills, "brand")}
    <button class="btn sm" style="margin-top:12px" data-a="toast" data-m="Registration saved (demo)">Register</button></div>`).join("")}</div>`;
  if (S.oppTab === "learning") body = `<div class="grid g2">${D.learning.map(l => `<div class="card"><span class="tag">${l[0]}</span><h3 style="margin-top:8px">${l[1]}</h3>
    <p class="desc" style="margin:6px 0 10px">Recommended because ${l[2]} is ${D.gaps.some(g => g.skill === l[2] && g.pri === "High") ? "currently one of your highest-priority skill gaps" : "a skill area worth strengthening"}.</p>${tags([l[2]], "red")}</div>`).join("")}</div>`;
  return head("Opportunities Around You", "University and external experiences that can help you close your career gaps.") +
  `<div class="pill-row" style="margin-bottom:18px">${tabs.map(t => `<button class="pill ${S.oppTab === t[0] ? "on" : ""}" data-a="opptab" data-t="${t[0]}">${t[1]}</button>`).join("")}</div>${body}`;
}

const PAGES = { dashboard, analysis, profile, gaps, plan, projects, opps };

/* ---------- COPILOT & DRAWERS ---------- */
function copilotHTML() {
  return `<div class="overlay" data-a="closecopilot"></div><aside class="drawer" role="dialog" aria-label="CareerGPS Copilot">
    <header><h3>CareerGPS Copilot</h3><button class="iconbtn" data-a="closecopilot" aria-label="Close">✕</button></header>
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
  const s = D.sources[k]; if (!s) return;
  return `<div class="overlay" data-a="closedrawer"></div><aside class="drawer" role="dialog" aria-label="Source"><header><h3>Source · ${esc(k)}</h3><button class="iconbtn" data-a="closedrawer" aria-label="Close">✕</button></header>
    <div class="body"><div class="card"><span class="tag brand">${s.org}</span><h3 style="margin:10px 0 6px">${s.title}</h3><p class="desc">${s.text}</p></div>
    <p class="desc" style="color:var(--muted)">CareerGPS shows the evidence behind each recommendation so you can verify it.</p></div></aside>`;
}
function detailsDrawer() {
  return `<div class="overlay" data-a="closedrawer"></div><aside class="drawer" role="dialog" aria-label="Analysis details"><header><h3>Analysis Details</h3><button class="iconbtn" data-a="closedrawer" aria-label="Close">✕</button></header>
  <div class="body">${[["Student Profile Agent", "Extracted 10 skills from your résumé and rated each by demonstrated evidence."], ["Market Intelligence Agent", "Retrieved 64 entry-level postings from the last 90 days; found 21 recurring skills."], ["Gap Analysis Agent", "Compared demand with your evidence; ranked 3 gaps as high priority."], ["Action Agent", "Built a 5-week roadmap around one project that closes multiple gaps."]].map(a => `<div class="card"><h3>${a[0]}</h3><p class="desc">${a[1]}</p></div>`).join("")}</div></aside>`;
}
let drawerHTML = "";
function renderDrawer() { $drawer.innerHTML = S.copilot ? copilotHTML() : drawerHTML; }
function openDrawer(h) { S.copilot = false; drawerHTML = h; renderDrawer(); }

/* ---------- RENDER ---------- */
function render() {
  const sc = S.screen;
  $app.innerHTML = sc === "login" ? loginView() : sc === "signup" ? signupView() : sc === "onboarding" ? onboardingView() : sc === "analyzing" ? analyzingView() : shell(PAGES[S.view]());
  renderDrawer();
}

/* ---------- EVENTS ---------- */
document.addEventListener("click", e => {
  const el = e.target.closest("[data-a]");
  if (!el) { if (S.menu) { S.menu = false; render(); } return; }
  const a = el.dataset.a;
  if (a === "task") return;
  if (a === "role") return;
  if (a !== "usermenu" && S.menu) S.menu = false;
  switch (a) {
    case "screen": S.screen = el.dataset.s; S.menu = false; S.copilot = false; drawerHTML = ""; render(); break;
    case "sso": S.screen = "app"; S.view = "dashboard"; render(); break;
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
    case "opptab": S.oppTab = el.dataset.t; render(); break;
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
  else if (t.id === "resume" && t.files[0]) { S.resume = t.files[0].name; const up = document.getElementById("up"); up.classList.add("done"); up.firstChild.textContent = "✓ " + S.resume; }
});
document.addEventListener("submit", e => {
  e.preventDefault();
  const f = e.target.dataset.form;
  if (f === "login") { if (S.onboarded) { S.screen = "app"; S.view = "dashboard"; } else S.screen = "onboarding"; render(); }
  else if (f === "signup") {
    const err = document.getElementById("err");
    if (document.getElementById("p1").value !== document.getElementById("p2").value) return err.textContent = "Passwords don't match.";
    if (!document.getElementById("terms").checked) return err.textContent = "Please accept the Terms of Service and Privacy Policy.";
    Object.assign(D.student, { name: document.getElementById("n").value, first: document.getElementById("n").value.split(" ")[0], email: document.getElementById("ue").value,
      university: document.getElementById("un").value, gradYear: document.getElementById("gy").value, role: document.getElementById("tr").value,
      level: document.querySelector("input[name=lvl]:checked").value });
    S.screen = "onboarding"; render();
  } else if (f === "onboard") {
    Object.assign(D.student, { role: document.getElementById("o1").value, gradYear: document.getElementById("o2").value, location: document.getElementById("o3").value,
      level: document.querySelector("input[name=lvl2]:checked").value });
    runAnalyzing();
  } else if (f === "chat") {
    const i = document.getElementById("cq"); if (i.value.trim()) ask(i.value.trim());
  }
});

render();
