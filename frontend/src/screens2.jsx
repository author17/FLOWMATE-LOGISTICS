import React, { useEffect, useState, useCallback } from "react";
import { api, eur, cents, download } from "./api.js";
import { useData, Err, Tag, Table, Card, PayLink } from "./ui.jsx";
import { BankConnections } from "./bank.jsx";
import { Security } from "./screens3.jsx";

export function Customers() {
  const [q, setQ] = useState(""), [rows, load, err] = useData("/customers" + (q ? `?q=${encodeURIComponent(q)}` : "")), [f, setF] = useState({ name: "", email: "", phone: "" }), [e2, setE2] = useState(""), [open, setOpen] = useState(null);
  const add = async () => { try { await api("/customers", { method: "POST", body: f }); setF({ name: "", email: "", phone: "" }); setE2(""); load(); } catch (x) { setE2(x.message); } };
  if (open) return <CustomerProfile id={open} onBack={() => setOpen(null)} />;
  return <><h1>Customers</h1><Err e={err || e2} /><div className="row"><input placeholder="Search customers…" value={q} onChange={e => setQ(e.target.value)} /></div>
    <div className="row">{["name", "email", "phone"].map(k => <input key={k} placeholder={k} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} />)}<button className="p" disabled={!f.name} onClick={add}>Add customer</button></div>
    {rows && <Table cols={[["Name", r => <a href="#" onClick={e => { e.preventDefault(); setOpen(r.id); }}>{r.name}</a>], ["Email", r => r.email], ["Phone", r => r.phone]]} rows={rows} />}</>;
}
function CustomerProfile({ id, onBack }) {
  const [p, , err] = useData(`/customers/${id}/profile`);
  if (!p) return <><Err e={err} /><p>Loading…</p></>;
  return <><button className="s" onClick={onBack}>← Customers</button><h1 style={{ marginTop: 10 }}>{p.customer.name}</h1><p className="mute">{p.customer.email} {p.customer.phone}</p>
    <div className="cards"><Card l="Paid" v={eur(p.paid_cents)} cls="good" /><Card l="Owes" v={eur(p.owed_cents)} cls={p.owed_cents ? "warn" : ""} /><Card l="Refunded" v={eur(p.refunded_cents)} /></div>
    <Table cols={[["#", r => r.id], ["Date", r => r.created_at?.slice(0, 10)], ["Items", r => r.items.map(i => `${i.description} ×${i.quantity}`).join(", ")], ["Total", r => eur(r.total_cents)], ["Status", r => <Tag s={r.status} />]]} rows={p.orders} /></>;
}

