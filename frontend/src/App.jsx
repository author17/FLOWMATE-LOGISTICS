import React, { useEffect, useState } from "react";
import { api, setToken } from "./api.js";
import { useData } from "./ui.jsx";
import { Orders, Delivery, CashUp, Audit } from "./screens.jsx";
import { Dashboard, Invoices, Scan, Banking, Stock, Suppliers, DataPage, MfaSetup, Payments, GlobalSearch } from "./screens3.jsx";
import { Customers, Products, Expenses, Members, Reports, Assistant, Users, Settings } from "./screens2.jsx";

// [name (used by links), component, permission needed, menu label, group]
const TABS = [["Dashboard", Dashboard, "reports", "Dashboard", ""],
  ["Orders", Orders, "orders", "Orders", "SALES"], ["Customers", Customers, "orders", "Customers", "SALES"], ["Members", Members, "memberships", "Members", "SALES"], ["Suppliers", Suppliers, "invoices", "Suppliers", "SUPPLY"], ["Products", Products, "stock_read", "Products", "SUPPLY"], ["Stock", Stock, "stock_read", "Inventory", "SUPPLY"],
  ["Invoices", Invoices, "invoices", "Invoices", "MONEY"], ["Expenses", Expenses, "expenses", "Expenses", "MONEY"], ["Banking", Banking, "banking_read", "Banking", "MONEY"], ["Payments", Payments, "banking_read", "Payments", "MONEY"], ["Cash-up", CashUp, "shifts", "Cash-up", "MONEY"],
  ["Delivery", Delivery, "delivery", "Logistics", "LOGISTICS"],
  ["Scan", Scan, "documents", "Documents", "INSIGHT"], ["Reports", Reports, "reports", "Reports", "INSIGHT"], ["Assistant", Assistant, "assistant_any", "AI Assist", "INSIGHT"],
  ["Settings", Settings, "users_dummy", "Settings", "ADMIN"], ["Users", Users, "users_dummy", "Users", "ADMIN"], ["Data", DataPage, "users_dummy", "Data & backups", "ADMIN"], ["Audit", Audit, "reports", "Audit", "ADMIN"]];
const can = (user, area) => user.perms.includes("*") || user.perms.includes(area) || (area === "assistant_any" && (user.perms.includes("assistant") || user.perms.includes("assistant_basic")));

export default function App() {
  const [demo, setDemo] = useState(false), [user, setUser] = useState(null), [ready, setReady] = useState(false), [tab, setTab] = useState(null), [locs, setLocs] = useState([]), [loc, setLoc] = useState("");
  useEffect(() => { api("/config").then(c => setDemo(c.demo)).catch(() => {}); api("/auth/me").then(setUser).catch(() => {}).finally(() => setReady(true)); }, []);
  useEffect(() => { if (user && !user.must_change_password) api("/locations").then(setLocs).catch(() => setLocs([])); }, [user]);
  if (!ready) return null;
  if (!user) return <><DemoBar demo={demo} /><Login onDone={u => api("/auth/me").then(setUser)} /></>;
  if (user.must_setup_mfa) return <><DemoBar demo={demo} /><MfaSetup forced onDone={() => api("/auth/me").then(setUser)} /></>;
  if (user.must_change_password) return <><DemoBar demo={demo} /><ChangePassword onDone={() => setUser({ ...user, must_change_password: false })} /></>;
  const visible = TABS.filter(t => can(user, t[2])), cur = visible.find(t => t[0] === tab) || visible[0];
  if (!cur) return <p style={{ padding: 20 }}>Your role has no screens yet. Ask the owner.</p>;
  const Screen = cur[1];
  return <><DemoBar demo={demo} /><div className="app">
    <nav className="side"><h2>FLOWMATE</h2><div className="mute logo2">LOGISTICS<br />Your business's digital assistant</div>
      <div className="tabs">{visible.map(([n, , , label, grp], i) => <React.Fragment key={n}>{grp && grp !== visible[i - 1]?.[4] && <div className="mute grp">{grp}</div>}<button className={n === cur[0] ? "on" : ""} onClick={() => setTab(n)}>{label}</button></React.Fragment>)}</div>
      <div className="mute who">{user.name} · {user.role}</div><button onClick={() => { setToken(null); location.reload(); }}>Log out</button></nav>
    <main className="main">
      <div className="row" style={{ justifyContent: "space-between" }}><div className="row" style={{ margin: 0 }}><select value={loc} onChange={e => setLoc(e.target.value)}><option value="">All locations</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select><GlobalSearch go={setTab} /></div>{can(user, "reports") && <Bell />}</div>
      <Screen key={cur[0] + loc} loc={loc ? +loc : null} locs={locs} user={user} reload={() => api("/auth/me").then(setUser)} go={setTab} /></main></div></>;
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
  const [email, setEmail] = useState(""), [pw, setPw] = useState(""), [err, setErr] = useState(""), [otp, setOtp] = useState(""), [needOtp, setNeedOtp] = useState(false);
  async function go(e) { e.preventDefault(); try { const r = await api("/auth/login", { method: "POST", body: new URLSearchParams({ username: email, password: pw, ...(otp && { otp }) }) }); setToken(r.access_token); onDone(r.user); } catch (x) { if (x.message.includes("MFA_REQUIRED")) { setNeedOtp(true); setErr(""); } else setErr(x.message); } }
  return <form className="login" onSubmit={go}><h1>FLOWMATE LOGISTICS</h1><div className="mute">From the first order to the final payment — everything connected.</div>{err && <div className="err">{err}</div>}
    <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" autoComplete="username" /><input type="password" value={pw} onChange={e => setPw(e.target.value)} placeholder="Password" autoComplete="current-password" />{needOtp && <><div className="mute">Enter the 6-digit code from your authenticator app (or a recovery code).</div><input autoFocus value={otp} onChange={e => setOtp(e.target.value)} placeholder="Code" autoComplete="one-time-code" /></>}<button className="p">Log in</button></form>;
}

function ChangePassword({ onDone }) {
  const [o, setO] = useState(""), [n, setN] = useState(""), [err, setErr] = useState("");
  async function go(e) { e.preventDefault(); try { await api("/auth/change-password", { method: "POST", body: { old_password: o, new_password: n } }); onDone(); } catch (x) { setErr(x.message); } }
  return <form className="login" onSubmit={go}><h1>Choose a new password</h1><div className="mute">Replace the temporary password (at least 10 characters).</div>{err && <div className="err">{err}</div>}
    <input type="password" placeholder="Temporary password" value={o} onChange={e => setO(e.target.value)} /><input type="password" placeholder="New password" value={n} onChange={e => setN(e.target.value)} /><button className="p">Save and continue</button></form>;
}
