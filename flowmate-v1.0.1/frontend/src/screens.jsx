import React, { useEffect, useState } from "react";
import { api, eur, cents } from "./api.js";

import { useData, Err, Tag, Table, Card, PayLink } from "./ui.jsx";
import { OrderTools, TillImport } from "./screens3.jsx";

export function Orders({ loc, locs, user }) {
  const [rows, load, err] = useData("/orders" + (loc ? `?location_id=${loc}` : "")), [products] = useData("/products"), [customers] = useData("/customers"), [stripe] = useData("/stripe/status");
  const [lines, setLines] = useState([{ pid: "", qty: 1 }]), [cust, setCust] = useState(""), [method, setMethod] = useState("CASH"), [where, setWhere] = useState(""), [e2, setE2] = useState(""), [link, setLink] = useState(null);
  const L = loc || +where || locs[0]?.id, valid = lines.filter(l => l.pid && +l.qty > 0);
  const setLine = (i, k, v) => setLines(lines.map((l, j) => j === i ? { ...l, [k]: v } : l));
  const run = fn => async (...a) => { try { await fn(...a); setE2(""); load(); } catch (x) { setE2(x.message); } };
  const add = run(async () => { await api("/orders", { method: "POST", body: { location_id: L, customer_id: cust ? +cust : null, payment_method: method, items: valid.map(l => ({ product_id: +l.pid, quantity: +l.qty })) } }); setLines([{ pid: "", qty: 1 }]); setCust(""); });
  const setStatus = run((id, status) => api(`/orders/${id}/status`, { method: "PUT", body: { status } }));
  const payLink = run(async id => { const r = await api("/stripe/checkout", { method: "POST", body: { target_type: "order", target_id: id } }); setLink(r.url); });
  const total = valid.reduce((a, l) => a + (products?.find(p => p.id === +l.pid)?.sell_cents || 0) * +l.qty, 0);
  return <><h1>Orders</h1><Err e={err || e2} />{link && <PayLink url={link} onClose={() => setLink(null)} />}
    <div className="card" style={{ marginBottom: 14 }}>{lines.map((l, i) => <div className="row" key={i}><select value={l.pid} onChange={e => setLine(i, "pid", e.target.value)}><option value="">Product…</option>{(products || []).map(p => <option key={p.id} value={p.id}>{p.name} · {eur(p.sell_cents)}</option>)}</select>
      <input type="number" min="1" value={l.qty} onChange={e => setLine(i, "qty", e.target.value)} style={{ width: 70 }} />{lines.length > 1 && <button className="s" onClick={() => setLines(lines.filter((_, j) => j !== i))}>✕</button>}</div>)}
      <div className="row"><button className="s" onClick={() => setLines([...lines, { pid: "", qty: 1 }])}>+ Add item</button>
        {!loc && <select value={where} onChange={e => setWhere(e.target.value)}>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select>}
        <select value={cust} onChange={e => setCust(e.target.value)}><option value="">Walk-in customer</option>{(customers || []).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <select value={method} onChange={e => setMethod(e.target.value)}>{["CASH", "CARD", "BANK_TRANSFER", "ONLINE", "OTHER"].map(m => <option key={m}>{m}</option>)}</select>
        <b>{eur(total)}</b><button className="p" onClick={add} disabled={!valid.length}>Create order</button></div></div>
    <TillImport loc={loc} locs={locs} onDone={load} />
    {rows && <Table cols={[["#", r => r.id], ["Place", r => locs.find(l => l.id === r.location_id)?.name], ["Items", r => r.items.map(i => `${i.description} ×${i.quantity}`).join(", ")], ["Customer", r => customers?.find(c => c.id === r.customer_id)?.name || ""], ["Method", r => r.payment_method], ["Total", r => eur(r.total_cents)], ["Status", r => <Tag s={r.status} />],
      ["", r => r.status !== "PAID" && r.status !== "CANCELLED" && <span className="row" style={{ margin: 0 }}><button className="s" onClick={() => setStatus(r.id, r.status === "NEW" ? "PROCESSING" : r.status === "PROCESSING" ? "COMPLETED" : "PAID")}>Next step</button>
        {stripe?.configured && <button className="s" onClick={() => payLink(r.id)}>Card link</button>}<button className="s" onClick={() => setStatus(r.id, "CANCELLED")}>Cancel</button></span> || <OrderTools order={r} onDone={load} />]]} rows={rows} />}</>;
}

export function CashUp({ loc, locs }) {
  const [rows, load, err] = useData("/shifts"), [open, setOpen] = useState(null), [f, setF] = useState({ float: "100", cash: "", card: "0", exp: "0", counted: "" }), [res, setRes] = useState(null), [e2, setE2] = useState("");
  const cur = rows?.find(s => s.status === "OPEN");
  async function start() { try { await api("/shifts/open", { method: "POST", body: { location_id: loc || locs[0].id, opening_float_cents: cents(f.float) } }); load(); setE2(""); } catch (x) { setE2(x.message); } }
  async function close() { try { setRes(await api(`/shifts/${cur.id}/close`, { method: "POST", body: { cash_sales_cents: cents(f.cash), card_sales_cents: cents(f.card), cash_expenses_cents: cents(f.exp), counted_cash_cents: cents(f.counted) } })); load(); setE2(""); } catch (x) { setE2(x.message); } }
  const set = k => e => setF({ ...f, [k]: e.target.value });
  return <><h1>Cashier shift & cash-up</h1><Err e={err || e2} />
    {res && <div className="card" style={{ marginBottom: 10 }}>Expected cash {eur(res.expected_cash_cents)} · counted {eur(res.counted_cash_cents)} · difference <b className={res.difference_cents ? "bad" : "good"}>{eur(res.difference_cents)}</b></div>}
    {!cur ? <div className="row"><input value={f.float} onChange={set("float")} style={{ width: 90 }} /><span className="mute">opening float €</span><button className="p" onClick={start}>Open shift</button></div>
      : <div className="card" style={{ marginBottom: 14 }}><b>Close shift #{cur.id}</b> <span className="mute">— enter the till (Z report) totals</span><div className="row" style={{ marginTop: 8 }}>
        <input placeholder="Cash sales €" value={f.cash} onChange={set("cash")} /><input placeholder="Card sales €" value={f.card} onChange={set("card")} /><input placeholder="Cash paid out €" value={f.exp} onChange={set("exp")} /><input placeholder="Cash counted €" value={f.counted} onChange={set("counted")} />
        <button className="p" disabled={!f.cash || !f.counted} onClick={close}>Close & compare</button></div></div>}
    {rows && <Table cols={[["#", r => r.id], ["Location", r => locs.find(l => l.id === r.location_id)?.name], ["Opened", r => r.opened_at?.slice(0, 16).replace("T", " ")], ["Cash sales", r => eur(r.cash_sales_cents)], ["Card", r => eur(r.card_sales_cents)], ["Difference", r => r.difference_cents == null ? "" : <span className={r.difference_cents ? "bad" : "good"}>{eur(r.difference_cents)}</span>], ["Status", r => <Tag s={r.status} />]]} rows={rows} />}</>;
}

export function Audit() {
  const [rows, , err] = useData("/audit");
  return <><h1>Audit history</h1><Err e={err} />{rows && <Table cols={[["When", r => r.at.slice(0, 19).replace("T", " ")], ["User", r => r.user_name], ["Action", r => r.action], ["Object", r => `${r.object_type} ${r.object_id}`], ["Change / device", r => r.new_value?.device ? <span>{r.new_value.device}{r.new_value.email ? ` · tried: ${r.new_value.email}` : ""}<div className="mute" style={{ fontSize: 11 }}>IP {r.new_value.ip}</div></span> : <code style={{ fontSize: 11 }}>{JSON.stringify(r.new_value)}</code>]]} rows={rows} />}</>;
}

export function Delivery({ user }) {
  const [rows, load, err] = useData("/deliveries"), [orders] = useData("/orders"), [drivers] = useData("/deliveries/drivers"), [f, setF] = useState({ order_id: "", address: "", eta: "" }), [e2, setE2] = useState("");
  const staff = user.role !== "driver";
  const wrap = fn => async (...a) => { try { await fn(...a); setE2(""); load(); } catch (x) { setE2(x.message); } };
  const create = wrap(async () => { await api("/deliveries", { method: "POST", body: { order_id: +f.order_id, address: f.address, eta: f.eta || null } }); setF({ order_id: "", address: "", eta: "" }); });
  const assign = wrap((id, driver_id) => api(`/deliveries/${id}/assign`, { method: "PUT", body: { driver_id: +driver_id } }));
  const setSt = wrap((id, status, reason) => api(`/deliveries/${id}/status`, { method: "PUT", body: { status, reason } }));
  async function proof(id, ev) {
    const file = ev.target.files[0]; if (!file) return; const fd = new FormData(); fd.append("file", file); fd.append("doc_type", "proof");
    try { const d = await api("/documents/scan", { method: "POST", body: fd }); await setSt_with_proof(id, d.id); } catch (x) { setE2(x.message); }
  }
  const setSt_with_proof = wrap((id, doc) => api(`/deliveries/${id}/status`, { method: "PUT", body: { status: "DELIVERED", proof_document_id: doc } }));
  const free = (orders || []).filter(o => o.status !== "CANCELLED" && !(rows || []).some(d => d.order_id === o.id));
  return <><h1>Delivery</h1><Err e={err || e2} />
    {staff && <div className="row"><select value={f.order_id} onChange={e => setF({ ...f, order_id: e.target.value })}><option value="">Order…</option>{free.map(o => <option key={o.id} value={o.id}>#{o.id} · {eur(o.total_cents)}</option>)}</select>
      <input placeholder="Delivery address" value={f.address} onChange={e => setF({ ...f, address: e.target.value })} style={{ minWidth: 240 }} /><label className="mute">ETA <input type="time" value={f.eta} onChange={e => setF({ ...f, eta: e.target.value })} /></label><button className="p" disabled={!f.order_id} onClick={create}>Create delivery</button></div>}
    {rows && <Table cols={[["Order", r => "#" + r.order_id], ["Customer", r => r.customer], ["Address", r => r.address], ["Driver", r => staff && r.status === "PREPARED" ? <select value={r.driver_id || ""} onChange={e => assign(r.id, e.target.value)}><option value="">Assign…</option>{(drivers || []).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select> : r.driver_name], ["ETA", r => staff ? <input type="time" value={r.eta || ""} style={{ width: 100 }} onChange={ev => wrap(v => api(`/deliveries/${r.id}/eta`, { method: "PUT", body: { eta: v } }))(ev.target.value)} /> : r.eta], ["Status", r => <Tag s={r.status} />],
      ["", r => <span className="row" style={{ margin: 0 }}>
        {r.driver_phone && <a className="btn" href={`tel:${r.driver_phone}`}>Call driver</a>}{r.status === "PREPARED" && <button className="s" onClick={() => setSt(r.id, "ON_THE_WAY")}>Start delivery</button>}
        {r.status === "ON_THE_WAY" && <><label className="btn">Delivered + photo<input type="file" accept="image/*" capture="environment" hidden onChange={e => proof(r.id, e)} /></label>
          <button className="s" onClick={() => { const why = prompt("Why did it fail?"); if (why) setSt(r.id, "FAILED", why); }}>Failed</button></>}
        {r.status === "FAILED" && <span className="bad">{r.failure_reason}</span>}</span>]]} rows={rows} />}</>;
}
