import React, { useEffect, useState } from "react";
import { api, setToken } from "./api.js";
import { Dashboard, Orders, Delivery, Invoices, Scan, Banking, CashUp, Stock, Suppliers, Audit } from "./screens.jsx";

const TABS = [["Dashboard", Dashboard], ["Orders", Orders], ["Delivery", Delivery], ["Suppliers", Suppliers], ["Invoices", Invoices], ["Scan", Scan], ["Banking", Banking], ["Cash-up", CashUp], ["Stock", Stock], ["Audit", Audit]];

export default function App() {
  const [user, setUser] = useState(null), [ready, setReady] = useState(false), [tab, setTab] = useState("Dashboard"), [locs, setLocs] = useState([]), [loc, setLoc] = useState("");
  useEffect(() => { api("/auth/me").then(setUser).catch(() => {}).finally(() => setReady(true)); }, []);
  useEffect(() => { if (user) api("/locations").then(setLocs).catch(() => {}); }, [user]);
  if (!ready) return null;
  if (!user) return <Login onDone={setUser} />;
  const Screen = TABS.find(t => t[0] === tab)[1];
  return <div className="app">
    <nav className="side"><h2>FLOWMATE</h2><div className="mute" style={{ padding: "0 8px 10px", fontSize: 11 }}>LOGISTICS</div>
      {TABS.map(([n]) => <button key={n} className={n === tab ? "on" : ""} onClick={() => setTab(n)}>{n}</button>)}
      <div className="mute" style={{ padding: 8, marginTop: 16 }}>{user.name} · {user.role}</div>
      <button onClick={() => { setToken(null); location.reload(); }}>Log out</button></nav>
    <main className="main">
      <div className="row"><select value={loc} onChange={e => setLoc(e.target.value)}><option value="">All locations</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select></div>
      <Screen key={tab + loc} loc={loc ? +loc : null} locs={locs} user={user} /></main></div>;
}

function Login({ onDone }) {
  const [email, setEmail] = useState("owner@demo.com"), [pw, setPw] = useState(""), [err, setErr] = useState("");
  async function go(e) { e.preventDefault(); try { const r = await api("/auth/login", { method: "POST", body: new URLSearchParams({ username: email, password: pw }) }); setToken(r.access_token); onDone(r.user); } catch (x) { setErr(x.message); } }
  return <form className="login" onSubmit={go}><h1>FLOWMATE LOGISTICS</h1><div className="mute">From the first order to the final payment — everything connected.</div>{err && <div className="err">{err}</div>}
    <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" /><input type="password" value={pw} onChange={e => setPw(e.target.value)} placeholder="Password" /><button className="p">Log in</button></form>;
}
