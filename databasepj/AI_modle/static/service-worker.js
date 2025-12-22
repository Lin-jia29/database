const CACHE_NAME = "pwa-cache-v1";
const CORE_ASSETS = [
  "/",
  "/questionnaire",
  "/static/style.css",
  "/static/script.js",
  "/static/manifest.webmanifest"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : null)))
    )
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // 動態 API / 結果頁：永遠走網路，不進 cache
  if (
    url.pathname.startsWith("/submit") ||
    url.pathname.startsWith("/result") ||
    url.pathname.startsWith("/product")
  ) {
    return;
  }

  // 其他靜態資源：網路優先，失敗才用 cache
  event.respondWith(fetch(req).catch(() => caches.match(req)));
});