export function Products({ user }) {
  const [rows, load, err] = useData("/products"), [sups] = useData("/suppliers"), [stock] = useData("/stock"), [cats, loadCats] = useData("/categories"), [e2, setE2] = useState("");
  const edit = user.perms.includes("*") || user.perms.includes("products");
  const [f, setF] = useState({ sku: "", name: "", purchase: "", sell: "", vat: "19", min: "0", max: "0", cat: "", sup: "" });
  const add = async () => { try { await api("/products", { method: "POST", body: { sku: f.sku, name: f.name, purchase_cents: cents(f.purchase), sell_cents: cents(f.sell), vat_percent: +f.vat, min_stock: +f.min, max_stock: +f.max, category_id: f.cat ? +f.cat : null, supplier_id: f.sup ? +f.sup : null } }); setF({ sku: "", name: "", purchase: "", sell: "", vat: "19", min: "0", max: "0", cat: "", sup: "" }); setE2(""); load(); } catch (x) { setE2(x.message); } };
  const qty = id => (stock || []).filter(s => s.product_id === id).reduce((a, s) => a + s.quantity, 0);
  const price = async (p) => { const v = prompt("New selling price in EUR", (p.sell_cents / 100).toFixed(2)); if (v) { await api(`/products/${p.id}`, { method: "PUT", body: { sell_cents: cents(v) } }); load(); } };
  return <><h1>Products</h1><Err e={err || e2} />{edit && <div className="row"><button className="s" onClick={async () => { const n = prompt("New category name"); if (n) { await api("/categories", { method: "POST", body: { name: n } }); loadCats(); } }}>+ Category</button></div>}
    {edit && <div className="row"><input placeholder="SKU" style={{ width: 90 }} value={f.sku} onChange={e => setF({ ...f, sku: e.target.value })} /><input placeholder="Name" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} />
      <input placeholder="Cost €" style={{ width: 80 }} value={f.purchase} onChange={e => setF({ ...f, purchase: e.target.value })} /><input placeholder="Price €" style={{ width: 80 }} value={f.sell} onChange={e => setF({ ...f, sell: e.target.value })} />
      <input placeholder="VAT %" style={{ width: 70 }} value={f.vat} onChange={e => setF({ ...f, vat: e.target.value })} /><input placeholder="Min stock" style={{ width: 90 }} value={f.min} onChange={e => setF({ ...f, min: e.target.value })} /><input placeholder="Max stock" style={{ width: 90 }} value={f.max} onChange={e => setF({ ...f, max: e.target.value })} /><select value={f.cat} onChange={e => setF({ ...f, cat: e.target.value })}><option value="">Category…</option>{(cats || []).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
      <select value={f.sup} onChange={e => setF({ ...f, sup: e.target.value })}><option value="">Supplier…</option>{(sups || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select><button className="p" disabled={!f.sku || !f.name} onClick={add}>Add product</button></div>}
    {rows && <Table cols={[["SKU", r => r.sku], ["Name", r => r.name], ["Cost", r => eur(r.purchase_cents)], ["Price", r => eur(r.sell_cents)], ["VAT", r => r.vat_percent + "%"], ["In stock", r => qty(r.id)], ["Min", r => r.min_stock], ["Max", r => r.max_stock || "—"], ["Online", r => <input type="checkbox" disabled={!edit} checked={!!r.show_online} onChange={async e => { await api(`/products/${r.id}`, { method: "PUT", body: { show_online: e.target.checked } }); load(); }} />], ["", r => edit && <button className="s" onClick={() => price(r)}>Change price</button>]]} rows={rows} />}</>;
}

export function Expenses({ locs }) {
  const [rows, load, err] = useData("/expenses"), [e2, setE2] = useState(""), today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ category: "Food supplies", amount: "", vat: "", date: today, desc: "", method: "CASH", loc: "" });
  const CATS = ["Food supplies", "Electricity", "Rent", "Equipment", "Fuel", "Internet", "Telephone", "Maintenance", "Advertising", "Bank fees", "Salaries", "Other"];
  const add = async () => { try { await api("/expenses", { method: "POST", body: { category: f.category, amount_cents: cents(f.amount), vat_cents: cents(f.vat), spent_on: f.date, description: f.desc, payment_method: f.method, location_id: f.loc ? +f.loc : null } }); setF({ ...f, amount: "", vat: "", desc: "" }); setE2(""); load(); } catch (x) { setE2(x.message); } };
  return <><h1>Expenses</h1><Err e={err || e2} /><div className="row"><select value={f.category} onChange={e => setF({ ...f, category: e.target.value })}>{CATS.map(c => <option key={c}>{c}</option>)}</select>
    <input placeholder="Amount €" style={{ width: 90 }} value={f.amount} onChange={e => setF({ ...f, amount: e.target.value })} /><input placeholder="VAT €" style={{ width: 80 }} value={f.vat} onChange={e => setF({ ...f, vat: e.target.value })} /><input type="date" value={f.date} onChange={e => setF({ ...f, date: e.target.value })} />
    <select value={f.method} onChange={e => setF({ ...f, method: e.target.value })}>{["CASH", "CARD", "BANK_TRANSFER", "ONLINE", "OTHER"].map(m => <option key={m}>{m}</option>)}</select>
    <select value={f.loc} onChange={e => setF({ ...f, loc: e.target.value })}><option value="">All / general</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select>
    <input placeholder="Note" value={f.desc} onChange={e => setF({ ...f, desc: e.target.value })} /><button className="p" disabled={!f.amount} onClick={add}>Add expense</button></div>
    <p className="mute">Tip: to attach a receipt photo, use Scan → Receipt and save it as an expense.</p>
    {rows && <Table cols={[["Date", r => r.spent_on], ["Category", r => r.category], ["Note", r => r.description], ["Location", r => locs.find(l => l.id === r.location_id)?.name || ""], ["Method", r => r.payment_method], ["Amount", r => eur(r.amount_cents)], ["Receipt", r => r.document_id ? "attached" : ""]]} rows={rows} />}</>;
}

