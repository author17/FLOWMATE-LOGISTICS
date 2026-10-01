// Free OCR that runs inside the browser (Tesseract.js, English + Greek). The document never leaves the computer.
let workerPromise = null;
async function getWorker(onProgress) {
  if (!workerPromise) workerPromise = import("tesseract.js").then(T => T.createWorker(["eng", "ell"], 1, {
    workerPath: "/ocr/worker.min.js", corePath: "/ocr/core", langPath: "/ocr/lang", gzip: true,
    logger: m => window.__ocrProgress && window.__ocrProgress(m),
  }));
  window.__ocrProgress = m => onProgress && m.status === "recognizing text" && onProgress(Math.round(m.progress * 100));
  return workerPromise;
}

// Phone photos are 12+ megapixels: feeding them straight to the OCR engine runs the phone out of memory.
// Shrink first (longest side <= maxSide), fix the orientation, and stretch the contrast a little.
export async function prepareImage(file, { maxSide = 1700, quality = 0.88, enhance = true } = {}) {
  let bmp;
  try { bmp = await createImageBitmap(file, { imageOrientation: "from-image" }); }
  catch { bmp = await new Promise((ok, no) => { const im = new Image(), u = URL.createObjectURL(file); im.onload = () => { URL.revokeObjectURL(u); ok(im); }; im.onerror = no; im.src = u; }); }
  const w0 = bmp.width || bmp.naturalWidth, h0 = bmp.height || bmp.naturalHeight, k = Math.min(1, maxSide / Math.max(w0, h0));
  const c = document.createElement("canvas"); c.width = Math.max(1, Math.round(w0 * k)); c.height = Math.max(1, Math.round(h0 * k));
  const g = c.getContext("2d", { willReadFrequently: true }); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(bmp, 0, 0, c.width, c.height);
  if (bmp.close) bmp.close();
  if (enhance) {   // grayscale + simple auto-contrast (2%..98%)
    const img = g.getImageData(0, 0, c.width, c.height), d = img.data, hist = new Uint32Array(256);
    for (let i = 0; i < d.length; i += 4) { const y = (d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) / 1000 | 0; d[i] = d[i + 1] = d[i + 2] = y; hist[y]++; }
    const n = d.length / 4; let lo = 0, hi = 255, a = 0; for (; lo < 255 && a + hist[lo] < n * .02; lo++) a += hist[lo]; a = 0; for (; hi > 0 && a + hist[hi] < n * .02; hi--) a += hist[hi];
    if (hi - lo > 40) { const f = 255 / (hi - lo); for (let i = 0; i < d.length; i += 4) { const v = Math.max(0, Math.min(255, (d[i] - lo) * f)); d[i] = d[i + 1] = d[i + 2] = v; } }
    g.putImageData(img, 0, 0);
  }
  const blob = await new Promise(r => c.toBlob(r, "image/jpeg", quality));
  return { canvas: c, blob };
}

async function pdfToImages(file, maxPages = 3) {
  const pdfjs = await import("pdfjs-dist/build/pdf.min.mjs");
  pdfjs.GlobalWorkerOptions.workerSrc = "/ocr/pdf.worker.min.mjs";
  const pdf = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise, out = [];
  for (let i = 1; i <= Math.min(pdf.numPages, maxPages); i++) {
    const page = await pdf.getPage(i), vp = page.getViewport({ scale: 1.6 }), c = document.createElement("canvas");
    c.width = vp.width; c.height = vp.height; await page.render({ canvasContext: c.getContext("2d"), viewport: vp }).promise; out.push(c);
  }
  return out;
}

export async function ocrFile(file, onProgress) {
  const w = await getWorker(onProgress);
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  const inputs = isPdf ? await pdfToImages(file) : [(await prepareImage(file)).canvas];
  let text = "", conf = 0;
  try { for (const inp of inputs) { const { data } = await w.recognize(inp); text += data.text + "\n"; conf += data.confidence; inp.width = inp.height = 0; } }
  catch (e) { workerPromise = null; try { await w.terminate(); } catch { } throw e; }   // start from a clean engine next time
  return { text, confidence: Math.round(conf / inputs.length) };
}

