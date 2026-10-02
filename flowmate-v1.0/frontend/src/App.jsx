import React, { useEffect, useState } from "react";
import { api, setToken } from "./api.js";
import { useData } from "./ui.jsx";
import { Orders, Delivery, CashUp, Audit } from "./screens.jsx";
import { Dashboard, Invoices, Scan, Banking, Stock, Suppliers, DataPage, MfaSetup, Payments, GlobalSearch, Account } from "./screens3.jsx";
import { Customers, Products, Expenses, Members, Reports, Assistant, Users, Settings } from "./screens2.jsx";

// [name (used by links), component, permission needed, menu label, group]
const TABS = [["Dashboard", Dashboard, "reports", "Dashboard", ""],
  ["Orders", Orders, "orders", "Orders", "SALES"], ["Customers", Customers, "orders", "Customers", "SALES"], ["Members", Members, "memberships", "Members", "SALES"], ["Suppliers", Suppliers, "invoices", "Suppliers", "SUPPLY"], ["Products", Products, "stock_read", "Products", "SUPPLY"], ["Stock", Stock, "stock_read", "Inventory", "SUPPLY"],
  ["Invoices", Invoices, "invoices", "Invoices", "MONEY"], ["Expenses", Expenses, "expenses", "Expenses", "MONEY"], ["Banking", Banking, "banking_read", "Banking", "MONEY"], ["Payments", Payments, "banking_read", "Payments", "MONEY"], ["Cash-up", CashUp, "shifts", "Cash-up", "MONEY"],
  ["Delivery", Delivery, "delivery", "Logistics", "LOGISTICS"],
  ["Scan", Scan, "documents", "Documents", "INSIGHT"], ["Reports", Reports, "reports", "Reports", "INSIGHT"], ["Assistant", Assistant, "assistant_any", "AI Assist", "INSIGHT"],
  ["Settings", Settings, "users_dummy", "Settings", "ADMIN"], ["Users", Users, "users_dummy", "Users", "ADMIN"], ["Data", DataPage, "users_dummy", "Data & backups", "ADMIN"], ["Audit", Audit, "reports", "Audit", "ADMIN"], ["Account", Account, "", "My account", "ACCOUNT"]];
const OPTIONAL = ["Members", "Delivery"];   // shown only for business types that use them
const can = (user, area) => area === "" || user.perms.includes("*") || user.perms.includes(area) || (area === "assistant_any" && (user.perms.includes("assistant") || user.perms.includes("assistant_basic")));

export default function App() {
  const [menu, setMenu] = useState(false);
  const [demo, setDemo] = useState(false), [user, setUser] = useState(null), [ready, setReady] = useState(false), [tab, setTab] = useState(null), [locs, setLocs] = useState([]), [loc, setLoc] = useState("");
  useEffect(() => { api("/config").then(c => setDemo(c.demo)).catch(() => {}); api("/auth/me").then(setUser).catch(() => {}).finally(() => setReady(true)); }, []);
  useEffect(() => { if (user && !user.must_change_password) api("/locations").then(setLocs).catch(() => setLocs([])); }, [user]);
  if (!ready) return null;
  if (!user) return <><DemoBar demo={demo} />{location.hash === "#signup" ? <SignUp onDone={() => api("/auth/me").then(setUser)} /> : <Login onDone={u => api("/auth/me").then(setUser)} />}</>;
  if (user.must_setup_mfa) return <><DemoBar demo={demo} /><MfaSetup forced user={user} onDone={() => api("/auth/me").then(setUser)} /></>;
  if (user.must_change_password) return <><DemoBar demo={demo} /><ChangePassword onDone={() => setUser({ ...user, must_change_password: false })} /></>;
  const visible = TABS.filter(t => can(user, t[2]) && (!OPTIONAL.includes(t[0]) || (user.business?.modules || OPTIONAL).includes(t[0]))), cur = visible.find(t => t[0] === tab) || visible[0];
  if (!cur) return <p style={{ padding: 20 }}>Your role has no screens yet. Ask the owner.</p>;
  const Screen = cur[1], goTab = n => { setTab(n); setMenu(false); window.scrollTo(0, 0); };
  const quick = ["Dashboard", "Orders", "Scan", "Delivery", "Stock"].map(n => visible.find(t => t[0] === n)).filter(Boolean).slice(0, 4);
  return <><DemoBar demo={demo} /><div className="app">
    <nav className={"side" + (menu ? " open" : "")}><div className="row mclose" style={{ justifyContent: "space-between" }}><b>Menu</b><button className="s" onClick={() => setMenu(false)}>Close ✕</button></div><h2>FLOWMATE</h2><div className="mute logo2">{user.business?.name}</div>
      <div className="tabs">{visible.map(([n, , , label, grp], i) => <React.Fragment key={n}>{grp && grp !== visible[i - 1]?.[4] && <div className="mute grp">{grp}</div>}<button className={n === cur[0] ? "on" : ""} onClick={() => goTab(n)}>{label}</button></React.Fragment>)}</div>
      <InstallHint />
      <div className="mute who">{user.name} · {user.role}</div><button onClick={() => { setToken(null); location.reload(); }}>Log out</button></nav>
    <main className="main">
      <div className="row" style={{ justifyContent: "space-between" }}><div className="row" style={{ margin: 0 }}><select value={loc} onChange={e => setLoc(e.target.value)}><option value="">All locations</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select><GlobalSearch go={goTab} /></div>{can(user, "reports") && <Bell />}</div>
      <Screen key={cur[0] + loc} loc={loc ? +loc : null} locs={locs} user={user} reload={() => api("/auth/me").then(setUser)} go={goTab} /></main>
    <div className="bnav">{quick.map(([n, , , label]) => <button key={n} className={n === cur[0] ? "on" : ""} onClick={() => goTab(n)}>{ICON[n]}<span>{label}</span></button>)}<button onClick={() => setMenu(true)}>☰<span>Menu</span></button></div></div></>;
}