export function Members({ loc, locs, user }) {
  const [sum, loadS] = useData("/memberships/summary" + (loc ? `?location_id=${loc}` : "")), [filter, setFilter] = useState(""), [q, setQ] = useState("");
  const [rows, load, err] = useData("/members?" + new URLSearchParams({ ...(q && { q }), ...(filter && { status: filter }), ...(loc && { location_id: loc }) })), [plans] = useData("/plans"), [sel, setSel] = useState(null), [e2, setE2] = useState(""), [msg, setMsg] = useState("");
  const [nm, setNm] = useState({ name: "", phone: "", email: "" }), [sell, setSell] = useState({ plan_id: "", pay: "", method: "CASH" });
  const [stripe] = useData("/stripe/status"), [link, setLink] = useState(null);
  const refresh = () => { load(); loadS(); };
  const run = fn => async (...a) => { try { await fn(...a); setE2(""); refresh(); } catch (x) { setE2(x.message); } };
  const add = run(async () => { await api("/members", { method: "POST", body: { ...nm, location_id: loc || locs[0]?.id } }); setNm({ name: "", phone: "", email: "" }); });
  const doSell = run(async m => { await api(`/members/${m.id}/subscriptions`, { method: "POST", body: { plan_id: +sell.plan_id, pay_cents: cents(sell.pay), method: sell.method, location_id: loc || m.location_id } }); setSell({ plan_id: "", pay: "", method: "CASH" }); setSel(null); });
  const checkin = run(async m => { const r = await api(`/members/${m.id}/checkin`, { method: "POST", body: { location_id: loc || m.location_id } }); setMsg(`${r.member} checked in.` + (r.warnings.length ? " ⚠ " + r.warnings.join("; ") : "") + (r.sessions_left != null ? ` Sessions left: ${r.sessions_left}` : "")); });
  const payBal = run(async (s) => { const v = prompt(`Amount received (balance ${eur(s.balance_cents)})`, (s.balance_cents / 100).toFixed(2)); if (v) await api(`/subscriptions/${s.id}/payments`, { method: "POST", body: { amount_cents: cents(v), method: "CASH" } }); });
  const onlineLink = run(async s => { const r = await api("/stripe/checkout", { method: "POST", body: { target_type: "subscription", target_id: s.id } }); setLink(r.url); });
  return <><h1>Gym members</h1><Err e={err || e2} />{msg && <div className="card" style={{ marginBottom: 10 }}>{msg}</div>}{link && <PayLink url={link} onClose={() => setLink(null)} />}
    {sum && <div className="cards"><Card l="Active members" v={sum.active} /><Card l="Expired" v={sum.expired} cls={sum.expired ? "warn" : ""} /><Card l="Expiring in 7 days" v={sum.expiring_7d.length} cls={sum.expiring_7d.length ? "warn" : ""} /><Card l="With unpaid balance" v={sum.owing.length} cls={sum.owing.length ? "bad" : ""} /><Card l="Membership income (month)" v={eur(sum.revenue_month_cents)} /><Card l="Check-ins today" v={sum.checkins_today} /></div>}
    <div className="row"><input placeholder="Search name or phone" value={q} onChange={e => setQ(e.target.value)} />{[["", "All"], ["ACTIVE", "Active"], ["EXPIRED", "Expired"], ["OWING", "Owing"], ["NO_PLAN", "No plan"]].map(([v, l]) => <button key={v} className={filter === v ? "p" : "s"} onClick={() => setFilter(v)}>{l}</button>)}</div>
    <div className="row"><input placeholder="New member name" value={nm.name} onChange={e => setNm({ ...nm, name: e.target.value })} /><input placeholder="Phone" value={nm.phone} onChange={e => setNm({ ...nm, phone: e.target.value })} /><input placeholder="Email" value={nm.email} onChange={e => setNm({ ...nm, email: e.target.value })} /><button className="p" disabled={!nm.name} onClick={add}>Add member</button></div>
    {rows && <Table cols={[["Member", r => <b>{r.name}</b>], ["Phone", r => r.phone], ["Plan", r => r.current_plan], ["Valid until", r => r.valid_until], ["Status", r => <Tag s={r.status} />], ["Owes", r => r.balance_cents > 0 ? <span className="bad">{eur(r.balance_cents)}</span> : ""],
      ["", r => <span className="row" style={{ margin: 0 }}><button className="p" onClick={() => checkin(r)}>Check in</button><button className="s" onClick={() => setSel(sel?.id === r.id ? null : r)}>Sell / renew</button>
        {r.subscriptions.filter(s => s.balance_cents > 0 && s.state !== "CANCELLED").slice(0, 1).map(s => <React.Fragment key={s.id}><button className="s" onClick={() => payBal(s)}>Take payment</button>{stripe?.configured && <button className="s" onClick={() => onlineLink(s)}>Pay link</button>}</React.Fragment>)}</span>]]} rows={rows} />}
    {sel && <div className="card" style={{ marginTop: 12 }}><b>Sell or renew for {sel.name}</b><div className="row" style={{ marginTop: 8 }}><select value={sell.plan_id} onChange={e => setSell({ ...sell, plan_id: e.target.value })}><option value="">Plan…</option>{(plans || []).filter(p => p.active).map(p => <option key={p.id} value={p.id}>{p.name} · {eur(p.price_cents)}</option>)}</select>
      <input placeholder="Paid now €" style={{ width: 100 }} value={sell.pay} onChange={e => setSell({ ...sell, pay: e.target.value })} /><select value={sell.method} onChange={e => setSell({ ...sell, method: e.target.value })}>{["CASH", "CARD", "BANK_TRANSFER", "OTHER"].map(m => <option key={m}>{m}</option>)}</select>
      <button className="p" disabled={!sell.plan_id} onClick={() => doSell(sel)}>Confirm</button></div><div className="mute">Renewing early starts after the current end date, so no days are lost.</div></div>}
    {sum?.expiring_7d.length > 0 && <><h1 style={{ marginTop: 18 }}>Expiring this week</h1><Table cols={[["Member", r => r.name], ["Plan", r => r.plan], ["Ends", r => r.valid_until]]} rows={sum.expiring_7d} /></>}</>;
}

