import React, { useEffect, useState } from "react";
import { api, eur, cents, download, API_BASE } from "./api.js";
import { useData, Err, Tag, Table, Card } from "./ui.jsx";
import { BankToast } from "./bank.jsx";
import { Capacitor } from "@capacitor/core";
import { ocrFile, parseText, prepareImage, isTiff, tiffToJpeg, resetOcr } from "./ocr.js";

const today = () => new Date().toISOString().slice(0, 10);
const useRun = (load) => { const [e, setE] = useState(""); return [e, (fn) => async (...a) => { try { await fn(...a); setE(""); load && load(); } catch (x) { setE(x.message); } }]; };
async function openFile(id) { const t = localStorage.getItem("token"); const r = await fetch(API_BASE + `/api/documents/${id}/file`, { headers: { Authorization: "Bearer " + t } }); if (r.ok) window.open(URL.createObjectURL(await r.blob())); }

/* ---------------- Dashboard ---------------- */
const DOT = { red: "🔴", orange: "🟠", blue: "🔵", green: "🟢" };
const ICON = { invoice_overdue: "⚠", invoice_due: "⚠", low_stock: "⚠", bank_problem: "⚠", payment_failed: "⚠", cash_difference: "⚠", payment_pending: "⏳", new_order: "🛒", invoice: "🧾", doc_to_verify: "📄", refund: "↩" };
const can = (u, a) => u.perms.includes("*") || u.perms.includes(a);