const ICON = { Dashboard: "🏠", Orders: "🧾", Scan: "📷", Delivery: "🚚", Stock: "📦" };

// "Install the app" helper: Android/Chrome shows a real install button, iPhone shows the manual steps.
function InstallHint() {
  const [ev, setEv] = useState(null), [done, setDone] = useState(false);
  useEffect(() => { const h = e => { e.preventDefault(); setEv(e); }; window.addEventListener("beforeinstallprompt", h); window.addEventListener("appinstalled", () => setDone(true)); return () => window.removeEventListener("beforeinstallprompt", h); }, []);
  const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  if (standalone || done) return null;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (ev) return <div className="card" style={{ margin: "10px 4px" }}><b>Install the app</b><div className="mute" style={{ margin: "4px 0 8px" }}>Opens full-screen from your home screen.</div><button className="p" onClick={async () => { ev.prompt(); await ev.userChoice; setEv(null); }}>Install FLOWMATE</button></div>;
  if (ios) return <div className="card mute" style={{ margin: "10px 4px", fontSize: 12 }}><b>Install on iPhone</b><br />Open this page in Safari, tap the Share button, then “Add to Home Screen”.</div>;
  return null;
}

function Bell() {
  const [n, load] = useData("/notifications"), [open, setOpen] = useState(false);
  useEffect(() => { const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);
  const unread = (n || []).filter(x => !x.read).length;
  return <div style={{ position: "relative" }}><button className="s" onClick={() => setOpen(!open)}>🔔 {unread > 0 && <b className="bad">{unread}</b>}</button>
    {open && <div className="card pop"><div className="row" style={{ justifyContent: "space-between" }}><b>Notifications</b><button className="s" onClick={async () => { await api("/notifications/read-all", { method: "POST" }); load(); }}>Mark all read</button></div>
      {(n || []).slice(0, 15).map(x => <div key={x.id} style={{ padding: "6px 0", borderTop: "1px solid var(--line)", opacity: x.read ? .55 : 1 }}>{x.message}<div className="mute" style={{ fontSize: 11 }}>{x.created_at.slice(0, 16).replace("T", " ")}</div></div>)}{!n?.length && <div className="mute">Nothing yet.</div>}</div>}</div>;
}

const DemoBar = ({ demo }) => demo ? <div style={{ background: "#b36b00", color: "#fff", textAlign: "center", padding: 6, fontWeight: 600 }}>PRACTICE VERSION — fake data for learning. Nothing here is real.</div> : null;

function Login({ onDone }) {
  const [email, setEmail] = useState(""), [pw, setPw] = useState(""), [err, setErr] = useState(""), [otp, setOtp] = useState(""), [needOtp, setNeedOtp] = useState(false), [how, setHow] = useState("");
  async function go(e, resend) { e?.preventDefault(); try { const r = await api("/auth/login", { method: "POST", body: new URLSearchParams({ username: email, password: pw, ...(otp && !resend && { otp }) }) }); setToken(r.access_token); onDone(r.user); } catch (x) { if (x.message.includes("MFA_REQUIRED")) { const [, m, to] = x.message.split(":"); setNeedOtp(true); setHow(m === "sms" ? `We sent a text message with a 6-digit code to ${to}.` : "Enter the 6-digit code from your authenticator app."); setErr(resend ? "A new code was sent." : ""); } else setErr(x.message); } }
  return <form className="login" onSubmit={go}><h1>FLOWMATE LOGISTICS</h1><div className="mute">From the first order to the final payment — everything connected.</div>{err && <div className="err">{err}</div>}
    <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" autoComplete="username" /><input type="password" value={pw} onChange={e => setPw(e.target.value)} placeholder="Password" autoComplete="current-password" />{needOtp && <><div className="mute">{how} You can also use a recovery code.</div><input autoFocus value={otp} onChange={e => setOtp(e.target.value)} placeholder="Code" autoComplete="one-time-code" inputMode="numeric" />{how.startsWith("We sent") && <button type="button" className="s" onClick={() => go(null, true)}>Send a new code</button>}</>}<button className="p">Log in</button><button type="button" className="s" onClick={() => { location.hash = "signup"; location.reload(); }}>Create a business account</button><div className="mute" style={{ fontSize: 12 }}><a href="/privacy" target="_blank">Privacy</a> · <a href="/terms" target="_blank">Terms</a></div></form>;
}

function ChangePassword({ onDone }) {
  const [o, setO] = useState(""), [n, setN] = useState(""), [err, setErr] = useState("");
  async function go(e) { e.preventDefault(); try { const r = await api("/auth/change-password", { method: "POST", body: { old_password: o, new_password: n } }); if (r.access_token) setToken(r.access_token); onDone(); } catch (x) { setErr(x.message); } }
  return <form className="login" onSubmit={go}><h1>Choose a new password</h1><div className="mute">Replace the temporary password (at least 10 characters).</div>{err && <div className="err">{err}</div>}
    <input type="password" placeholder="Temporary password" value={o} onChange={e => setO(e.target.value)} /><input type="password" placeholder="New password" value={n} onChange={e => setN(e.target.value)} /><button className="p">Save and continue</button></form>;
}

function SignUp({ onDone }) {
  const [types, setTypes] = useState([]), [f, setF] = useState({ business_name: "", kind: "cafe", owner_name: "", email: "", password: "", accept_terms: false }), [err, setErr] = useState("");
  useEffect(() => { api("/business-types").then(setTypes).catch(() => {}); }, []);
  async function go(e) { e.preventDefault(); try { const r = await api("/signup", { method: "POST", body: f }); setToken(r.access_token); location.hash = ""; onDone(); } catch (x) { setErr(x.message); } }
  const set = k => e => setF({ ...f, [k]: e.target.value });
  return <form className="login" onSubmit={go}><h1>Create your business account</h1><div className="mute">Your own private workspace. Nobody else can see your data.</div>{err && <div className="err">{err}</div>}
    <input placeholder="Business name" value={f.business_name} onChange={set("business_name")} /><select value={f.kind} onChange={set("kind")}>{types.map(t => <option key={t.kind} value={t.kind}>{t.label}</option>)}</select>
    <input placeholder="Your name" value={f.owner_name} onChange={set("owner_name")} autoComplete="name" /><input type="email" placeholder="Email" value={f.email} onChange={set("email")} autoComplete="username" /><input type="password" placeholder="Password (at least 10 characters)" value={f.password} onChange={set("password")} autoComplete="new-password" />
    <label style={{ fontSize: 13 }}><input type="checkbox" checked={f.accept_terms} onChange={e => setF({ ...f, accept_terms: e.target.checked })} style={{ width: "auto" }} /> I accept the <a href="/terms" target="_blank">Terms</a> and <a href="/privacy" target="_blank">Privacy Policy</a></label>
    <button className="p" disabled={!f.accept_terms}>Create account</button><button type="button" className="s" onClick={() => { location.hash = ""; location.reload(); }}>I already have an account</button></form>;
}