export function Reports({ locs }) {
  const LIST = [["sales", "Sales"], ["ledger", "Accounting ledger (journal)"], ["pnl", "Profit / loss estimate"], ["expenses", "Expenses by category"], ["suppliers", "Supplier spending"], ["outstanding", "Outstanding invoices"], ["customers", "Customer payments"], ["bank", "Bank transactions"], ["cashflow", "Cash flow"], ["vat", "VAT summary"], ["stock", "Stock value"], ["products", "Product sales"], ["shifts", "Cash-up differences"]];
  const today = new Date(), m0 = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10), t0 = today.toISOString().slice(0, 10);
  const [f, setF] = useState({ name: "sales", from: m0, to: t0, loc: "", period: "day" }), [data, setData] = useState(null), [err, setErr] = useState("");
  const qs = fmt => `/reports/${f.name}?` + new URLSearchParams({ fmt, date_from: f.from, date_to: f.to, period: f.period, ...(f.loc && { location_id: f.loc }) });
  const run = () => api(qs("json")).then(d => { setData(d); setErr(""); }).catch(e => setErr(e.message));
  useEffect(() => { run(); }, [f.name, f.from, f.to, f.loc, f.period]);
  const dl = async fmt => { try { await download(qs(fmt), `${f.name}_${f.from}_${f.to}.${fmt}`); } catch (e) { setErr(e.message); } };
  return <><h1>Reports</h1><Err e={err} /><div className="row"><select value={f.name} onChange={e => setF({ ...f, name: e.target.value })}>{LIST.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
    <input type="date" value={f.from} onChange={e => setF({ ...f, from: e.target.value })} /><input type="date" value={f.to} onChange={e => setF({ ...f, to: e.target.value })} />
    <select value={f.loc} onChange={e => setF({ ...f, loc: e.target.value })}><option value="">All locations</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select>
    {f.name === "sales" && <select value={f.period} onChange={e => setF({ ...f, period: e.target.value })}><option value="day">Daily</option><option value="week">Weekly</option><option value="month">Monthly</option></select>}
    <button className="s" onClick={() => dl("pdf")}>PDF</button><button className="s" onClick={() => dl("xlsx")}>Excel</button><button className="s" onClick={() => dl("csv")}>CSV</button></div>
    {data && <><h1 style={{ fontSize: 16 }}>{data.title} <span className="mute">{data.from} → {data.to}</span></h1><div className="scroll"><table><thead><tr>{data.columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{data.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{String(v)}</td>)}</tr>)}</tbody></table></div>{!data.rows.length && <p className="mute">No data in this period.</p>}</>}</>;
}

