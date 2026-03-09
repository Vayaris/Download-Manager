const CACHE_NAME = "dm-v1";
const PRECACHE = [
  "/",
  "/settings-page",
  "/static/css/style.css",
  "/static/js/app.js",
  "/static/js/settings.js",
  "/static/js/websocket.js",
  "/static/js/theme.js",
  "/static/js/filebrowser.js",
  "/static/js/account.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // API and WebSocket requests: network only
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) {
    return;
  }

  // Static assets: network first, fallback to cache
  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
        }
        return resp;
      })
      .catch(() => caches.match(e.request))
  );
});
