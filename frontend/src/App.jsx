import React, { useEffect, useState } from "react";
import { api, setToken } from "./api.js";
import { Dashboard, Orders, Delivery, Invoices, Scan, Banking, CashUp, Stock, Suppliers, Audit } from "./screens.jsx";

const TABS = [["Dashboard", Dashboard], ["Orders", Orders], ["Delivery", Delivery], ["Suppliers", Suppliers], ["Invoices", Invoices], ["Scan", Scan], ["Banking", Banking], ["Cash-up", CashUp], ["Stock", Stock], ["Audit", Audit]];

export default function App() {
  const [demo, setDemo] = useState(false), [user, setUser] = useState(null), [ready, setReady] = useState(false), [tab, setTab] = useState("Dashboard"), [locs, setLocs] = useState([]), [loc, setLoc] = useState("");
  useEffect(() => { api("/config").then(c => setDemo(c.demo)).catch(() => {}); api("/auth/me").then(setUser).catch(() => {}).finally(() => setReady(true)); }, []);
  useEffect(() => { if (user) api("/locations").then(setLocs).catch(() => {}); }, [user]);
  if (!ready) return null;
  if (!user) return <><DemoBar demo={demo} /><Login onDone={setUser} /></>;
  if (user.must_change_password) return <><DemoBar demo={demo} /><ChangePassword onDone={() => setUser({ ...user, must_change_password: false })} /></>;
  const Screen = TABS.find(t => t[0] === tab)[1];
  return <><DemoBar demo={demo} /><div className="app">
    <nav className="side"><h2>FLOWMATE</h2><div className="mute" style={{ padding: "0 8px 10px", fontSize: 11 }}>LOGISTICS</div>
      {TABS.map(([n]) => <button key={n} className={n === tab ? "on" : ""} onClick={() => setTab(n)}>{n}</button>)}
      <div className="mute" style={{ padding: 8, marginTop: 16 }}>{user.name} · {user.role}</div>
      <button onClick={() => { setToken(null); location.reload(); }}>Log out</button></nav>
    <main className="main">
      <div className="row"><select value={loc} onChange={e => setLoc(e.target.value)}><option value="">All locations</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select></div>
      <Screen key={tab + loc} loc={loc ? +loc : null} locs={locs} user={user} /></main></div></>;
}

function Login({ onDone }) {
  const [email, setEmail] = useState("owner@demo.com"), [pw, setPw] = useState(""), [err, setErr] = useState("");
  async function go(e) { e.preventDefault(); try { const r = await api("/auth/login", { method: "POST", body: new URLSearchParams({ username: email, password: pw }) }); setToken(r.access_token); onDone(r.user); } catch (x) { setErr(x.message); } }
  return <form className="login" onSubmit={go}><h1>FLOWMATE LOGISTICS</h1><div className="mute">From the first order to the final payment — everything connected.</div>{err && <div className="err">{err}</div>}
    <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" /><input type="password" value={pw} onChange={e => setPw(e.target.value)} placeholder="Password" /><button className="p">Log in</button></form>;
}

const DemoBar = ({ demo }) => demo ? <div style={{ background: "#b36b00", color: "#fff", textAlign: "center", padding: 6, fontWeight: 600 }}>PRACTICE VERSION — fake data for learning. Nothing here is real. Do not enter real customer or bank data.</div> : null;

function ChangePassword({ onDone }) {
  const [o, setO] = useState(""), [n, setN] = useState(""), [err, setErr] = useState("");
  async function go(e) { e.preventDefault(); try { await api("/auth/change-password", { method: "POST", body: { old_password: o, new_password: n } }); onDone(); } catch (x) { setErr(x.message); } }
  return <form className="login" onSubmit={go}><h1>Choose a new password</h1><div className="mute">For security you must replace the temporary password (at least 10 characters).</div>{err && <div className="err">{err}</div>}
    <input type="password" placeholder="Temporary password" value={o} onChange={e => setO(e.target.value)} /><input type="password" placeholder="New password" value={n} onChange={e => setN(e.target.value)} /><button className="p">Save and continue</button></form>;
}