export function Dashboard({ loc, user, go }) {
  const [d, load, err] = useData("/cockpit" + (loc ? `?location_id=${loc}` : "")), [e2, setE2] = useState(""), [open, setOpen] = useState(null);
  useEffect(() => { const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);
  if (err) return <Err e={err} />; if (!d) return <p>Loading…</p>;
  const h = new Date().getHours(), greet = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening", k = d.kpi, f = d.finance, b = d.bank, lg = d.logistics;
  const max = Math.max(1, ...f.weeks.map(w => w.sales_cents));
  const QA = [["＋ New order", "Orders", "orders"], ["📷 Scan document", "Scan", "documents"], ["💶 Payment", "Invoices", "invoices"], ["＋ Expense", "Expenses", "expenses"], ["📦 Purchase order", "Stock", "purchase"], ["🚚 Delivery", "Delivery", "delivery"], ["🏦 Banking", "Banking", "banking_read"], ["👤 Customer", "Customers", "orders"], ["🏭 Supplier", "Suppliers", "invoices"]].filter(q => can(user, q[2]));
  const po = async l => { try { await api("/purchase-orders", { method: "POST", body: { supplier_id: l.supplier_id, location_id: l.location_id, items: [{ product_id: l.product_id, quantity: l.suggested }] } }); setE2(""); load(); go && go("Stock"); } catch (x) { setE2(x.message); } };
  const setSt = async (id, status) => { try { await api(`/deliveries/${id}/status`, { method: "PUT", body: { status } }); setOpen(null); load(); } catch (x) { setE2(x.message); } };
  const Box = ({ t, children, tab }) => <div className="card" style={{ marginBottom: 12 }}><div className="row" style={{ justifyContent: "space-between", margin: 0 }}><b>{t}</b>{tab && <button className="s" onClick={() => go(tab)}>View</button>}</div>{children}</div>;
  return <><BankToast /><h1 style={{ marginBottom: 2 }}>{greet}, {user.name.split(" ")[0]}</h1><div className="mute" style={{ marginBottom: 12 }}>{new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</div><Err e={e2} />
    <div className="cards">
      <Card l="Orders" v={<>{k.orders_open} open <span className="mute" style={{ fontSize: 12 }}>+{k.orders_today} today</span></>} />
      <Card l="Received (month)" v={<>{eur(k.received_cents)} {k.received_change_pct != null && <span className={k.received_change_pct >= 0 ? "good" : "bad"} style={{ fontSize: 12 }}>{k.received_change_pct >= 0 ? "+" : ""}{k.received_change_pct}%</span>}</>} />
      <Card l="To pay (suppliers)" v={<>{eur(k.to_pay_cents)} <span className="mute" style={{ fontSize: 12 }}>{k.to_pay_count} pending</span></>} />
      <Card l="Stock" v={k.stock_alerts ? `${k.stock_alerts} alerts ⚠` : "All fine"} cls={k.stock_alerts ? "warn" : "good"} />
      <Card l="Delivery" v={<>{k.deliveries_today} today <span className="mute" style={{ fontSize: 12 }}>{k.deliveries_pending} pending</span></>} />
      <Card l="Bank" v={<>{eur(b.balance_cents)} <span className={b.connected ? "good" : "warn"} style={{ fontSize: 12 }}>{b.connected ? "● connected" : "○ not connected"}</span></>} /></div>

    <Box t="⚠ What needs your attention">{d.attention.length ? d.attention.map((a, i) => <div key={i} className="row" style={{ justifyContent: "space-between", borderTop: i ? "1px solid var(--line)" : 0, padding: "8px 0", margin: 0 }}><span>{DOT[a.level]} {a.text}</span><button className={a.level === "red" ? "p" : "s"} onClick={() => go(a.tab)}>{a.action}</button></div>) : <p className="good">Nothing needs your attention. All clear.</p>}</Box>

    {d.low_stock.length > 0 && <Box t="Low stock — with suggested order">{d.low_stock.map(l => <div key={l.product_id + "-" + l.location_id} className="row" style={{ justifyContent: "space-between", borderTop: "1px solid var(--line)", padding: "8px 0", margin: 0 }}>
      <span><b>{l.name}</b> — {l.quantity} units <span className="mute">(minimum {l.min_stock})</span><br /><span className="mute">Suggested order: {l.suggested} units · Supplier: {l.supplier || "none set"} · Last price: {eur(l.last_price_cents)}/unit</span></span>
      {can(user, "purchase") && (l.supplier_id ? <button className="p" onClick={() => po(l)}>CREATE PURCHASE ORDER</button> : <button className="s" onClick={() => go("Products")}>Set supplier</button>)}</div>)}</Box>}

    <Box t="Quick actions"><div className="row" style={{ margin: "8px 0 0" }}>{QA.map(([l, tab]) => <button key={l} className="s" style={{ padding: "10px 14px" }} onClick={() => go(tab)}>{l}</button>)}</div></Box>

    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 12 }}>
      <Box t="Financial pulse — this month">
        {[["Sales", eur(f.sales_cents)], ["Expenses", eur(f.expenses_cents)]].map(([a, v]) => <div key={a} className="row" style={{ justifyContent: "space-between", margin: "4px 0" }}><span>{a}</span><b>{v}</b></div>)}
        <div className="row" style={{ justifyContent: "space-between", borderTop: "1px solid var(--line)", margin: "4px 0", paddingTop: 6 }}><span>Net</span><b className={f.net_cents < 0 ? "bad" : "good"}>{eur(f.net_cents)}</b></div>
        {[["Money outstanding", eur(f.outstanding_cents)], ["Supplier payments", eur(f.supplier_paid_cents)]].map(([a, v]) => <div key={a} className="row" style={{ justifyContent: "space-between", margin: "4px 0" }}><span className="mute">{a}</span><span>{v}</span></div>)}
        <svg viewBox="0 0 240 90" style={{ width: "100%", height: 100 }} role="img" aria-label="Sales by week">{f.weeks.map((w, i) => { const hh = Math.round(w.sales_cents / max * 60); return <g key={i}><rect x={i * 60 + 12} y={70 - hh} width={36} height={hh} rx={3} fill="var(--accent)"><title>{eur(w.sales_cents)}</title></rect><text x={i * 60 + 30} y={84} fontSize="9" textAnchor="middle" fill="var(--mute)">{w.label}</text></g>; })}</svg></Box>

      <Box t="Banking" tab="Banking">
        <div className={b.connected ? "good" : "warn"}>{b.connected ? `● BANK CONNECTED${b.institution ? " — " + b.institution : ""}` : "○ Not connected"}</div>
        <div style={{ fontSize: 22, fontWeight: 700, margin: "6px 0" }}>{eur(b.balance_cents)}</div>
        {b.today.length ? b.today.map(t => <div key={t.id} className="row" style={{ justifyContent: "space-between", margin: "2px 0" }}><span className={t.amount_cents < 0 ? "bad" : "good"}>{t.amount_cents > 0 ? "+" : "−"} {eur(Math.abs(t.amount_cents))}</span><span className="mute">{t.counterparty || t.reference}</span></div>) : <div className="mute">No movements today.</div>}
        <div className="mute" style={{ marginTop: 6 }}>{b.matched_today} transaction(s) matched automatically today</div>
        {!b.connected && can(user, "banking_admin") && <button className="p" style={{ marginTop: 6 }} onClick={() => go("Settings")}>Connect your bank</button>}
        <div className="mute" style={{ fontSize: 12, marginTop: 6 }}>🔒 FLOWMATE never stores your bank password. Access is granted at your bank and can be removed any time.</div></Box>

      <Box t="Today's logistics" tab="Delivery">
        {[["Ready for delivery", lg.ready, ""], ["In transit", lg.in_transit, ""], ["Delivered today", lg.delivered_today, "good"], ["Delayed / failed", lg.delayed, lg.delayed ? "bad" : ""]].map(([a, v, c]) => <div key={a} className="row" style={{ justifyContent: "space-between", margin: "4px 0" }}><span>{a}</span><b className={c}>{v}</b></div>)}
        {lg.active.map(x => <div key={x.id}><a href="#" onClick={e => { e.preventDefault(); setOpen(open === x.id ? null : x.id); }}>Delivery #{x.id} · {x.customer} · <Tag s={x.status} /></a>
          {open === x.id && <div className="card" style={{ margin: "6px 0" }}><div>Order #{x.order_id} · {x.packages} package(s)</div><div>Driver: {x.driver_name || "not assigned"}</div><div>Address: {x.address || "—"}</div><div>ETA: <b>{x.eta || "—"}</b> {can(user, "delivery") && <button className="s" onClick={async () => { const v = prompt("ETA (HH:MM, empty to clear)", x.eta || ""); if (v === null) return; try { await api(`/deliveries/${x.id}/eta`, { method: "PUT", body: { eta: v } }); load(); } catch (e) { setE2(e.message); } }}>Set</button>}</div>{x.scheduled_for && <div>Scheduled: {x.scheduled_for}</div>}{x.failure_reason && <div className="bad">{x.failure_reason}</div>}
            <div className="row" style={{ margin: "8px 0 0" }}>{x.address && <a className="btn" target="_blank" rel="noreferrer" href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(x.address)}`}>View route</a>}{x.driver_phone && <a className="btn" href={`tel:${x.driver_phone}`}>Contact driver</a>}{x.phone && <a className="btn" href={`tel:${x.phone}`}>Call customer</a>}
              {x.status === "PREPARED" && x.driver_id && <button className="s" onClick={() => setSt(x.id, "ON_THE_WAY")}>Start delivery</button>}<button className="s" onClick={() => go("Delivery")}>{x.status === "ON_THE_WAY" ? "Mark delivered (photo)" : "Open"}</button></div></div>}</div>)}</Box></div>

    <Box t="FLOWMATE activity — what happened">{d.activity.length ? d.activity.map((a, i) => <div key={i} style={{ padding: "6px 0", borderTop: i ? "1px solid var(--line)" : 0 }}>{ICON[a.kind] || "✓"} {a.message}<div className="mute" style={{ fontSize: 11 }}>{a.at.slice(0, 16).replace("T", " ")}</div></div>) : <p className="mute">Nothing yet — activity appears here as the business runs.</p>}</Box>
    {can(user, "assistant") || can(user, "assistant_basic") ? <AskBar /> : null}</>;
}

function AskBar() {
  const [q, setQ] = useState(""), [a, setA] = useState(""), [busy, setBusy] = useState(false);
  const ask = async t => { const question = t || q; if (!question) return; setBusy(true); try { setA((await api("/assistant", { method: "POST", body: { question } })).answer); } catch (x) { setA("Error: " + x.message); } setBusy(false); };
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = () => { const r = new SR(); r.lang = "en-GB"; r.onresult = e => { const t = e.results[0][0].transcript; setQ(t); ask(t); }; r.start(); };
  return <div className="card" style={{ position: "sticky", bottom: 8, boxShadow: "0 4px 18px rgba(0,0,0,.18)" }}><b>🤖 Ask FLOWMATE</b>
    {a && <div style={{ margin: "6px 0", whiteSpace: "pre-wrap" }}>{a}</div>}
    <div className="row" style={{ margin: "6px 0 0" }}><input style={{ flex: 1, minWidth: 180 }} placeholder='"What needs my attention today?"' value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === "Enter" && ask()} />{SR && <button className="s" onClick={mic} title="Speak">🎤</button>}<button className="p" disabled={busy} onClick={() => ask()}>{busy ? "…" : "➤"}</button></div>
    <div className="row" style={{ margin: "6px 0 0" }}>{["What needs my attention today?", "Show unpaid invoices", "What do I need to order?", "How much did we spend this month?"].map(s => <button key={s} className="s" style={{ fontSize: 12 }} onClick={() => { setQ(s); ask(s); }}>{s}</button>)}</div></div>;
}

/* ---------------- Suppliers + profile ---------------- */
export function Suppliers() {
  const [q, setQ] = useState(""), [rows, load, err] = useData("/suppliers" + (q ? `?q=${encodeURIComponent(q)}` : "")), [open, setOpen] = useState(null);
  const empty = { name: "", vat_number: "", iban: "", email: "", phone: "", notes: "" }, [f, setF] = useState(empty), [e2, run] = useRun(load);
  const add = run(async () => { await api("/suppliers", { method: "POST", body: f }); setF(empty); });
  if (open) return <SupplierProfile id={open} onBack={() => { setOpen(null); load(); }} />;
  return <><h1>Suppliers</h1><Err e={err || e2} />
    <div className="row"><input placeholder="Search suppliers…" value={q} onChange={e => setQ(e.target.value)} /></div>
    <div className="row">{[["name", "Name *"], ["vat_number", "VAT no."], ["iban", "IBAN"], ["email", "E-mail"], ["phone", "Phone"]].map(([k, p]) => <input key={k} placeholder={p} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} />)}<button className="p" disabled={!f.name} onClick={add}>Add supplier</button></div>
    {rows && <Table cols={[["Name", r => <a href="#" onClick={e => { e.preventDefault(); setOpen(r.id); }}>{r.name}</a>], ["VAT", r => r.vat_number], ["IBAN", r => r.iban], ["Email", r => r.email], ["Phone", r => r.phone]]} rows={rows} />}</>;
}

function SupplierProfile({ id, onBack }) {
  const [p, load, err] = useData(`/suppliers/${id}/profile`), [f, setF] = useState(null), [msg, setMsg] = useState(""), [e2, run] = useRun(load);
  useEffect(() => { if (p && !f) setF({ name: p.supplier.name, vat_number: p.supplier.vat_number || "", iban: p.supplier.iban || "", email: p.supplier.email || "", phone: p.supplier.phone || "", notes: p.supplier.notes || "" }); }, [p]);
  const save = run(async () => { await api(`/suppliers/${id}`, { method: "PUT", body: f }); setMsg("Saved"); });
  if (!p || !f) return <><Err e={err} /><p>Loading…</p></>;
  return <><button className="s" onClick={onBack}>← Suppliers</button><h1 style={{ marginTop: 10 }}>{p.supplier.name}</h1><Err e={err || e2} />
    <div className="cards"><Card l="Outstanding" v={eur(p.outstanding_cents)} cls={p.outstanding_cents ? "warn" : ""} /><Card l="Pending invoices" v={p.pending_invoices} /><Card l="Last payment" v={p.last_payment ? `${eur(p.last_payment.amount_cents)} · ${p.last_payment.date}` : "—"} /></div>
    <div className="row">{[["name", "Name"], ["vat_number", "VAT no."], ["iban", "IBAN"], ["email", "E-mail"], ["phone", "Phone"], ["notes", "Notes"]].map(([k, l]) => <input key={k} placeholder={l} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} />)}<button className="p" onClick={save}>Save</button><span className="mute">{msg}</span></div>
    <h1 style={{ fontSize: 16 }}>Invoices</h1><Table cols={[["Invoice", r => r.number], ["Date", r => r.issue_date], ["Due", r => r.due_date], ["Total", r => eur(r.total_cents)], ["Status", r => <Tag s={r.status} />]]} rows={p.invoices} />
    <h1 style={{ fontSize: 16, marginTop: 14 }}>Payments</h1><Table cols={[["#", r => r.id], ["Amount", r => eur(r.amount_cents)], ["Status", r => <Tag s={r.status} />], ["Created", r => r.created_at?.slice(0, 10)]]} rows={p.payments} />
    <h1 style={{ fontSize: 16, marginTop: 14 }}>Products from this supplier</h1><Table cols={[["SKU", r => r.sku], ["Name", r => r.name], ["Cost", r => eur(r.purchase_cents)]]} rows={p.products} />
    <h1 style={{ fontSize: 16, marginTop: 14 }}>Documents</h1><Table cols={[["File", r => <a href="#" onClick={e => { e.preventDefault(); openFile(r.id); }}>{r.filename}</a>], ["Type", r => r.doc_type], ["Status", r => <Tag s={r.status} />]]} rows={p.documents} /></>;
}

/* ---------------- Invoices (items, detail, pay flow) ---------------- */
export function Invoices({ locs, user }) {
  const [rows, load, err] = useData("/invoices"), [sups] = useData("/suppliers"), [prods] = useData("/products"), [pos] = useData("/purchase-orders/full"), [open, setOpen] = useState(null), [e2, run] = useRun(load);
  const blank = { supplier_id: "", number: "", total: "", vat: "", due: "", loc: "", po: "", stock: false }, [f, setF] = useState(blank), [items, setItems] = useState([]);
  const add = run(async () => { await api("/invoices", { method: "POST", body: { supplier_id: +f.supplier_id, number: f.number, issue_date: today(), due_date: f.due || null, total_cents: cents(f.total), vat_cents: cents(f.vat), location_id: f.loc ? +f.loc : null, purchase_order_id: f.po ? +f.po : null, add_to_stock: f.stock && !!f.loc, items: items.filter(i => i.pid).map(i => ({ product_id: +i.pid, description: prods.find(p => p.id === +i.pid)?.name, quantity: +i.qty, unit_cents: cents(i.cost) })) } }); setF(blank); setItems([]); });
  if (open) return <InvoiceDetail id={open} user={user} onBack={() => { setOpen(null); load(); }} />;
  return <><h1>Supplier invoices</h1><Err e={err || e2} />
    <div className="card" style={{ marginBottom: 12 }}><div className="row"><select value={f.supplier_id} onChange={e => setF({ ...f, supplier_id: e.target.value })}><option value="">Supplier…</option>{(sups || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
      <input placeholder="Invoice no." value={f.number} onChange={e => setF({ ...f, number: e.target.value })} /><input placeholder="Total €" value={f.total} onChange={e => setF({ ...f, total: e.target.value })} style={{ width: 90 }} /><input placeholder="VAT €" value={f.vat} onChange={e => setF({ ...f, vat: e.target.value })} style={{ width: 80 }} />
      <label className="mute">Due <input type="date" value={f.due} onChange={e => setF({ ...f, due: e.target.value })} /></label></div>
      {items.map((it, i) => <div className="row" key={i}><select value={it.pid} onChange={e => setItems(items.map((x, j) => j === i ? { ...x, pid: e.target.value, cost: x.cost || ((prods.find(p => p.id === +e.target.value)?.purchase_cents || 0) / 100).toFixed(2) } : x))}><option value="">Product…</option>{(prods || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <input type="number" min="1" style={{ width: 70 }} value={it.qty} onChange={e => setItems(items.map((x, j) => j === i ? { ...x, qty: e.target.value } : x))} /><input placeholder="Unit cost €" style={{ width: 100 }} value={it.cost} onChange={e => setItems(items.map((x, j) => j === i ? { ...x, cost: e.target.value } : x))} /><button className="s" onClick={() => setItems(items.filter((_, j) => j !== i))}>✕</button></div>)}
      <div className="row"><button className="s" onClick={() => setItems([...items, { pid: "", qty: 1, cost: "" }])}>+ Line item</button>
        <select value={f.loc} onChange={e => setF({ ...f, loc: e.target.value })}><option value="">Received at…</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select>
        <select value={f.po} onChange={e => setF({ ...f, po: e.target.value })}><option value="">Link purchase order…</option>{(pos || []).filter(p => p.status !== "INVOICED" && p.status !== "PAID").map(p => <option key={p.id} value={p.id}>PO-{p.id} · {p.supplier}</option>)}</select>
        <label><input type="checkbox" checked={f.stock} onChange={e => setF({ ...f, stock: e.target.checked })} /> Add items to stock</label>
        <button className="p" disabled={!f.supplier_id || !f.number || !f.total} onClick={add}>Add invoice</button></div></div>
    {rows && <Table cols={[["Supplier", r => r.supplier_name], ["Invoice", r => <a href="#" onClick={e => { e.preventDefault(); setOpen(r.id); }}>{r.number}</a>], ["Due", r => r.due_date], ["Total", r => eur(r.total_cents)], ["Status", r => <Tag s={r.status} />]]} rows={rows} />}</>;
}

function InvoiceDetail({ id, user, onBack }) {
  const [i, load, err] = useData(`/invoices/${id}`), [accts] = useData("/bank/accounts"), [pays, loadP] = useData("/payments"), [e2, run] = useRun(() => { load(); loadP(); });
  const [m, setM] = useState("CASH");
  const canApprove = user.perms.includes("*") || user.perms.includes("payments_approve");
  const prepare = run(() => api("/payments", { method: "POST", body: { invoice_id: id, account_id: accts[0].id } }));
  const approve = run(async p => { const r = await api(`/payments/${p.id}/approve`, { method: "POST" }); if (r.authorization_url) window.open(r.authorization_url); });
  const reject = run(p => { const why = prompt("Reason for rejecting?") ; if (why !== null) return api(`/payments/${p.id}/reject`, { method: "POST", body: { reason: why } }); });
  const markPaid = run(() => api(`/invoices/${id}/mark-paid`, { method: "POST", body: { method: m } }));
  if (!i) return <><Err e={err} /><p>Loading…</p></>;
  const mine = (pays || []).filter(p => p.invoice_id === id), open = mine.find(p => !["COMPLETED", "FAILED", "CANCELLED", "REJECTED"].includes(p.status));
  return <><button className="s" onClick={onBack}>← Invoices</button><h1 style={{ marginTop: 10 }}>Invoice {i.number} <Tag s={i.status} /></h1><Err e={err || e2} />
    <div className="cards"><Card l="Supplier" v={i.supplier?.name} /><Card l="Total" v={eur(i.total_cents)} /><Card l="VAT" v={eur(i.vat_cents)} /><Card l="Due" v={i.due_date || "—"} /><Card l="Paid on" v={i.paid_on ? `${i.paid_on} (${i.paid_method})` : "—"} /></div>
    {i.document && <p><a href="#" onClick={e => { e.preventDefault(); openFile(i.document.id); }}>View original document ({i.document.filename})</a></p>}
    <Table cols={[["Item", r => r.description], ["Qty", r => r.quantity], ["Unit", r => eur(r.unit_cents)], ["Line", r => eur(r.quantity * r.unit_cents)]]} rows={i.items} />
    {i.status !== "PAID" && <div className="card" style={{ marginTop: 12 }}><b>Pay this invoice</b>
      <p className="mute">Step 1: prepare the payment. Step 2: the owner approves it. Step 3: pay in your bank's own app; the bank statement line completes it automatically.</p>
      <div className="row">{!open && accts?.length > 0 && <button className="p" onClick={prepare}>Prepare payment {eur(i.total_cents)}</button>}
        {open?.status === "PENDING" && (canApprove ? <><button className="p" onClick={() => approve(open)}>Approve payment</button><button className="s" onClick={() => reject(open)}>Reject</button></> : <span className="warn">Waiting for the owner's approval</span>)}
        {open && !["PENDING"].includes(open.status) && <><Tag s={open.status} />{open.authorization_url && <a className="btn" href={open.authorization_url} target="_blank" rel="noreferrer">Open bank approval</a>}<button className="s" onClick={run(() => api(`/payments/${open.id}/refresh`, { method: "POST" }))}>Check status</button></>}</div>
      {!open && <div className="row"><span className="mute">Already paid outside the app?</span><select value={m} onChange={e => setM(e.target.value)}>{["CASH", "BANK_TRANSFER", "CARD", "OTHER"].map(x => <option key={x}>{x}</option>)}</select><button className="s" onClick={markPaid}>Mark as paid</button></div>}</div>}</>;
}

/* ---------------- Banking: connect banner, manual match, classify, approvals ---------------- */
export function Banking({ user, locs }) {
  const [txs, load, err] = useData("/bank/transactions"), [accts] = useData("/bank/accounts"), [conns] = useData("/bank/connections"), [online] = useData("/stripe/payments"), [pays, loadP] = useData("/payments");
  const [orders] = useData("/orders"), [invs] = useData("/invoices");
  const [msg, setMsg] = useState(""), [sel, setSel] = useState(null), [f, setF] = useState({ target: "" }), [e2, run] = useRun(() => { load(); loadP(); });
  const admin = user.perms.includes("*") || user.perms.includes("banking_admin"), approver = user.perms.includes("*") || user.perms.includes("payments_approve");
  const live = (conns || []).some(c => c.status === "ACTIVE");
  async function imp(ev) { const file = ev.target.files[0]; if (!file) return; const fd = new FormData(); fd.append("file", file); try { const r = await api(`/bank/accounts/${accts[0].id}/import-csv`, { method: "POST", body: fd }); setMsg(`Imported ${r.added} (skipped ${r.skipped_duplicates} duplicates). Auto-reconciled ${r.matching.reconciled}, suggestions ${r.matching.suggested}, unmatched ${r.matching.unmatched}.`); load(); } catch (x) { setMsg(x.message); } }
  const manual = run(async t => { const [type, tid] = f.target.split(":"); await api(`/bank/transactions/${t.id}/match`, { method: "POST", body: { target_type: type, target_id: +tid } }); setSel(null); });
  const classify = run(async (t, category) => { await api(`/bank/transactions/${t.id}/classify`, { method: "POST", body: { category, expense_category: category === "EXPENSE" ? (prompt("Expense category (e.g. Utilities, Rent)", "Other") || "Other") : null } }); setSel(null); });
  const runMatch = run(async () => { const r = await api("/bank/match/run", { method: "POST" }); setMsg(`Reconciled ${r.reconciled}, suggestions ${r.suggested}, unmatched ${r.unmatched}.`); });
  const approve = run(async p => { const r = await api(`/payments/${p.id}/approve`, { method: "POST" }); if (r.authorization_url) window.open(r.authorization_url); });
  const reject = run(p => { const why = prompt("Reason for rejecting?"); if (why !== null) return api(`/payments/${p.id}/reject`, { method: "POST", body: { reason: why } }); });
  const waiting = (pays || []).filter(p => p.status === "PENDING");
  return <><BankToast /><h1>Banking</h1><Err e={err || e2} />
    {!live && admin && <div className="card" style={{ marginBottom: 12 }}><b>Connect your bank</b> — skip the CSV files: link your bank once (Settings → Bank connections) and transactions arrive automatically.</div>}
    {live && <div className="card" style={{ marginBottom: 12 }}>Live bank feed connected: {conns.filter(c => c.status === "ACTIVE").map(c => c.institution).join(", ")}. {conns.some(c => c.needs_reconnect) && <b className="warn">Access is about to expire - renew it in Settings → Bank connections.</b>}</div>}
    {msg && <div className="card" style={{ marginBottom: 10 }}>{msg}</div>}
    {waiting.length > 0 && <div className="card" style={{ marginBottom: 12, borderColor: "var(--warn)" }}><b>Payments waiting for approval</b><Table cols={[["Supplier", r => r.supplier], ["Invoice", r => r.invoice_number], ["Amount", r => eur(r.amount_cents)], ["Prepared by", r => r.prepared_by], ["", r => approver ? <span className="row" style={{ margin: 0 }}><button className="p" onClick={() => approve(r)}>Approve</button><button className="s" onClick={() => reject(r)}>Reject</button></span> : <span className="mute">owner must approve</span>]]} rows={waiting} /></div>}
    {admin && <div className="row"><span>Import statement CSV (Eurobank export etc.):</span><input type="file" accept=".csv" onChange={imp} disabled={!accts?.length} /><button className="s" onClick={runMatch}>Re-run matching</button></div>}
    {accts?.length > 0 && <div className="cards">{accts.map(a => <Card key={a.id} l={`${a.name}${a.iban ? " · " + a.iban : ""}`} v={eur(a.balance_cents)} />)}</div>}
    {txs && <Table cols={[["Date", r => r.booked_on], ["Amount", r => <span className={r.amount_cents < 0 ? "bad" : "good"}>{eur(r.amount_cents)}</span>], ["Reference", r => r.reference], ["Counterparty", r => r.counterparty], ["Status", r => <Tag s={r.match_status} />], ["Matched to", r => r.match ? `${r.match.target_type} #${r.match.target_id}` : r.category || ""],
      ["", r => r.match_status === "SUGGESTED" ? <button className="s" onClick={run(async () => { await api(`/bank/transactions/${r.id}/confirm`, { method: "POST" }); })}>Confirm {r.match?.target_type} #{r.match?.target_id}</button> : r.match_status !== "RECONCILED" && admin && <button className="s" onClick={() => { setSel(sel === r.id ? null : r.id); setF({ target: "" }); }}>Match / classify</button>]]} rows={txs} />}
    {sel && txs && (() => { const t = txs.find(x => x.id === sel); return <div className="card" style={{ marginTop: 10 }}><b>Line {t.booked_on} · {eur(t.amount_cents)} · {t.reference}</b>
      <div className="row" style={{ marginTop: 8 }}><select value={f.target} onChange={e => setF({ target: e.target.value })}><option value="">Match to order or invoice…</option>
        {t.amount_cents > 0 ? (orders || []).filter(o => o.status !== "PAID" && o.status !== "CANCELLED").map(o => <option key={o.id} value={`order:${o.id}`}>Order #{o.id} · {eur(o.total_cents)}</option>) : (invs || []).filter(i => i.status !== "PAID").map(i => <option key={i.id} value={`invoice:${i.id}`}>{i.supplier_name} {i.number} · {eur(i.total_cents)}</option>)}</select>
        <button className="p" disabled={!f.target} onClick={() => manual(t)}>Match</button></div>
      <div className="row">{t.amount_cents < 0 ? <><button className="s" onClick={() => classify(t, "EXPENSE")}>It's an expense</button><button className="s" onClick={() => classify(t, "BANK_FEE")}>Bank fee</button></> : <button className="s" onClick={() => classify(t, "OTHER_INCOME")}>Other income</button>}<button className="s" onClick={() => classify(t, "TRANSFER")}>Transfer between own accounts</button><button className="s" onClick={() => classify(t, "REFUND")}>Refund</button><button className="s" onClick={() => setSel(null)}>Close</button></div></div>; })()}
    {online?.length > 0 && <><h1 style={{ marginTop: 20 }}>Card payments (Stripe)</h1><Table cols={[["#", r => r.id], ["For", r => `${r.target_type} #${r.target_id}`], ["Amount", r => eur(r.amount_cents)], ["Status", r => <Tag s={r.status} />], ["Paid", r => r.paid_at?.slice(0, 16).replace("T", " ")]]} rows={online} /></>}
    <h1 style={{ marginTop: 20 }}>Supplier payments</h1>
    {pays && <Table cols={[["#", r => r.id], ["Supplier", r => r.supplier], ["Invoice", r => r.invoice_number], ["Amount", r => eur(r.amount_cents)], ["Status", r => <Tag s={r.status} />], ["", r => ["APPROVED", "AUTHORIZATION_REQUIRED", "PROCESSING"].includes(r.status) && <span className="row" style={{ margin: 0 }}>{r.authorization_url && <a className="btn" href={r.authorization_url} target="_blank" rel="noreferrer">Bank approval</a>}<button className="s" onClick={run(() => api(`/payments/${r.id}/refresh`, { method: "POST" }))}>Check status</button></span>]]} rows={pays} />}</>;
}

/* ---------------- Stock: movements, transfer, adjust, purchase orders ---------------- */
export function Stock({ loc, locs, user }) {
  const [rows, load, err] = useData("/stock" + (loc ? `?location_id=${loc}` : "")), [prods] = useData("/products"), [mv, loadMv] = useData("/stock/movements?limit=60");
  const can = k => user.perms.includes("*") || user.perms.includes(k), [msg, setMsg] = useState(""), [e2, run] = useRun(() => { load(); loadMv(); });
  const [a, setA] = useState({ pid: "", loc: "", change: "", reason: "count correction" }), [t, setT] = useState({ pid: "", from: "", to: "", qty: "" });
  const adjust = run(async () => { await api("/stock/adjust", { method: "POST", body: { product_id: +a.pid, location_id: +(a.loc || loc || locs[0].id), change: +a.change, reason: a.reason } }); setA({ ...a, change: "" }); setMsg("Stock updated"); });
  const transfer = run(async () => { await api("/stock/transfer", { method: "POST", body: { product_id: +t.pid, from_location_id: +t.from, to_location_id: +t.to, quantity: +t.qty } }); setT({ ...t, qty: "" }); setMsg("Transferred"); });
  const lowPO = run(async () => { const r = await api(`/purchase-orders/from-low-stock/${loc || locs[0].id}`, { method: "POST" }); setMsg(`${r.length} draft purchase order(s) created — see below`); });
  const name = id => prods?.find(p => p.id === id)?.name || "#" + id, L = id => locs.find(l => l.id === id)?.name;
  return <><h1>Stock</h1><Err e={err || e2} />{msg && <div className="card" style={{ marginBottom: 10 }}>{msg}</div>}
    {can("stock") && <div className="card" style={{ marginBottom: 10 }}><b>Correct stock (count / waste / delivery)</b><div className="row" style={{ marginTop: 6 }}><select value={a.pid} onChange={e => setA({ ...a, pid: e.target.value })}><option value="">Product…</option>{(prods || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      {!loc && <select value={a.loc} onChange={e => setA({ ...a, loc: e.target.value })}><option value="">Location…</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select>}<input placeholder="+/- qty" style={{ width: 80 }} value={a.change} onChange={e => setA({ ...a, change: e.target.value })} />
      <select value={a.reason} onChange={e => setA({ ...a, reason: e.target.value })}>{["count correction", "waste", "damaged", "delivery received", "adjustment"].map(x => <option key={x}>{x}</option>)}</select><button className="p" disabled={!a.pid || !+a.change} onClick={adjust}>Apply</button></div>
      <b>Move stock between locations</b><div className="row" style={{ marginTop: 6 }}><select value={t.pid} onChange={e => setT({ ...t, pid: e.target.value })}><option value="">Product…</option>{(prods || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
        <select value={t.from} onChange={e => setT({ ...t, from: e.target.value })}><option value="">From…</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select><select value={t.to} onChange={e => setT({ ...t, to: e.target.value })}><option value="">To…</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select>
        <input placeholder="Qty" style={{ width: 70 }} value={t.qty} onChange={e => setT({ ...t, qty: e.target.value })} /><button className="p" disabled={!t.pid || !t.from || !t.to || !+t.qty} onClick={transfer}>Transfer</button></div></div>}
    {can("purchase") && <div className="row"><button className="p" onClick={lowPO}>Create purchase orders for low stock</button></div>}
    {rows && <Table cols={[["SKU", r => r.sku], ["Product", r => r.name], ["Location", r => L(r.location_id)], ["Qty", r => <span className={r.low ? "bad" : ""}>{r.quantity}</span>], ["Min", r => r.min_stock], ["Max", r => r.max_stock || "—"], ["", r => r.low && <Tag s="LOW STOCK" />]]} rows={rows} />}
    {can("purchase") && <PurchaseOrders prods={prods} locs={locs} onChange={() => { load(); loadMv(); }} />}
    {mv?.length > 0 && <><h1 style={{ fontSize: 16, marginTop: 18 }}>Stock movements</h1><Table cols={[["When", r => r.created_at?.slice(0, 16).replace("T", " ")], ["Product", r => r.product], ["Location", r => L(r.location_id)], ["Change", r => <span className={r.change < 0 ? "bad" : "good"}>{r.change > 0 ? "+" : ""}{r.change}</span>], ["Reason", r => r.reason], ["Ref", r => r.ref]]} rows={mv} /></>}</>;
}

function PurchaseOrders({ prods, locs, onChange }) {
  const [pos, load, err] = useData("/purchase-orders/full"), [sups] = useData("/suppliers"), [e2, run] = useRun(() => { load(); onChange(); }), [msg, setMsg] = useState("");
  const [f, setF] = useState({ supplier: "", loc: "", lines: [{ pid: "", qty: 1 }] }), POS = ["DRAFT", "SENT", "CONFIRMED", "RECEIVED", "INVOICED", "PAID"];
  const create = run(async () => { await api("/purchase-orders", { method: "POST", body: { supplier_id: +f.supplier, location_id: +f.loc, items: f.lines.filter(l => l.pid).map(l => ({ product_id: +l.pid, quantity: +l.qty })) } }); setF({ supplier: "", loc: "", lines: [{ pid: "", qty: 1 }] }); });
  const next = run(p => api(`/purchase-orders/${p.id}/status`, { method: "PUT", body: { status: POS[POS.indexOf(p.status) + 1] } }));
  const send = run(async p => { await api(`/purchase-orders/${p.id}/send`, { method: "POST" }); setMsg(`PO-${p.id} e-mailed to the supplier.`); });
  const setL = (i, k, v) => setF({ ...f, lines: f.lines.map((l, j) => j === i ? { ...l, [k]: v } : l) });
  return <><h1 style={{ fontSize: 16, marginTop: 18 }}>Purchase orders</h1><Err e={err || e2} />{msg && <div className="card">{msg}</div>}
    <div className="card" style={{ marginBottom: 10 }}><div className="row"><select value={f.supplier} onChange={e => setF({ ...f, supplier: e.target.value })}><option value="">Supplier…</option>{(sups || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
      <select value={f.loc} onChange={e => setF({ ...f, loc: e.target.value })}><option value="">Deliver to…</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select></div>
      {f.lines.map((l, i) => <div className="row" key={i}><select value={l.pid} onChange={e => setL(i, "pid", e.target.value)}><option value="">Product…</option>{(prods || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select><input type="number" min="1" style={{ width: 80 }} value={l.qty} onChange={e => setL(i, "qty", e.target.value)} /></div>)}
      <div className="row"><button className="s" onClick={() => setF({ ...f, lines: [...f.lines, { pid: "", qty: 1 }] })}>+ Line</button><button className="p" disabled={!f.supplier || !f.loc || !f.lines.some(l => l.pid)} onClick={create}>Create purchase order</button></div></div>
    {pos && <Table cols={[["#", r => "PO-" + r.id], ["Supplier", r => r.supplier], ["Items", r => r.items.map(i => `${i.product} ×${i.quantity}`).join(", ")], ["Total", r => eur(r.total_cents)], ["Status", r => <Tag s={r.status} />],
      ["", r => <span className="row" style={{ margin: 0 }}><button className="s" onClick={() => download(`/purchase-orders/${r.id}/pdf`, `PO-${r.id}.pdf`).catch(x => alert(x.message))}>PDF</button>{r.status === "DRAFT" && <button className="s" onClick={() => send(r)}>E-mail to supplier</button>}{r.status !== "PAID" && <button className="s" onClick={() => next(r)}>Mark {POS[POS.indexOf(r.status) + 1]}</button>}</span>]]} rows={pos} />}</>;
}

/* ---------------- Documents: scan + library + review ---------------- */
const DTYPES = [["receipt", "Receipt"], ["invoice", "Supplier invoice"], ["delivery_note", "Delivery note"], ["purchase_order", "Purchase order"], ["tax_document", "Tax document"], ["statement", "Bank statement"], ["contract", "Contract"], ["other", "Other"]];

/* In-page camera: no switch to the phone's camera app (which can make low-memory phones close the browser tab). */
function CameraCapture({ onShot, onClose }) {
  const vid = React.useRef(null), [err, setErr] = useState(""), [n, setN] = useState(0), stream = React.useRef(null);
  useEffect(() => {
    let dead = false;
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 2048 }, height: { ideal: 1536 } }, audio: false })
      .then(st => { if (dead) { st.getTracks().forEach(t => t.stop()); return; } stream.current = st; if (vid.current) { vid.current.srcObject = st; vid.current.play().catch(() => { }); } })
      .catch(x => setErr(x.name === "NotAllowedError" ? "Camera permission was refused. Allow the camera for this site in the browser settings, or use the other button to pick a photo." : "Could not open the camera: " + (x.message || x.name)));
    return () => { dead = true; stream.current?.getTracks().forEach(t => t.stop()); };
  }, []);
  async function shot() {
    const v = vid.current; if (!v || !v.videoWidth) return;
    const k = Math.min(1, 2000 / Math.max(v.videoWidth, v.videoHeight)), c = document.createElement("canvas"); c.width = Math.round(v.videoWidth * k); c.height = Math.round(v.videoHeight * k);
    c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
    const blob = await new Promise(r => c.toBlob(r, "image/jpeg", 0.9)); c.width = c.height = 0;
    if (blob) { setN(n + 1); onShot(new File([blob], `photo-${Date.now()}.jpg`, { type: "image/jpeg" })); }
  }
  return <div style={{ position: "fixed", inset: 0, zIndex: 100, background: "#000", display: "flex", flexDirection: "column" }}>
    {err ? <div style={{ color: "#fff", padding: 24 }}>{err}</div> : <video ref={vid} playsInline muted style={{ flex: 1, minHeight: 0, width: "100%", objectFit: "contain" }} />}
    <div style={{ display: "flex", gap: 12, justifyContent: "center", alignItems: "center", padding: "12px 12px calc(16px + env(safe-area-inset-bottom))", background: "#000" }}>
      <button className="s" onClick={onClose}>{n ? `Done (${n})` : "Cancel"}</button>
      {!err && <button className="p" style={{ fontSize: 18, padding: "14px 28px" }} onClick={shot}>📸 Capture</button>}
    </div></div>;
}
export function Scan({ loc, locs }) {
  const [q, setQ] = useState(""), [ft, setFt] = useState(""), [st, setSt] = useState(""), qs = new URLSearchParams({ ...(q && { q }), ...(ft && { doc_type: ft }), ...(st && { status: st }) }).toString();
  const [docs, load, err] = useData("/documents" + (qs ? "?" + qs : "")), [sups] = useData("/suppliers"), [dtype, setDtype] = useState("receipt"), [busy, setBusy] = useState(false), [e2, setE2] = useState(""), [sel, setSel] = useState(null), [meta, setMeta] = useState(null);
  const [prog, setProg] = useState(""), [drag, setDrag] = useState(false), [cam, setCam] = useState(false), canCam = !!navigator.mediaDevices?.getUserMedia;
  async function handle(files) {
    files = [...files]; if (!files.length) return; if (files.length > 50) { setE2(`${files.length} files selected - please add at most 50 at a time (the first 50 are being processed).`); files = files.slice(0, 50); }
    setBusy(true); setE2(""); let last = null;
    for (let i = 0; i < files.length; i++) {
      const file = files[i], tag = files.length > 1 ? `File ${i + 1}/${files.length}: ` : "";
      try {
        setProg(tag + "uploading…");
        if (i > 0 && i % 10 === 0) await resetOcr();   // long batches: start a fresh reader now and then so memory never builds up
        let src = file;
        if (isTiff(file)) { setProg(tag + "converting TIFF…"); src = await tiffToJpeg(file); }
        let up = src;   // shrink big phone photos before uploading (faster, less memory, less storage)
        if (/^image\//.test(src.type) && src.size > 1.5e6) { try { const { blob } = await prepareImage(src, { maxSide: 2400, quality: 0.85, enhance: false }); if (blob && blob.size < src.size) up = new File([blob], src.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }); } catch { } }
        const fd = new FormData(); fd.append("file", up); fd.append("doc_type", dtype); if (loc) fd.append("location_id", loc);
        let d = await api("/documents/scan", { method: "POST", body: fd });
        if (d.duplicate_of) setE2(`${file.name}: the same file was already uploaded (document #${d.duplicate_of}). It was added again - delete one if it is a mistake.`);
        const ex = d.extracted || {};
        if (["receipt", "invoice", "delivery_note", "purchase_order", "tax_document"].includes(dtype) && !ex.total && !ex.supplier) {   // server has no reader: read it here, free, in the browser
          setProg(tag + "reading the text (first time takes ~20 s)…");
          let text = "", confidence = 0;
          try { ({ text, confidence } = await ocrFile(up, (p, msg) => setProg(tag + (msg || `reading… ${p}%`)))); }
          catch (x) { setE2(`${file.name}: saved, but the phone could not read it automatically (${x.message || x.name || "unknown error"}). Open Details and type the fields, or try again with better light / closer photo.`); last = d; continue; }
          const r = parseText(text, sups || []);
          const extracted = { ...r, confidence, raw_text: text.slice(0, 4000) };
          const sup = (sups || []).find(s => s.name === r.supplier);
          d = await api(`/documents/${d.id}`, { method: "PUT", body: { company: r.supplier || null, reference: r.number || null, amount_cents: r.total ? cents(r.total) : null, doc_date: r.date || null } });
          d = { ...d, extracted, supplier_id: sup?.id };
        }
        last = d;
      } catch (x) { setE2(`${file.name}: ${x.message}`); }
    }
    setBusy(false); setProg(""); load();
    if (last && files.length === 1 && ["receipt", "invoice"].includes(dtype)) setSel(last);
  }
  const up = ev => { handle(ev.target.files); ev.target.value = ""; };
  const native = Capacitor.isNativePlatform();
  async function nativeShot() {      // store app: the phone's own camera screen (permission + quality handled by the OS)
    try { const { Camera, CameraResultType, CameraSource } = await import("@capacitor/camera"); const ph = await Camera.getPhoto({ quality: 85, resultType: CameraResultType.Uri, source: CameraSource.Camera, correctOrientation: true, width: 2400 });
      const blob = await (await fetch(ph.webPath)).blob(); handle([new File([blob], `photo-${Date.now()}.${ph.format || "jpg"}`, { type: blob.type || "image/jpeg" })]); } catch (x) { if (!/cancel/i.test(x.message || "")) setE2(x.message || "Camera error"); } }
  const saveMeta = async () => { try { await api(`/documents/${meta.id}`, { method: "PUT", body: { doc_type: meta.doc_type, company: meta.company || null, reference: meta.reference || null, amount_cents: meta.amount ? cents(meta.amount) : null, doc_date: meta.doc_date || null, related_order_id: meta.related_order_id ? +meta.related_order_id : null, related_invoice_id: meta.related_invoice_id ? +meta.related_invoice_id : null, status: meta.status } }); setMeta(null); load(); } catch (x) { setE2(x.message); } };
  return <><h1>Documents</h1><Err e={err || e2} />
    {cam && <CameraCapture onShot={f => { setCam(false); handle([f]); }} onClose={() => setCam(false)} />}
    <div className="row"><select value={dtype} onChange={e => setDtype(e.target.value)}>{DTYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>{native ? <button className="p camera-btn" onClick={nativeShot}>📷 Take photo</button> : canCam ? <button className="p camera-btn" onClick={() => setCam(true)}>📷 Take photo (mobile / webcam)</button> : <label className="btn camera-btn">📷 Take photo<input type="file" accept="image/*" capture="environment" hidden onChange={up} /></label>}<label className="btn">🖨 Add from scanner / computer<input type="file" multiple accept="image/*,.tif,.tiff,.bmp,application/pdf" hidden onChange={up} /></label>{busy && <span className="mute">{prog || "Working…"}</span>}</div>
    <div onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); handle(e.dataTransfer.files); }} className="card" style={{ marginBottom: 10, textAlign: "center", borderStyle: "dashed", borderColor: drag ? "var(--accent)" : undefined }}><b>Using a scanner?</b> Scan to a PDF or image on this computer (most scanners do “Scan to PC / folder”), then click <b>Add from scanner / computer</b> and select the files — or drag them here. You can add many at once. <span className="mute">Best scanner settings: A4, 200–300 dpi, grayscale or black &amp; white, save as PDF or JPEG (TIFF and BMP also work). Files up to 30 MB.</span> On a phone, use <b>Take photo</b>.</div>
    {sel && <Review doc={sel} sups={sups || []} onDone={() => { setSel(null); load(); }} />}
    {meta && <div className="card" style={{ marginBottom: 12 }}><b>Document details</b><div className="row" style={{ marginTop: 6 }}><select value={meta.doc_type} onChange={e => setMeta({ ...meta, doc_type: e.target.value })}>{DTYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
      <input placeholder="Company" value={meta.company || ""} onChange={e => setMeta({ ...meta, company: e.target.value })} /><input placeholder="Reference / number" value={meta.reference || ""} onChange={e => setMeta({ ...meta, reference: e.target.value })} /><input placeholder="Amount €" style={{ width: 90 }} value={meta.amount || ""} onChange={e => setMeta({ ...meta, amount: e.target.value })} />
      <input type="date" value={meta.doc_date || ""} onChange={e => setMeta({ ...meta, doc_date: e.target.value })} /><input placeholder="Order #" style={{ width: 80 }} value={meta.related_order_id || ""} onChange={e => setMeta({ ...meta, related_order_id: e.target.value })} /><input placeholder="Invoice id" style={{ width: 90 }} value={meta.related_invoice_id || ""} onChange={e => setMeta({ ...meta, related_invoice_id: e.target.value })} />
      <select value={meta.status} onChange={e => setMeta({ ...meta, status: e.target.value })}><option value="NEEDS_REVIEW">Needs review</option><option value="VERIFIED">Verified</option></select><button className="p" onClick={saveMeta}>Save</button><button className="s" onClick={() => setMeta(null)}>Cancel</button></div></div>}
    <div className="row"><input placeholder="Search name / company / reference…" value={q} onChange={e => setQ(e.target.value)} style={{ minWidth: 240 }} /><select value={ft} onChange={e => setFt(e.target.value)}><option value="">All types</option>{DTYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
      <select value={st} onChange={e => setSt(e.target.value)}><option value="">Any status</option><option value="NEEDS_REVIEW">Needs review</option><option value="VERIFIED">Verified</option></select></div>
    {docs && <Table cols={[["#", r => r.id], ["Type", r => DTYPES.find(d => d[0] === r.doc_type)?.[1] || r.doc_type], ["File", r => <a href="#" onClick={e => { e.preventDefault(); openFile(r.id); }}>{r.filename}</a>], ["Company", r => r.company], ["Ref", r => r.reference], ["Amount", r => r.amount_cents != null ? eur(r.amount_cents) : ""], ["Date", r => r.doc_date], ["Source", r => r.source], ["Status", r => <Tag s={r.status} />],
      ["", r => <span className="row" style={{ margin: 0 }}><button className="s" onClick={() => setMeta({ ...r, amount: r.amount_cents != null ? (r.amount_cents / 100).toFixed(2) : "" })}>Details</button>{r.status === "NEEDS_REVIEW" && ["receipt", "invoice"].includes(r.doc_type) && <button className="s" onClick={() => setSel(r)}>Review</button>}</span>]]} rows={docs} />}</>;
}

function Review({ doc, sups, onDone }) {
  const x = doc.extracted || {}, [f, setF] = useState({ supplier: x.supplier || "", number: x.number || "", date: x.date || today(), total: x.total || "", vat: x.vat || "", kind: doc.doc_type === "invoice" ? "invoice" : "expense", category: "Food supplies", supplier_id: "", loc: "", stock: false }), [items, setItems] = useState((x.items || []).map(i => ({ pid: "", description: i.description || "", qty: i.quantity || 1, cost: i.unit_price || "" }))), [err, setErr] = useState("");
  const [prods] = useData("/products"), [locs] = useData("/locations");
  useEffect(() => { api("/scan/suggest", { method: "POST", body: { supplier: x.supplier || "", items: x.items || [] } }).then(s => { if (s.supplier_id) setF(v => ({ ...v, supplier_id: String(s.supplier_id) })); setItems((x.items || []).map((i, k) => ({ pid: s.items[k]?.product_id ? String(s.items[k].product_id) : "", description: i.description || "", qty: i.quantity || 1, cost: i.unit_price || "" }))); }).catch(() => {}); }, []);
  async function save() {
    try {
      if (f.kind === "invoice") await api("/invoices", { method: "POST", body: { supplier_id: +f.supplier_id, number: f.number, issue_date: f.date, total_cents: cents(f.total), vat_cents: cents(f.vat), document_id: doc.id, location_id: f.loc ? +f.loc : null, add_to_stock: f.stock && !!f.loc, items: items.filter(i => i.pid).map(i => ({ product_id: +i.pid, description: i.description, quantity: +i.qty, unit_cents: cents(i.cost) })) } });
      else await api("/expenses", { method: "POST", body: { category: f.category, description: f.supplier, amount_cents: cents(f.total), vat_cents: cents(f.vat), spent_on: f.date, document_id: doc.id } });
      onDone();
    } catch (e) { setErr(e.message); }
  }
  const set = k => e => setF({ ...f, [k]: e.target.value });
  return <div className="card" style={{ marginBottom: 14 }}><b>Check the extracted data before saving</b> {x.confidence != null && <span className="mute">(OCR confidence {x.confidence}%)</span>} {x.note && <div className="mute">{x.note}</div>}<Err e={err} />
    <p><a href="#" onClick={e => { e.preventDefault(); openFile(doc.id); }}>View the original</a></p>
    <div className="row"><select value={f.kind} onChange={set("kind")}><option value="expense">Save as expense (receipt)</option><option value="invoice">Save as supplier invoice</option></select><input placeholder="Merchant / supplier" value={f.supplier} onChange={set("supplier")} />
      {f.kind === "invoice" && <><select value={f.supplier_id} onChange={set("supplier_id")}><option value="">Pick supplier…</option>{sups.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select><input placeholder="Invoice no." value={f.number} onChange={set("number")} /></>}
      {f.kind === "expense" && <input placeholder="Category" value={f.category} onChange={set("category")} />}<input type="date" value={f.date} onChange={set("date")} /><input placeholder="Total €" style={{ width: 90 }} value={f.total} onChange={set("total")} /><input placeholder="VAT €" style={{ width: 80 }} value={f.vat} onChange={set("vat")} /></div>
    {f.kind === "invoice" && <>{items.map((it, i) => <div className="row" key={i}><span style={{ minWidth: 160 }}>{it.description}</span><select value={it.pid} onChange={e => setItems(items.map((y, j) => j === i ? { ...y, pid: e.target.value } : y))}><option value="">Not a stock product</option>{(prods || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select><span className="mute">×{it.qty} @ {it.cost}</span></div>)}
      <div className="row"><select value={f.loc} onChange={set("loc")}><option value="">Received at…</option>{(locs || []).map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select><label><input type="checkbox" checked={f.stock} onChange={e => setF({ ...f, stock: e.target.checked })} /> Add matched items to stock</label></div></>}
    <div className="row"><button className="p" onClick={save}>Verify & save</button><button className="s" onClick={onDone}>Later</button></div></div>;
}

/* ---------------- Orders extras: refund + till CSV import ---------------- */
export function OrderTools({ order, onDone }) {
  const [e, setE] = useState("");
  async function refund() { const v = prompt(`Refund amount in EUR (max ${(order.total_cents / 100).toFixed(2)})`, (order.total_cents / 100).toFixed(2)); if (!v) return; const why = prompt("Reason?") || ""; try { await api(`/orders/${order.id}/refund`, { method: "POST", body: { amount_cents: cents(v), reason: why, restock: confirm("Put the items back into stock?") } }); onDone(); } catch (x) { alert(x.message); } }
  return order.status === "PAID" ? <button className="s" onClick={refund}>Refund</button> : null;
}
export function TillImport({ loc, locs, onDone }) {
  const [msg, setMsg] = useState("");
  async function up(ev) { const file = ev.target.files[0]; if (!file) return; const fd = new FormData(); fd.append("file", file); fd.append("location_id", loc || locs[0]?.id); try { const r = await api("/orders/import-csv", { method: "POST", body: fd }); setMsg(`Imported ${r.added} sale line(s), skipped ${r.skipped_duplicates} duplicates${r.errors.length ? `, ${r.errors.length} unreadable` : ""}.`); onDone(); } catch (x) { setMsg(x.message); } ev.target.value = ""; }
  return <div className="row"><span>Import till / POS sales CSV (date, amount, method):</span><input type="file" accept=".csv" onChange={up} /><span className="mute">{msg}</span></div>;
}

/* ---------------- Data & backups ---------------- */
export function DataPage() {
  const [b, load, err] = useData("/backups"), [msg, setMsg] = useState(""), [e2, run] = useRun(load);
  const go = run(async () => { const r = await api("/backups/run", { method: "POST" }); setMsg("Backup created: " + r.name); });
  const dl = (p, n) => download(p, n).catch(x => setMsg(x.message));
  return <><h1>Your data & backups</h1><Err e={e2} />{msg && <div className="card" style={{ marginBottom: 10 }}>{msg}</div>}
    <p className="mute">Your data belongs to you. Download everything (data as CSV, and your uploaded documents) whenever you like. Passwords and security keys are never included. The service also keeps its own nightly backups.</p>
    <div className="row">{b && <button className="p" onClick={go}>Back up now</button>}<button className="s" onClick={() => dl("/export/all.zip", "flowmate-data.zip")}>Download all data (CSV)</button><button className="s" onClick={() => dl("/export/documents.zip", "flowmate-documents.zip")}>Download all documents</button></div>
    {b && <Table cols={[["Backup", r => r.name], ["Made", r => r.at.replace("T", " ")], ["Size", r => (r.bytes / 1024).toFixed(0) + " KB"], ["", r => <button className="s" onClick={() => dl(`/backups/${r.name}`, r.name)}>Download</button>]]} rows={b} />}
    {b && !b.length && <p className="mute">No backups yet.</p>}
    <p className="mute" style={{ marginTop: 12 }}>Keep a copy somewhere else too (your computer or cloud drive) - download your data regularly.</p></>;
}

/* ---------------- Two-step sign-in: the user CHOOSES: authenticator app or text-message code ---------------- */
export function MfaSetup({ forced, onDone, user }) {
  const [method, setMethod] = useState(null), [cfg] = useData("/config"), [err, setErr] = useState(""), [codes, setCodes] = useState(null);
  if (codes) return <div className="login"><h1>Save your recovery codes</h1><div className="mute">Each works once if you lose your phone. They are shown only now. Write them on paper.</div><pre style={{ fontSize: 16 }}>{codes.join("\n")}</pre><button className="p" onClick={onDone}>I saved them</button></div>;
  if (!method) return <div className="login"><h1>{forced ? "Two-step login is required" : "Turn on two-step login"}</h1>
    <div className="mute">After your password you confirm with a code. Choose how you want to receive it:</div>
    <button className="p" style={{ textAlign: "left", padding: 14 }} onClick={() => setMethod("app")}>🔐 <b>Authenticator app</b><br /><span style={{ fontSize: 12, opacity: .85 }}>Most secure. Free. Works without signal. Google or Microsoft Authenticator.</span></button>
    <button className="s" style={{ textAlign: "left", padding: 14 }} disabled={!cfg?.sms_available} onClick={() => setMethod("sms")}>💬 <b>Text message (SMS)</b><br /><span className="mute" style={{ fontSize: 12 }}>{cfg?.sms_available ? "Easiest. We text a 6-digit code to your mobile each time you log in." : "Not set up on this server yet (the owner needs to connect an SMS service)."}</span></button>
    {!forced && <button className="s" onClick={onDone}>Not now</button>}</div>;
  return method === "app" ? <AppSetup forced={forced} err={err} setErr={setErr} setCodes={setCodes} back={() => setMethod(null)} /> : <SmsSetup user={user} setCodes={setCodes} back={() => setMethod(null)} />;
}

function AppSetup({ setCodes, back, err, setErr }) {
  const [s, setS] = useState(null), [code, setCode] = useState(""), [qr, setQr] = useState("");
  useEffect(() => { api("/auth/mfa/setup", { method: "POST" }).then(setS).catch(x => setErr(x.message)); }, []);
  useEffect(() => { if (s) import("qrcode").then(m => (m.default || m).toDataURL(s.otpauth, { width: 180, margin: 1 })).then(setQr).catch(() => {}); }, [s]);
  async function enable() { try { setCodes((await api("/auth/mfa/enable", { method: "POST", body: { code } })).recovery_codes); } catch (x) { setErr(x.message); } }
  return <div className="login"><h1>Authenticator app</h1><div className="mute">Scan with Google Authenticator / Microsoft Authenticator / Authy, or type the key in manually.</div><Err e={err} />
    {s && <>{qr && <img alt="QR code" width={180} height={180} src={qr} style={{ alignSelf: "center", background: "#fff", padding: 6, borderRadius: 8 }} />}<div className="mute" style={{ fontSize: 12 }}>On the same phone? Skip the QR and copy this key into your authenticator app (“Enter a setup key”).</div><code style={{ wordBreak: "break-all" }}>{s.secret}</code>
      <input placeholder="6-digit code" value={code} onChange={e => setCode(e.target.value)} inputMode="numeric" /><button className="p" disabled={code.length < 6} onClick={enable}>Confirm and turn on</button></>}
    <button className="s" onClick={back}>← Choose another way</button></div>;
}

function SmsSetup({ user, setCodes, back }) {
  const [phone, setPhone] = useState(user?.phone || ""), [sent, setSent] = useState(""), [code, setCode] = useState(""), [err, setErr] = useState("");
  async function send() { try { setErr(""); setSent((await api("/auth/mfa/sms/start", { method: "POST", body: { phone } })).sent_to); } catch (x) { setErr(x.message); } }
  async function enable() { try { setCodes((await api("/auth/mfa/sms/enable", { method: "POST", body: { code } })).recovery_codes); } catch (x) { setErr(x.message); } }
  return <div className="login"><h1>Text-message code</h1><div className="mute">Enter your mobile number. We send a code to check it is yours.</div><Err e={err} />
    <input placeholder="+357 96 123456" value={phone} onChange={e => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" />
    {!sent ? <button className="p" disabled={phone.length < 8} onClick={send}>Send me a code</button> : <>
      <div className="mute">Code sent to {sent}. It is valid for 5 minutes.</div><input placeholder="6-digit code" value={code} onChange={e => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" />
      <button className="p" disabled={code.length < 6} onClick={enable}>Confirm and turn on</button><button className="s" onClick={send}>Send again</button></>}
    <button className="s" onClick={back}>← Choose another way</button></div>;
}

export function Security({ user, reload }) {
  const [e, setE] = useState(""), [setup, setSetup] = useState(false), [st, loadSt] = useData("/settings"), admin = ["owner", "admin"].includes(user.role);
  if (setup) return <MfaSetup user={user} onDone={() => { setSetup(false); reload(); }} />;
  async function off() { const pw = prompt("Your password"), code = pw && (user.mfa_method === "sms" ? "-" : prompt("Current 6-digit code")); if (!code) return; try { await api("/auth/mfa/disable", { method: "POST", body: { password: pw, code: code === "-" ? "" : code } }); reload(); } catch (x) { setE(x.message); } }
  async function out() { try { await api("/auth/logout-all", { method: "POST" }); localStorage.removeItem("token"); location.reload(); } catch (x) { setE(x.message); } }
  async function policy(v) { try { await api("/settings", { method: "PUT", body: { mfa_policy: v } }); loadSt(); } catch (x) { setE(x.message); } }
  return <><h1 style={{ fontSize: 16, marginTop: 18 }}>My security</h1><Err e={e} />
    <div className="row"><span>Two-step login: <b className={user.totp_enabled ? "good" : "warn"}>{user.totp_enabled ? `ON (${user.mfa_method === "sms" ? "text message" : "authenticator app"})` : "OFF"}</b></span>{user.totp_enabled ? <button className="s" onClick={off}>Turn off</button> : <button className="p" onClick={() => setSetup(true)}>Turn on</button>}<button className="s" onClick={out}>Log out everywhere</button></div>
    {admin && st && <div className="row"><span>Two-step login for owners and payment staff:</span><select value={st.mfa_policy} onChange={ev => policy(ev.target.value)}><option value="optional">Optional (each person chooses)</option><option value="required">Required (recommended when real money is approved)</option></select></div>}
    {!user.totp_enabled && <div className="mute" style={{ fontSize: 12 }}>Two-step login protects your account even if someone learns your password. Recommended for anyone who approves payments.</div>}</>;
}

/* ---------------- Global search ---------------- */
export function GlobalSearch({ go }) {
  const [q, setQ] = useState(""), [r, setR] = useState([]), [open, setOpen] = useState(false);
  useEffect(() => { if (q.trim().length < 2) { setR([]); return; } const t = setTimeout(() => api("/search?q=" + encodeURIComponent(q)).then(x => { setR(x); setOpen(true); }).catch(() => {}), 250); return () => clearTimeout(t); }, [q]);
  return <div className="srch"><input placeholder="Search customers, suppliers, invoices…" value={q} onChange={e => setQ(e.target.value)} onFocus={() => r.length && setOpen(true)} style={{ minWidth: 230 }} />
    {open && q.trim().length >= 2 && <div className="card pop">{r.length ? r.map((x, i) => <button key={i} className="hit" onClick={() => { go(x.tab); setOpen(false); setQ(""); }}><b>{x.label}</b> <span className="mute">· {x.kind}{x.sub ? " · " + x.sub : ""}</span></button>) : <div className="mute">No results.</div>}<button className="s" style={{ marginTop: 6 }} onClick={() => setOpen(false)}>Close</button></div>}</div>;
}

/* ---------------- Payments (supplier payment queue) ---------------- */
export function Payments({ user }) {
  const [pays, load, err] = useData("/payments"), [e2, run] = useRun(load);
  const approver = user.perms.includes("*") || user.perms.includes("payments_approve");
  const approve = run(async p => { const r = await api(`/payments/${p.id}/approve`, { method: "POST" }); if (r.authorization_url) window.open(r.authorization_url); });
  const reject = run(p => { const why = prompt("Reason for rejecting?"); if (why !== null) return api(`/payments/${p.id}/reject`, { method: "POST", body: { reason: why } }); });
  const waiting = (pays || []).filter(p => p.status === "PENDING");
  return <><h1>Supplier payments</h1><Err e={err || e2} />
    <p className="mute">Flow: prepare on the invoice → owner approves → pay in your bank's own app → the bank statement completes it automatically.</p>
    {waiting.length > 0 && <div className="card" style={{ marginBottom: 12, borderColor: "var(--warn)" }}><b>Awaiting approval ({waiting.length})</b><Table cols={[["Supplier", r => r.supplier], ["Invoice", r => r.invoice_number], ["Amount", r => eur(r.amount_cents)], ["Prepared by", r => r.prepared_by], ["", r => approver ? <span className="row" style={{ margin: 0 }}><button className="p" onClick={() => approve(r)}>Approve</button><button className="s" onClick={() => reject(r)}>Reject</button></span> : <span className="mute">owner must approve</span>]]} rows={waiting} /></div>}
    {pays && <Table cols={[["#", r => r.id], ["Supplier", r => r.supplier], ["Invoice", r => r.invoice_number], ["Amount", r => eur(r.amount_cents)], ["Status", r => <Tag s={r.status} />], ["", r => ["APPROVED", "AUTHORIZATION_REQUIRED", "PROCESSING"].includes(r.status) && <span className="row" style={{ margin: 0 }}>{r.authorization_url && <a className="btn" href={r.authorization_url} target="_blank" rel="noreferrer">Bank approval</a>}<button className="s" onClick={run(() => api(`/payments/${r.id}/refresh`, { method: "POST" }))}>Check status</button></span>]]} rows={pays} />}
    {pays && !pays.length && <p className="mute">No payments yet. Open an invoice and press "Prepare payment".</p>}</>;
}

/* ---------------- My account: delete (required by Google Play and the App Store) ---------------- */
export function Account({ user }) {
  const owner = user.role === "owner", [pw, setPw] = useState(""), [name, setName] = useState(""), [err, setErr] = useState(""), [open, setOpen] = useState(false);
  async function go() { try { await api(owner ? "/account/delete-business" : "/account/delete-me", { method: "POST", body: owner ? { password: pw, confirm_name: name } : { password: pw } }); localStorage.removeItem("token"); alert("Your account has been deleted."); location.reload(); } catch (x) { setErr(x.message); } }
  return <><h1>My account</h1><p className="mute">{user.name} · {user.email} · {user.role}</p>
    <p><a href="/privacy" target="_blank">Privacy policy</a> · <a href="/terms" target="_blank">Terms</a></p>
    <h1 style={{ fontSize: 16, marginTop: 20 }}>Delete account</h1>
    {!open ? <button className="s" onClick={() => setOpen(true)}>{owner ? "Delete my business and all its data…" : "Delete my login…"}</button> :
      <div className="card"><b className="bad">{owner ? "This permanently deletes the whole business: all orders, stock, invoices, documents and every staff login. It cannot be undone. Download your data first (Data page)." : "This removes your login. Records you created for the business stay, without your name."}</b>
        <Err e={err} /><div className="row"><input type="password" placeholder="Your password" value={pw} onChange={e => setPw(e.target.value)} />{owner && <input placeholder="Type the business name to confirm" value={name} onChange={e => setName(e.target.value)} />}<button className="p" style={{ background: "var(--bad,#c0392b)" }} disabled={!pw || (owner && !name)} onClick={go}>Delete permanently</button><button className="s" onClick={() => setOpen(false)}>Cancel</button></div></div>}</>;
}