// ---------- turn raw text into fields (Cyprus/Greek/English receipts & invoices) ----------
const toNum = s => {
  s = s.replace(/[^\d.,-]/g, ""); if (!s) return NaN;
  const lc = s.lastIndexOf(","), ld = s.lastIndexOf(".");
  if (lc > -1 && ld > -1) s = lc > ld ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  else if (lc > -1) s = /,\d{1,2}$/.test(s) ? s.replace(",", ".") : s.replace(/,/g, "");
  return parseFloat(s);
};
const AMT = /(?<![\d.,])(\d{1,3}(?:[.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2})(?![\d])/g;
const amountsIn = line => [...line.matchAll(AMT)].map(m => toNum(m[1])).filter(n => n > 0 && n < 10000000);

export function parseText(text, suppliers = []) {
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean), res = { supplier: "", number: "", date: "", total: "", vat: "", items: [], note: "Read locally (free OCR) - please check every field." };
  // total: prefer lines with a total keyword, take the biggest amount on them; else the biggest amount in the document
  const TOT = /(grand\s*total|total\s*due|amount\s*due|balance\s*due|to\s*pay|total|συνολο|σύνολο|πληρωτεο|πληρωτέο|ποσο|ποσό)/i, NOT = /(sub\s*total|net|vat|φπα|φ\.π\.α|καθαρη|καθαρή|change|ρεστα|cash|μετρητ)/i;
  let cands = []; lines.forEach((l, i) => { if (TOT.test(l) && !NOT.test(l)) { const a = amountsIn(l); cands.push(...(a.length ? a : amountsIn(lines[i + 1] || ""))); } });
  const all = lines.flatMap(amountsIn);
  const total = cands.length ? Math.max(...cands) : (all.length ? Math.max(...all) : NaN);
  if (!isNaN(total)) res.total = total.toFixed(2);
  // VAT: amount on a VAT line that is smaller than the total
  const vats = []; lines.forEach((l, i) => { if (/(vat|φπα|φ\.π\.α)/i.test(l) && !/(vat\s*(no|number|reg)|αρ\.?\s*φπα)/i.test(l)) { const a = amountsIn(l), b = a.length ? a : amountsIn(lines[i + 1] || ""); vats.push(...b.filter(x => !isNaN(total) && x < total)); } });
  if (vats.length) res.vat = Math.max(...vats).toFixed(2);
  // date
  let m = text.match(/\b(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{4}|\d{2})\b/), d;
  if (m) { const y = m[3].length === 2 ? "20" + m[3] : m[3]; d = `${y}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`; }
  else if ((m = text.match(/\b(20\d{2})-(\d{2})-(\d{2})\b/))) d = m[0];
  if (d && !isNaN(Date.parse(d))) res.date = d;
  // invoice / receipt number
  const NUM = /(?:invoice|inv|τιμολ[οό]γιο|παραστατικ[οό]|receipt|απ[οό]δειξη|document|doc)\s*(?:no\.?|number|αρ\.?|#|nr\.?)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-\/]*\d[A-Z0-9\-\/]*)/gi;
  m = null; for (const x of text.matchAll(NUM)) { m = x; break; }
  if (m) res.number = m[1];
  // supplier: match a known supplier (by VAT number or name), else the first line that looks like a name
  const vatNo = (text.match(/\b(CY)?\s?(\d{8}[A-Z])\b/i) || [])[2];
  const low = text.toLowerCase(), hit = suppliers.find(s => (vatNo && s.vat_number && s.vat_number.toUpperCase().includes(vatNo.toUpperCase())) || (s.name && low.includes(s.name.toLowerCase().split(/\s+/)[0]) && s.name.length > 3));
  res.supplier = hit ? hit.name : (lines.find(l => /[A-Za-zΑ-Ωα-ω]{3,}/.test(l) && !/^(invoice|receipt|tax|τιμολ|απόδειξη|date|www|tel)/i.test(l) && l.length < 60) || "");
  // line items: "description  qty  price" style lines (best effort)
  lines.forEach(l => { const a = amountsIn(l); const q = l.match(/^(.*?[A-Za-zΑ-Ωα-ω].*?)\s+(\d{1,3})\s*[x×]?\s+\d+[.,]\d{2}/i); if (q && a.length && !TOT.test(l) && !/(vat|φπα)/i.test(l)) res.items.push({ description: q[1].trim(), quantity: +q[2], unit_price: a[0] }); });
  res.items = res.items.slice(0, 20);
  return res;
}
