self.addEventListener('install', (e) => {
  console.log('Sahal POS Service Worker Installed');
});

self.addEventListener('fetch', (e) => {
  // Koodhkan wuxuu u oggolaanayaa App-ka inuu caadi u shaqeeyo
  e.respondWith(fetch(e.request));
});