import React, { useEffect, useState, useCallback } from "react";
import { api, eur, cents } from "./api.js";

function useData(path) {
  const [d, setD] = useState(null), [err, setErr] = useState("");
  const load = useCallback(() => api(path).then(x => { setD(x); setErr(""); }).catch(e => setErr(e.message)), [path]);
  useEffect(() => { load(); }, [load]);
  return [d, load, err];
}
const Err = ({ e }) => e ? <div className="err">{e}</div> : null;
const Tag = ({ s }) => <span className={"tag " + (["PAID", "COMPLETED", "RECONCILED", "VERIFIED"].includes(s) ? "good" : ["UNMATCHED", "FAILED", "REJECTED", "CANCELLED"].includes(s) ? "bad" : "warn")}>{s}</span>;
const Table = ({ cols, rows }) => <div className="scroll"><table><thead><tr>{cols.map(c => <th key={c[0]}>{c[0]}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={r.id ?? i}>{cols.map(c => <td key={c[0]}>{c[1](r)}</td>)}</tr>)}</tbody></table></div>;
const Card = ({ l, v, cls }) => <div className="card"><div className="l">{l}</div><div className={"v " + (cls || "")}>{v}</div></div>;

export function Dashboard({ loc }) {
  const [d, , err] = useData("/dashboard" + (loc ? `?location_id=${loc}` : ""));
  if (err) return <Err e={err} />; if (!d) return <p>Loading…</p>;
  return <><h1>Dashboard</h1>
    <div className="cards"><Card l="Sales today" v={eur(d.sales_today_cents)} /><Card l="Expenses today" v={eur(d.expenses_today_cents)} /><Card l="Bank balance" v={eur(d.bank_balance_cents)} />
      <Card l="Unpaid invoices" v={`${d.unpaid_invoices} · ${eur(d.unpaid_total_cents)}`} /><Card l="Low stock" v={d.low_stock_items + " items"} cls={d.low_stock_items ? "warn" : ""} />
      <Card l="Orders waiting" v={d.orders_waiting} /><Card l="Deliveries active" v={d.deliveries_active} /><Card l="Failed deliveries" v={d.deliveries_failed} cls={d.deliveries_failed ? "bad" : ""} /><Card l="Docs to verify" v={d.documents_to_verify} /><Card l="Unmatched payments" v={d.unmatched_payments} />
      <Card l="Month sales" v={eur(d.sales_month_cents)} /><Card l="Month expenses" v={eur(d.expenses_month_cents)} /><Card l="Profit estimate" v={eur(d.profit_estimate_month_cents)} cls={d.profit_estimate_month_cents < 0 ? "bad" : "good"} /></div>
    <h1>Per location (this month)</h1>
    <Table cols={[["Location", r => r.location], ["Sales", r => eur(r.sales_cents)], ["Expenses", r => eur(r.expenses_cents)], ["Profit", r => eur(r.profit_cents)]]} rows={d.by_location} /></>;
}

