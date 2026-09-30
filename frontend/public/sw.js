// Minimal service worker: makes the app installable. Never caches API data (business data must always be live).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => { if (e.request.url.includes("/api/")) return; });
