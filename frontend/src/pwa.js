// Service-worker registration (from LLMStockAnalysis).
//
// iOS standalone PWAs can stay alive for days across home-screen launches
// without re-fetching /sw.js, so `autoUpdate` alone never discovers a new
// build. Two things fix that:
//   1. registration.update() hourly and whenever the app returns to the
//      foreground;
//   2. one reload when the new worker takes control.
// nginx revalidating the shell and /sw.js on every load is the other half.

import { registerSW } from 'virtual:pwa-register';

const UPDATE_INTERVAL_MS = 60 * 60 * 1000; // 1h

registerSW({
  immediate: true,
  onRegisteredSW(_swUrl, registration) {
    if (!registration) return;
    setInterval(() => {
      void registration.update();
    }, UPDATE_INTERVAL_MS);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') void registration.update();
    });
  },
  onRegisterError(error) {
    console.error('SW registration failed:', error);
  },
});

if ('serviceWorker' in navigator) {
  // Reload once when a new worker takes over; not on the first install (no old
  // bundle to swap out), and never in a loop.
  let hadController = Boolean(navigator.serviceWorker.controller);
  let reloading = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController) {
      hadController = true;
      return;
    }
    if (reloading) return;
    reloading = true;
    window.location.reload();
  });
}
