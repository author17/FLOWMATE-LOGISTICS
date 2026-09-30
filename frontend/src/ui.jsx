import React, { useEffect, useState, useCallback } from "react";
import { api } from "./api.js";
export function useData(path) {
  const [d, setD] = useState(null), [err, setErr] = useState("");
  const load = useCallback(() => api(path).then(x => { setD(x); setErr(""); }).catch(e => setErr(e.message)), [path]);
  useEffect(() => { load(); }, [load]);
  return [d, load, err];
}
export const Err = ({ e }) => e ? <div className="err">{e}</div> : null;
export const Tag = ({ s }) => <span className={"tag " + (["PAID", "COMPLETED", "RECONCILED", "VERIFIED", "ACTIVE", "DELIVERED"].includes(s) ? "good" : ["UNMATCHED", "FAILED", "REJECTED", "CANCELLED", "EXPIRED", "AMOUNT_MISMATCH"].includes(s) ? "bad" : "warn")}>{s}</span>;
export const Table = ({ cols, rows }) => <div className="scroll"><table><thead><tr>{cols.map(c => <th key={c[0]}>{c[0]}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={r.id ?? i}>{cols.map(c => <td key={c[0]}>{c[1](r)}</td>)}</tr>)}</tbody></table></div>;
export const Card = ({ l, v, cls }) => <div className="card"><div className="l">{l}</div><div className={"v " + (cls || "")}>{v}</div></div>;
export function PayLink({ url, onClose }) {
  const [copied, setCopied] = useState(false);
  return <div className="card" style={{ marginBottom: 12 }}><b>Card payment link</b> <span className="mute">— send it to the customer (WhatsApp, SMS, email). It's marked paid automatically when they pay.</span>
    <div className="row" style={{ marginTop: 8 }}><input readOnly value={url} style={{ flex: 1, minWidth: 240 }} onFocus={e => e.target.select()} /><button className="p" onClick={async () => { try { await navigator.clipboard.writeText(url); setCopied(true); } catch { } }}>{copied ? "Copied" : "Copy"}</button>
      <a className="btn" href={url} target="_blank" rel="noreferrer">Open</a><button className="s" onClick={onClose}>Close</button></div></div>;
}