export function Orders({ loc, locs }) {
  const [rows, load, err] = useData("/orders" + (loc ? `?location_id=${loc}` : "")), [products] = useData("/products"), [f, setF] = useState({ pid: "", qty: 1 }), [e2, setE2] = useState("");
  async function add() { try { await api("/orders", { method: "POST", body: { location_id: loc || locs[0]?.id, items: [{ product_id: +f.pid, quantity: +f.qty }] } }); setE2(""); load(); } catch (x) { setE2(x.message); } }
  async function setStatus(id, status) { await api(`/orders/${id}/status`, { method: "PUT", body: { status } }); load(); }
  return <><h1>Orders</h1><Err e={err || e2} />
    <div className="row"><select value={f.pid} onChange={e => setF({ ...f, pid: e.target.value })}><option value="">Product…</option>{(products || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      <input type="number" min="1" value={f.qty} onChange={e => setF({ ...f, qty: e.target.value })} style={{ width: 70 }} /><button className="p" onClick={add} disabled={!f.pid}>New order</button></div>
    {rows && <Table cols={[["#", r => r.id], ["Items", r => r.items.map(i => `${i.description} ×${i.quantity}`).join(", ")], ["Total", r => eur(r.total_cents)], ["Status", r => <Tag s={r.status} />],
      ["", r => r.status !== "PAID" && r.status !== "CANCELLED" && <button className="s" onClick={() => setStatus(r.id, r.status === "NEW" ? "PROCESSING" : r.status === "PROCESSING" ? "COMPLETED" : "PAID")}>Next step</button>]]} rows={rows} />}</>;
}

export function Suppliers() {
  const [rows, load, err] = useData("/suppliers"), [n, setN] = useState("");
  return <><h1>Suppliers</h1><Err e={err} /><div className="row"><input placeholder="New supplier name" value={n} onChange={e => setN(e.target.value)} />
    <button className="p" disabled={!n} onClick={async () => { await api("/suppliers", { method: "POST", body: { name: n } }); setN(""); load(); }}>Add</button></div>
    {rows && <Table cols={[["Name", r => r.name], ["VAT", r => r.vat_number], ["IBAN", r => r.iban], ["Email", r => r.email]]} rows={rows} />}</>;
}

export function Invoices({ locs }) {
  const [rows, load, err] = useData("/invoices"), [sups] = useData("/suppliers"), [accts] = useData("/bank/accounts"), [e2, setE2] = useState("");
  const [f, setF] = useState({ supplier_id: "", number: "", total: "", due: "" });
  async function add() { try { await api("/invoices", { method: "POST", body: { supplier_id: +f.supplier_id, number: f.number, issue_date: new Date().toISOString().slice(0, 10), due_date: f.due || null, total_cents: cents(f.total) } }); setE2(""); setF({ supplier_id: "", number: "", total: "", due: "" }); load(); } catch (x) { setE2(x.message); } }
  async function pay(i) { try { const p = await api("/payments", { method: "POST", body: { invoice_id: i.id, account_id: accts[0].id } }); alert(`Payment ${p.status}. Approve in your bank: ${p.authorization_url}`); setE2(""); load(); } catch (x) { setE2(x.message); } }
  return <><h1>Supplier invoices</h1><Err e={err || e2} />
    <div className="row"><select value={f.supplier_id} onChange={e => setF({ ...f, supplier_id: e.target.value })}><option value="">Supplier…</option>{(sups || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
      <input placeholder="Invoice no." value={f.number} onChange={e => setF({ ...f, number: e.target.value })} /><input placeholder="Total €" value={f.total} onChange={e => setF({ ...f, total: e.target.value })} style={{ width: 90 }} />
      <input type="date" value={f.due} onChange={e => setF({ ...f, due: e.target.value })} /><button className="p" disabled={!f.supplier_id || !f.number || !f.total} onClick={add}>Add invoice</button></div>
    {rows && <Table cols={[["Supplier", r => r.supplier_name], ["Invoice", r => r.number], ["Due", r => r.due_date], ["Total", r => eur(r.total_cents)], ["Status", r => <Tag s={r.status} />],
      ["", r => r.status === "UNPAID" && accts?.length > 0 && <button className="s" onClick={() => pay(r)}>PAY {eur(r.total_cents)}</button>]]} rows={rows} />}</>;
}

export function Scan({ loc, locs }) {
  const [docs, load, err] = useData("/documents"), [sups] = useData("/suppliers"), [dtype, setDtype] = useState("receipt"), [busy, setBusy] = useState(false), [e2, setE2] = useState(""), [sel, setSel] = useState(null);
  async function up(ev) {
    const file = ev.target.files[0]; if (!file) return; setBusy(true); setE2("");
    const fd = new FormData(); fd.append("file", file); fd.append("doc_type", dtype); if (loc) fd.append("location_id", loc);
    try { const d = await api("/documents/scan", { method: "POST", body: fd }); if (["receipt", "invoice"].includes(dtype)) setSel(d); load(); ev.target.value = ""; } catch (x) { setE2(x.message); } setBusy(false);
  }
  return <><h1>Scan receipts & documents</h1><Err e={err || e2} />
    <div className="row"><select value={dtype} onChange={e => setDtype(e.target.value)}><option value="receipt">Receipt</option><option value="invoice">Supplier invoice</option><option value="statement">Bank statement</option><option value="contract">Contract</option><option value="other">Other document</option></select><input type="file" accept="image/*,application/pdf" capture="environment" onChange={up} />{busy && <span className="mute">Reading…</span>}</div>
    {sel && <Review doc={sel} sups={sups || []} locs={locs} onDone={() => { setSel(null); load(); }} />}
    {docs && <Table cols={[["#", r => r.id], ["Type", r => r.doc_type], ["File", r => <a href={`/api/documents/${r.id}/file`} target="_blank" rel="noreferrer" onClick={e => { e.preventDefault(); openFile(r); }}>{r.filename}</a>], ["Status", r => <Tag s={r.status} />], ["", r => r.status === "NEEDS_REVIEW" && <button className="s" onClick={() => setSel(r)}>Review</button>]]} rows={docs} />}</>;
}
async function openFile(d) { const t = localStorage.getItem("token"); const r = await fetch(`/api/documents/${d.id}/file`, { headers: { Authorization: "Bearer " + t } }); window.open(URL.createObjectURL(await r.blob())); }

function Review({ doc, sups, locs, onDone }) {
  const x = doc.extracted || {}, [f, setF] = useState({ supplier: x.supplier || "", number: x.number || "", date: x.date || new Date().toISOString().slice(0, 10), total: x.total || "", vat: x.vat || "", kind: "expense", category: "Food supplies", supplier_id: "" }), [err, setErr] = useState("");
  const match = sups.find(s => f.supplier && s.name.toLowerCase().includes(f.supplier.toLowerCase().slice(0, 6)));
  async function save() {
    try {
      if (f.kind === "invoice") await api("/invoices", { method: "POST", body: { supplier_id: +(f.supplier_id || match?.id), number: f.number, issue_date: f.date, total_cents: cents(f.total), vat_cents: cents(f.vat), document_id: doc.id } });
      else await api("/expenses", { method: "POST", body: { category: f.category, description: f.supplier, amount_cents: cents(f.total), vat_cents: cents(f.vat), spent_on: f.date, document_id: doc.id } });
      onDone();
    } catch (e) { setErr(e.message); }
  }
  const set = k => e => setF({ ...f, [k]: e.target.value });
  return <div className="card" style={{ marginBottom: 14 }}><b>Check the extracted data before saving</b> {x.confidence != null && <span className="mute">(OCR confidence {x.confidence}%)</span>} {x.note && <div className="mute">{x.note}</div>}<Err e={err} />
    <div className="row" style={{ marginTop: 10 }}><select value={f.kind} onChange={set("kind")}><option value="expense">Save as expense (receipt)</option><option value="invoice">Save as supplier invoice</option></select>
      <input placeholder="Merchant / supplier" value={f.supplier} onChange={set("supplier")} />
      {f.kind === "invoice" && <><select value={f.supplier_id || match?.id || ""} onChange={set("supplier_id")}><option value="">Pick supplier…</option>{sups.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select><input placeholder="Invoice no." value={f.number} onChange={set("number")} /></>}
      {f.kind === "expense" && <input placeholder="Category" value={f.category} onChange={set("category")} />}
      <input type="date" value={f.date} onChange={set("date")} /><input placeholder="Total €" style={{ width: 90 }} value={f.total} onChange={set("total")} /><input placeholder="VAT €" style={{ width: 80 }} value={f.vat} onChange={set("vat")} />
      <button className="p" onClick={save}>Verify & save</button><button className="s" onClick={onDone}>Later</button></div></div>;
}

export function Banking() {
  const [txs, load, err] = useData("/bank/transactions"), [accts] = useData("/bank/accounts"), [pays, loadP] = useData("/payments"), [msg, setMsg] = useState(""), [e2, setE2] = useState("");
  async function imp(ev) { const file = ev.target.files[0]; if (!file) return; const fd = new FormData(); fd.append("file", file); try { const r = await api(`/bank/accounts/${accts[0].id}/import-csv`, { method: "POST", body: fd }); setMsg(`Imported ${r.added} (skipped ${r.skipped_duplicates} duplicates). Auto-reconciled ${r.matching.reconciled}, suggestions ${r.matching.suggested}, unmatched ${r.matching.unmatched}.`); setE2(""); load(); } catch (x) { setE2(x.message); } }
  return <><h1>Banking</h1><Err e={err || e2} />{msg && <div className="card" style={{ marginBottom: 10 }}>{msg}</div>}
    <div className="row"><span>Import bank statement CSV:</span><input type="file" accept=".csv" onChange={imp} disabled={!accts?.length} /></div>
    {txs && <Table cols={[["Date", r => r.booked_on], ["Amount", r => <span className={r.amount_cents < 0 ? "bad" : "good"}>{eur(r.amount_cents)}</span>], ["Reference", r => r.reference], ["Counterparty", r => r.counterparty], ["Status", r => <Tag s={r.match_status} />],
      ["", r => r.match_status === "SUGGESTED" && <button className="s" onClick={async () => { await api(`/bank/transactions/${r.id}/confirm`, { method: "POST" }); load(); }}>Confirm {r.match?.target_type} #{r.match?.target_id}</button>]]} rows={txs} />}
    <h1 style={{ marginTop: 20 }}>Payments to suppliers</h1>
    {pays && <Table cols={[["#", r => r.id], ["Invoice", r => r.invoice_id], ["Amount", r => eur(r.amount_cents)], ["Status", r => <Tag s={r.status} />], ["Bank ref", r => r.provider_ref],
      ["", r => !["COMPLETED", "FAILED", "REJECTED", "CANCELLED"].includes(r.status) && <button className="s" onClick={async () => { await api(`/payments/${r.id}/refresh`, { method: "POST" }); loadP(); }}>Check status</button>]]} rows={pays} />}</>;
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

export function Stock({ loc, locs }) {
  const [rows, load, err] = useData("/stock" + (loc ? `?location_id=${loc}` : "")), [msg, setMsg] = useState("");
  async function po() { try { const r = await api(`/purchase-orders/from-low-stock/${loc || locs[0].id}`, { method: "POST" }); setMsg(`${r.length} draft purchase order(s) created`); } catch (x) { setMsg(x.message); } }
  return <><h1>Stock</h1><Err e={err} /><div className="row"><button className="p" onClick={po}>Create purchase orders for low stock</button><span className="mute">{msg}</span></div>
    {rows && <Table cols={[["SKU", r => r.sku], ["Product", r => r.name], ["Location", r => locs.find(l => l.id === r.location_id)?.name], ["Qty", r => <span className={r.low ? "bad" : ""}>{r.quantity}</span>], ["Min", r => r.min_stock], ["", r => r.low && <Tag s="LOW STOCK" />]]} rows={rows} />}</>;
}

export function Audit() {
  const [rows, , err] = useData("/audit");
  return <><h1>Audit history</h1><Err e={err} />{rows && <Table cols={[["When", r => r.at.slice(0, 19).replace("T", " ")], ["User", r => r.user_name], ["Action", r => r.action], ["Object", r => `${r.object_type} ${r.object_id}`], ["Change", r => <code style={{ fontSize: 11 }}>{JSON.stringify(r.new_value)}</code>]]} rows={rows} />}</>;
}

export function Delivery({ user }) {
  const [rows, load, err] = useData("/deliveries"), [orders] = useData("/orders"), [drivers] = useData("/deliveries/drivers"), [f, setF] = useState({ order_id: "", address: "" }), [e2, setE2] = useState("");
  const staff = user.role !== "driver";
  const wrap = fn => async (...a) => { try { await fn(...a); setE2(""); load(); } catch (x) { setE2(x.message); } };
  const create = wrap(async () => { await api("/deliveries", { method: "POST", body: { order_id: +f.order_id, address: f.address } }); setF({ order_id: "", address: "" }); });
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
      <input placeholder="Delivery address" value={f.address} onChange={e => setF({ ...f, address: e.target.value })} style={{ minWidth: 240 }} /><button className="p" disabled={!f.order_id} onClick={create}>Create delivery</button></div>}
    {rows && <Table cols={[["Order", r => "#" + r.order_id], ["Customer", r => r.customer], ["Address", r => r.address], ["Driver", r => staff && r.status === "PREPARED" ? <select value={r.driver_id || ""} onChange={e => assign(r.id, e.target.value)}><option value="">Assign…</option>{(drivers || []).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select> : r.driver_name], ["Status", r => <Tag s={r.status} />],
      ["", r => <span className="row" style={{ margin: 0 }}>
        {r.status === "PREPARED" && <button className="s" onClick={() => setSt(r.id, "ON_THE_WAY")}>Start delivery</button>}
        {r.status === "ON_THE_WAY" && <><label className="btn">Delivered + photo<input type="file" accept="image/*" capture="environment" hidden onChange={e => proof(r.id, e)} /></label>
          <button className="s" onClick={() => { const why = prompt("Why did it fail?"); if (why) setSt(r.id, "FAILED", why); }}>Failed</button></>}
        {r.status === "FAILED" && <span className="bad">{r.failure_reason}</span>}</span>]]} rows={rows} />}</>;
}
