// Copies the OCR engine + language data out of node_modules into public/ocr so the app serves them itself (no outside downloads).
import { cpSync, mkdirSync, existsSync } from "node:fs";
const out = "public/ocr"; mkdirSync(out + "/lang", { recursive: true }); mkdirSync(out + "/core", { recursive: true });
const cp = (a, b) => { if (!existsSync(a)) throw new Error("missing " + a); cpSync(a, b); };
cp("node_modules/tesseract.js/dist/worker.min.js", out + "/worker.min.js");
for (const f of ["tesseract-core-lstm.wasm.js", "tesseract-core-simd-lstm.wasm.js", "tesseract-core-relaxedsimd-lstm.wasm.js"]) cp("node_modules/tesseract.js-core/" + f, out + "/core/" + f);
cp("node_modules/@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz", out + "/lang/eng.traineddata.gz");
cp("node_modules/@tesseract.js-data/ell/4.0.0_best_int/ell.traineddata.gz", out + "/lang/ell.traineddata.gz");
cp("node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs", out + "/pdf.worker.min.mjs");
console.log("OCR assets copied");