export function Assistant() {
  const [q, setQ] = useState(""), [log, setLog] = useState([]), [busy, setBusy] = useState(false);
  const ask = async t => { const question = t || q; if (!question) return; setBusy(true); setQ(""); try { const r = await api("/assistant", { method: "POST", body: { question } }); setLog(l => [{ q: question, a: r.answer }, ...l]); } catch (x) { setLog(l => [{ q: question, a: "Error: " + x.message }, ...l]); } setBusy(false); };
  return <><h1>Business assistant</h1><div className="row">{["Sales last week", "How much did we spend on food this month?", "Which supplier do we owe most?", "Which products are running low?", "Show unpaid invoices", "Which customers haven't paid?", "Today's bank transactions"].map(s => <button key={s} className="s" onClick={() => ask(s)}>{s}</button>)}</div>
    <div className="row"><input style={{ flex: 1, minWidth: 220 }} placeholder="Ask about your business…" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === "Enter" && ask()} /><button className="p" disabled={busy} onClick={() => ask()}>Ask</button></div>
    {log.map((m, i) => <div key={i} className="card" style={{ marginBottom: 8 }}><div className="mute">{m.q}</div><div>{m.a}</div></div>)}<p className="mute">It only answers from your own data and only what your role may see.</p></>;
}

