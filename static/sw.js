/**
 * HOMI PWA Service Worker
 * Caches static assets for faster repeat loads and basic offline support.
 * REF: MDN Web Docs (2024) Service Worker API - https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API
 * REF: MDN Web Docs (2024) Progressive Web Apps overview - https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps
 */
// Cache name and list of URLs to store when the worker first installs.
const CACHE_NAME = "homi-v1";
const STATIC_ASSETS = [
  "/static/css/site.css",
  "/static/img/homi-logo.png",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
  "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
];

// On install: open cache, add all static assets, then activate right away.
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

// On activate: remove old caches and take control of open pages.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// On fetch: skip non-GET and API; cache static/CDN; for HTML use network first, then cache.
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only same-origin and static/CDN assets
  if (url.origin !== self.location.origin && !url.host.includes("cdn.jsdelivr.net")) {
    return;
  }

  // API and form submissions: network only (no cache)
  if (url.pathname.startsWith("/api/") || request.method !== "GET") {
    return;
  }

  // Static assets: cache-first
  if (
    url.pathname.startsWith("/static/") ||
    url.host.includes("cdn.jsdelivr.net")
  ) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((res) => {
        const clone = res.clone();
        if (res.ok) caches.open(CACHE_NAME).then((c) => c.put(request, clone));
        return res;
      }))
    );
    return;
  }

  // HTML pages: network-first, fallback to cache for offline
  event.respondWith(
    fetch(request)
      .then((res) => {
        const clone = res.clone();
        if (res.ok && res.headers.get("content-type")?.includes("text/html")) {
          caches.open(CACHE_NAME).then((c) => c.put(request, clone));
        }
        return res;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match("/")))
  );
});
