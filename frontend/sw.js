const CACHE_NAME = 'squeeze-tracker-v1';
const urlsToCache = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/manifest.json'
  // Remove icon references until you have the actual files
];

// Install event
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        console.log('Opened cache');
        // Try to add files, but don't fail if some are missing
        return Promise.allSettled(
          urlsToCache.map(url => cache.add(url))
        );
      })
      .then(() => {
        console.log('Cache setup complete');
        self.skipWaiting(); // Activate immediately
      })
  );
});

// Fetch event
self.addEventListener('fetch', function(event) {
  // Only handle GET requests
  if (event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(function(response) {
        // Return cached version or fetch from network
        if (response) {
          return response;
        }
        return fetch(event.request).catch(() => {
          // Return offline page for navigation requests
          if (event.request.destination === 'document') {
            return caches.match('/index.html');
          }
        });
      }
    )
  );
});

// Activate event
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(cacheName) {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      return self.clients.claim();
    })
  );
});

// Push notification event
self.addEventListener('push', function(event) {
  const options = {
    body: event.data ? event.data.text() : 'New squeeze opportunity detected!',
    icon: '/icon-192x192.png',
    badge: '/icon-192x192.png', // Use same icon as badge for now
    vibrate: [200, 100, 200],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: '2'
    },
    actions: [
      {
        action: 'explore',
        title: 'View Details'
      },
      {
        action: 'close',
        title: 'Close'
      }
    ]
  };

  event.waitUntil(
    self.registration.showNotification('Squeeze Tracker', options)
  );
});

// Notification click event
self.addEventListener('notificationclick', function(event) {
  event.notification.close();

  if (event.action === 'explore') {
    // Open the app to buy tab
    event.waitUntil(
      clients.openWindow('/?tab=buy')
    );
  } else if (event.action === 'close') {
    // Just close the notification
    return;
  } else {
    // Default action - open app
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

// Background sync for data updates
self.addEventListener('sync', function(event) {
  if (event.tag === 'background-sync') {
    event.waitUntil(doBackgroundSync());
  }
});

function doBackgroundSync() {
  // Fetch latest squeeze data in background
  return fetch('/api/squeeze-opportunities')
    .then(response => response.json())
    .then(data => {
      // Store in IndexedDB for offline access
      return storeSqueezeData(data);
    })
    .catch(err => {
      console.log('Background sync failed:', err);
    });
}

function storeSqueezeData(data) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('SqueezeDB', 1);

    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const db = request.result;
      const transaction = db.transaction(['squeezes'], 'readwrite');
      const store = transaction.objectStore('squeezes');

      store.put(data);

      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    };

    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore('squeezes', { keyPath: 'id' });
    };
  });
}