// FLOWMATE service worker. Business data (/api/) is NEVER cached - it must always be live.
// It caches only the app shell + static files so the app opens fast and shows a friendly page when offline.
const V = "flowmate-v1";
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(["/offline.html"])).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/")) return;
  if (r.mode === "navigate") { e.respondWith(fetch(r).catch(() => caches.match("/offline.html"))); return; }
  // hashed build files and OCR engine files never change under the same name -> cache first
  if (u.pathname.startsWith("/assets/") || u.pathname.startsWith("/ocr/")) {
    e.respondWith(caches.match(r).then(hit => hit || fetch(r).then(res => { if (res.ok) { const c = res.clone(); caches.open(V).then(ch => ch.put(r, c)); } return res; })));
  }
});
