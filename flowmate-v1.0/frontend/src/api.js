export const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");   // empty on the web; the store apps set the server address at build time
let token = localStorage.getItem("token");
export const setToken = (t) => { token = t; t ? localStorage.setItem("token", t) : localStorage.removeItem("token"); };
export const eur = (c) => (c / 100).toLocaleString("en-IE", { style: "currency", currency: "EUR" });
export const cents = (s) => Math.round(parseFloat(String(s).replace(",", ".") || "0") * 100);

export async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}), ...(window.matchMedia?.("(display-mode: standalone)").matches || navigator.standalone ? { "X-App-Mode": "standalone" } : {}) };
  if (token) headers.Authorization = "Bearer " + token;
  let body = opts.body;
  if (body && !(body instanceof FormData) && !(body instanceof URLSearchParams)) { body = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const r = await fetch(API_BASE + "/api" + path, { ...opts, headers, body });
  if (r.status === 401 && token) { setToken(null); location.reload(); }
  if (!r.ok) { let m = r.statusText; try { const j = await r.json(); m = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {} throw new Error(m); }
  return r.json();
}

export async function download(path, filename) {
  const r = await fetch(API_BASE + "/api" + path, { headers: { Authorization: "Bearer " + localStorage.getItem("token") } });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail; } catch {} throw new Error(m); }
  const url = URL.createObjectURL(await r.blob()); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
}
