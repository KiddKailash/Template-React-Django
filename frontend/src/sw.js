/// <reference lib="webworker" />
// Custom service worker (vite-plugin-pwa injectManifest mode), after
// LLMStockAnalysis's. Three jobs:
//   1. Precache the app shell, and serve index.html for in-app navigations
//      (what the generated worker's navigateFallback used to do).
//   2. Show Web Push notifications.
//   3. Route a notification click to its page, reusing an open tab.
//
// Deliberately NO runtime caching of /api/: responses are per-user and
// authenticated, so a URL-keyed cache would show one account's data to the
// next person on the device and keep it readable after sign-out.
//
// Push payload shape (backend/notifications/utils/dispatcher.py):
//   { title, body, url, type, notification_id }

import { clientsClaim } from 'workbox-core';
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

self.skipWaiting();
clientsClaim();

registerRoute(
  new NavigationRoute(createHandlerBoundToURL('index.html'), {
    denylist: [/^\/api\//, /^\/admin\//, /^\/static\//, /^\/media\//],
  }),
);

// ─── Web Push ────────────────────────────────────────────────────────────

const APP_NAME = 'Template App';
const ICON = '/icon-192.png';

self.addEventListener('push', (event) => {
  if (!event.data) return;
  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: APP_NAME, body: event.data.text() };
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || APP_NAME, {
      body: payload.body,
      icon: ICON,
      badge: ICON,
      // Same type replaces the previous notification instead of stacking.
      tag: payload.type || 'general',
      data: { url: payload.url || '/' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  // Same-origin paths only: a payload is server-built, but a notification
  // must never become a way to open an arbitrary site.
  const raw = event.notification.data?.url || '/';
  const target = new URL(raw, self.location.origin);
  const url = target.origin === self.location.origin ? target.href : self.location.origin + '/';

  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const client of windows) {
        if ('focus' in client && 'navigate' in client) {
          await client.focus();
          try {
            await client.navigate(url);
          } catch {
            // Uncontrolled client, or already there.
          }
          return;
        }
      }
      await self.clients.openWindow(url);
    })(),
  );
});
