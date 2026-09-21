// Service Worker AFYA APP — alarmes Web Push + page hors ligne élégante
// Stratégie volontairement minimale : SEULES les navigations (pages HTML) sont
// interceptées, en "réseau d'abord" — aucun cache agressif, aucun risque de
// servir des données périmées.

var OFFLINE_URL = '/static/offline.html';

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open('afya-offline-v1').then(function (cache) {
      return cache.add(OFFLINE_URL);
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

// Pages HTML : réseau d'abord, sinon page "Connexion perdue"
self.addEventListener('fetch', function (event) {
  if (event.request.mode !== 'navigate') return;   // on ne touche pas au reste
  event.respondWith(
    fetch(event.request).catch(function () {
      return caches.match(OFFLINE_URL);
    })
  );
});

// Réception d'une notification push (serveur → navigateur, même onglet fermé)
self.addEventListener('push', function (event) {
  var data = {title: 'AFYA APP', body: 'Rappel de rendez-vous', link: '/'};
  try {
    if (event.data) { data = event.data.json(); }
  } catch (e) { /* garde les valeurs par défaut */ }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/img/icon-192.png',
      badge: '/static/img/icon-192.png',
      tag: 'afya-rappel-' + Date.now(),
      renotify: true,
      requireInteraction: true,            // reste affichée jusqu'à action de l'utilisateur
      vibrate: [500, 200, 500, 200, 500],  // vibration type alarme
      data: {link: data.link || '/'}
    })
  );
});

// Clic sur la notification → ouvre (ou focus) l'application sur la bonne page
self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var link = (event.notification.data && event.notification.data.link) || '/';
  var url = new URL(link, self.location.origin).href;

  event.waitUntil(
    self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(function (clients) {
      for (var i = 0; i < clients.length; i++) {
        if (clients[i].url.indexOf(self.location.origin) === 0 && 'focus' in clients[i]) {
          clients[i].navigate(url);
          return clients[i].focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
