import React, { useEffect, useState } from "react";
import { api, eur } from "./api.js";
import { useData, Err, Tag } from "./ui.jsx";

// Bank connection portal: the business owner links / syncs / reconnects / disconnects their own bank. No developer involved.
export function BankConnections() {
  const [st, loadSt, e0] = useData("/bank/status"), [conns, load, e1] = useData("/bank/connections");
  const [country, setCountry] = useState("CY"), [psu, setPsu] = useState("business"), [inst, setInst] = useState([]), [pick, setPick] = useState(""), [q, setQ] = useState("");
  const [msg, setMsg] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(""), [keys, setKeys] = useState({ app_id: "", private_key: "" }), [showKeys, setShowKeys] = useState(false);
  const run = (label, fn) => async (...a) => { setBusy(label); setErr(""); setMsg(""); try { await fn(...a); } catch (x) { setErr(x.message); } setBusy(""); };
  useEffect(() => { if (st?.configured) api(`/bank/institutions?country=${country}&psu_type=${psu}`).then(r => { setInst(r); setPick(r[0]?.name || ""); }).catch(x => setErr(x.message)); }, [st?.configured, country, psu]);
  const go = run("connect", async () => { const r = await api("/bank/connections", { method: "POST", body: { institution: pick, country, psu_type: psu } }); window.location.href = r.authorization_url; });
  const reconnect = run("reconnect", async c => { const r = await api(`/bank/connections/${c.id}/reconnect`, { method: "POST" }); window.location.href = r.authorization_url; });
  const sync = run("sync", async c => { const r = await api(`/bank/connections/${c.id}/sync`, { method: "POST" }); setMsg(`Synced: ${r.added} new transaction(s).`); load(); });
  const disc = run("disc", async c => { if (!confirm(`Disconnect ${c.institution}? FLOWMATE stops reading this bank. Past transactions stay in your records.`)) return; await api(`/bank/connections/${c.id}`, { method: "DELETE" }); setMsg("Disconnected."); load(); });
  const saveKeys = run("keys", async () => { await api("/bank/credentials", { method: "PUT", body: keys }); setKeys({ app_id: "", private_key: "" }); setShowKeys(false); setMsg("Provider keys saved (stored encrypted)."); loadSt(); });
  const rmKeys = run("keys", async () => { if (!confirm("Remove the saved provider keys? Existing connections will stop syncing.")) return; await api("/bank/credentials", { method: "DELETE" }); loadSt(); });
  const shown = inst.filter(i => i.name.toLowerCase().includes(q.toLowerCase()));
  return <><h1 style={{ fontSize: 16, marginTop: 18 }}>Bank connections (live bank feed)</h1><Err e={e0 || e1 || err} />{msg && <div className="card" style={{ marginBottom: 10 }}>{msg}</div>}
    {st && <p className="mute">Provider: <b>{st.provider === "none" ? "not set up" : st.provider}</b>{st.keys_from !== "none" && <> · keys from {st.keys_from}</>} · automatic sync every {st.auto_sync_hours} h. Read-only: FLOWMATE can see balances and transactions, it can never move money, and it never sees your bank password.</p>}
    {st && !st.configured && <div className="card" style={{ marginBottom: 10 }}><b>Step 1 — one-time setup</b>
      <p className="mute">Register a free application at <b>enablebanking.com</b> (Control Panel), set its redirect URL to <code>{st.redirect_url}</code>, then paste the Application ID and the private key here.</p>
      <KeyForm keys={keys} setKeys={setKeys} save={saveKeys} busy={busy} /></div>}
    {st?.configured && st.keys_from === "settings" && <div className="row"><button className="s" onClick={() => setShowKeys(!showKeys)}>Change provider keys</button><button className="s" onClick={rmKeys}>Remove keys</button></div>}
    {showKeys && <KeyForm keys={keys} setKeys={setKeys} save={saveKeys} busy={busy} />}
    {st?.configured && <div className="card" style={{ marginBottom: 12 }}><b>Connect a bank</b><div className="row" style={{ marginTop: 8 }}>
      <select value={country} onChange={e => setCountry(e.target.value)}>{[["CY", "Cyprus"], ["GR", "Greece"], ["DE", "Germany"], ["FR", "France"], ["IT", "Italy"], ["ES", "Spain"], ["NL", "Netherlands"], ["IE", "Ireland"], ["GB", "United Kingdom"]].map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select>
      <select value={psu} onChange={e => setPsu(e.target.value)}><option value="business">Business account</option><option value="personal">Personal account</option></select>
      <input placeholder="Search bank…" value={q} onChange={e => setQ(e.target.value)} style={{ width: 150 }} />
      <select value={pick} onChange={e => setPick(e.target.value)}>{shown.map(i => <option key={i.name}>{i.name}</option>)}</select>
      <button className="p" disabled={!pick || busy} onClick={go}>{busy === "connect" ? "Opening bank…" : "Connect"}</button></div>
      <div className="mute">You will be sent to your bank's own secure page to approve read-only access (valid up to 90 days; FLOWMATE reminds you to renew).</div></div>}
    {(conns || []).map(c => <div className="card" key={c.id} style={{ marginBottom: 10 }}>
      <div className="row" style={{ justifyContent: "space-between", margin: 0 }}><b>{c.institution} <span className="mute">({c.psu_type})</span></b><Tag s={c.status} /></div>
      <div className="mute">{c.status === "PENDING" ? "Waiting for you to approve at the bank. " : ""}{c.days_left != null && c.status === "ACTIVE" && <>Access valid for {c.days_left} more day(s). </>}{c.last_sync_at && <>Last sync {c.last_sync_at.slice(0, 16).replace("T", " ")}. </>}</div>
      {c.last_error && <div className="err">{c.last_error}</div>}
      {c.accounts.map(a => <div key={a.id} style={{ padding: "4px 0" }}>{a.name} · <code>{a.iban}</code> · balance <b>{eur(a.balance_cents)}</b>{a.available_cents != null && <span className="mute"> (available {eur(a.available_cents)})</span>}</div>)}
      <div className="row" style={{ margin: "8px 0 0" }}>
        {c.status === "ACTIVE" && <button className="s" disabled={busy} onClick={() => sync(c)}>{busy === "sync" ? "Syncing…" : "Sync now"}</button>}
        {(c.needs_reconnect || c.status === "PENDING") && <button className="p" disabled={busy} onClick={() => reconnect(c)}>{c.status === "PENDING" ? "Finish connecting" : "Renew access"}</button>}
        <button className="s" disabled={busy} onClick={() => disc(c)}>Disconnect</button></div></div>)}
    {conns && !conns.length && st?.configured && <p className="mute">No bank connected yet.</p>}</>;
}

function KeyForm({ keys, setKeys, save, busy }) {
  return <div className="row"><input placeholder="Application ID" value={keys.app_id} onChange={e => setKeys({ ...keys, app_id: e.target.value })} style={{ minWidth: 260 }} />
    <textarea placeholder="-----BEGIN PRIVATE KEY----- …" rows={3} value={keys.private_key} onChange={e => setKeys({ ...keys, private_key: e.target.value })} style={{ minWidth: 320, flex: 1 }} />
    <button className="p" disabled={!keys.app_id || !keys.private_key || busy} onClick={save}>Save keys</button></div>;
}

// shows the result of the bank redirect (/?bank=connected|failed&reason=...)
export function BankToast() {
  const [m, setM] = useState(null);
  useEffect(() => { const p = new URLSearchParams(location.search); if (p.get("bank")) { setM({ ok: p.get("bank") === "connected", why: p.get("reason") }); history.replaceState({}, "", "/"); } }, []);
  if (!m) return null;
  const why = { unknown_or_used_link: "This link was already used or is unknown.", link_expired: "The link expired - start again.", not_granted: "Access was not granted at the bank.", provider_error: "The provider could not finish the connection." }[m.why] || m.why;
  return <div className="card" style={{ marginBottom: 12, borderColor: m.ok ? "var(--good)" : "var(--bad)" }}>{m.ok ? "Bank connected. Transactions are being matched to your orders and invoices." : `Bank connection failed. ${why || ""}`} <button className="s" onClick={() => setM(null)}>OK</button></div>;
}