export function Users({ locs }) {
  const [rows, load, err] = useData("/users"), [e2, setE2] = useState(""), ROLES = ["owner", "manager", "employee", "accountant", "bank_payment", "driver", "admin"];
  const [f, setF] = useState({ name: "", email: "", password: "", role: "employee", location_id: "", phone: "" });
  const run = fn => async (...a) => { try { await fn(...a); setE2(""); load(); } catch (x) { setE2(x.message); } };
  const add = run(async () => { await api("/users", { method: "POST", body: { ...f, location_id: f.location_id ? +f.location_id : null } }); setF({ name: "", email: "", password: "", role: "employee", location_id: "", phone: "" }); });
  const edit = run((id, b) => api(`/users/${id}`, { method: "PUT", body: b }));
  const reset = run(async id => { const p = prompt("Temporary password (10+ characters). The user must change it at next login."); if (p) await api(`/users/${id}/reset-password`, { method: "POST", body: { temp_password: p } }); });
  return <><h1>Users & permissions</h1><Err e={err || e2} /><div className="row"><input placeholder="Name" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /><input placeholder="Email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /><input placeholder="Phone" value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} style={{ width: 130 }} />
    <input placeholder="Temporary password (10+)" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /><select value={f.role} onChange={e => setF({ ...f, role: e.target.value })}>{ROLES.map(r => <option key={r}>{r}</option>)}</select>
    <select value={f.location_id} onChange={e => setF({ ...f, location_id: e.target.value })}><option value="">All locations</option>{locs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select><button className="p" disabled={!f.name || !f.email || f.password.length < 10} onClick={add}>Add user</button></div>
    {rows && <Table cols={[["Name", r => r.name], ["Email", r => r.email], ["Phone", r => <input defaultValue={r.phone || ""} style={{ width: 120 }} onBlur={e => e.target.value !== (r.phone || "") && edit(r.id, { phone: e.target.value })} />], ["Role", r => <select value={r.role} onChange={e => edit(r.id, { role: e.target.value })}>{ROLES.map(x => <option key={x}>{x}</option>)}</select>], ["Active", r => <input type="checkbox" checked={r.active} onChange={e => edit(r.id, { active: e.target.checked })} />], ["", r => <button className="s" onClick={() => reset(r.id)}>Reset password</button>]]} rows={rows} />}
    <p className="mute">Roles: owner/admin everything · manager operations & reports · employee orders, cash-up, members · accountant finance & reports · bank_payment prepares payments · driver own deliveries only.</p></>;
}

export function Settings({ user, reload }) {
  const [s, load, err] = useData("/settings"), [st] = useData("/stripe/status"), [f, setF] = useState(null), [msg, setMsg] = useState("");
  useEffect(() => { if (s && !f) setF({ company_name: s.company_name, vat_number: s.vat_number, company_email: s.company_email, company_address: s.company_address, public_orders_enabled: s.public_orders_enabled }); }, [s]);
  const save = async () => { await api("/settings", { method: "PUT", body: f }); setMsg("Saved"); load(); };
  return <><h1>Settings</h1><Err e={err} />{f && <><div className="row"><input placeholder="Company name" value={f.company_name} onChange={e => setF({ ...f, company_name: e.target.value })} /><input placeholder="VAT number" value={f.vat_number} onChange={e => setF({ ...f, vat_number: e.target.value })} />
      <input placeholder="Company e-mail" value={f.company_email} onChange={e => setF({ ...f, company_email: e.target.value })} /><input placeholder="Address" value={f.company_address} onChange={e => setF({ ...f, company_address: e.target.value })} /></div>
      <div className="row"><label><input type="checkbox" checked={f.public_orders_enabled} onChange={e => setF({ ...f, public_orders_enabled: e.target.checked })} /> Let customers order online (public page: <code>/order</code>; choose the products in Products → "Online")</label><button className="p" onClick={save}>Save</button><span className="mute">{msg}</span></div></>}
    <BankConnections />
    <Security user={user} reload={reload} />
    <Plans />
    <h1 style={{ fontSize: 16, marginTop: 18 }}>Connections</h1>{s && st && <Table cols={[["Service", r => r[0]], ["Status", r => r[1]]]} rows={[["Card payments (Stripe)", st.configured ? `ON (${st.mode} mode)${st.webhook_configured ? "" : " - webhook secret missing"}` : "OFF - add STRIPE_SECRET_KEY"], ["Stripe webhook address", st.webhook_url], ["Receipt reading (OCR)", s.ocr_provider === "claude" ? "ON" : "OFF - manual entry (set OCR_PROVIDER=claude)"], ["Mode", s.demo ? "PRACTICE (fake data)" : "REAL"]].map((r, i) => ({ id: i, 0: r[0], 1: r[1] }))} />}
    <p className="mute" style={{ marginTop: 12 }}>Backups and full data export: the Data page.</p></>;
}

function Plans() {
  const [rows, load, err] = useData("/plans"), [e2, setE2] = useState(""), [f, setF] = useState({ name: "", kind: "membership", days: "30", sessions: "", price: "" });
  const KINDS = [["membership", "Membership"], ["class_pack", "Class pack"], ["personal_training", "Personal training"], ["day_pass", "Day pass"]];
  const run = fn => async (...a) => { try { await fn(...a); setE2(""); load(); } catch (x) { setE2(x.message); } };
  const add = run(async () => { await api("/plans", { method: "POST", body: { name: f.name, kind: f.kind, duration_days: +f.days, sessions: f.sessions ? +f.sessions : null, price_cents: cents(f.price) } }); setF({ name: "", kind: "membership", days: "30", sessions: "", price: "" }); });
  const toggle = run((p) => api(`/plans/${p.id}`, { method: "PUT", body: { active: !p.active } }));
  return <><h1 style={{ fontSize: 16, marginTop: 18 }}>Membership plans & packages</h1><Err e={err || e2} />
    <div className="row"><input placeholder="Name (e.g. Monthly)" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /><select value={f.kind} onChange={e => setF({ ...f, kind: e.target.value })}>{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
      <input placeholder="Valid days" style={{ width: 90 }} value={f.days} onChange={e => setF({ ...f, days: e.target.value })} /><input placeholder="Sessions (packs)" style={{ width: 120 }} value={f.sessions} onChange={e => setF({ ...f, sessions: e.target.value })} />
      <input placeholder="Price €" style={{ width: 90 }} value={f.price} onChange={e => setF({ ...f, price: e.target.value })} /><button className="p" disabled={!f.name || !f.price || !+f.days} onClick={add}>Add plan</button></div>
    {rows && <Table cols={[["Plan", r => r.name], ["Type", r => r.kind], ["Days", r => r.duration_days], ["Sessions", r => r.sessions ?? "unlimited"], ["Price", r => eur(r.price_cents)], ["Active", r => <input type="checkbox" checked={r.active} onChange={() => toggle(r)} />]]} rows={rows} />}</>;
}
