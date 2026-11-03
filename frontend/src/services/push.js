// Web Push helpers (from LLMStockAnalysis).
//
// State is derived from the live PushSubscription on the registered service
// worker; nothing is cached in localStorage. The server owns the subscription
// list; the service worker is the local copy.

import api from './api';

export const PUSH_STATE = {
  UNSUPPORTED: 'unsupported', // browser can't deliver pushes (or not installed, on iOS)
  UNCONFIGURED: 'unconfigured', // backend has no VAPID key
  DEFAULT: 'default', // not asked yet, or turned off
  GRANTED_SUBSCRIBED: 'granted-subscribed',
  GRANTED_PENDING: 'granted-pending', // permission given, this device not registered
  DENIED: 'denied',
};

export function urlBase64ToUint8Array(base64) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const normalized = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(normalized);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export function isPushSupported() {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

async function fetchVapidPublicKey() {
  const res = await api.get('notifications/vapid-public-key/');
  return res.data?.public_key || '';
}

export async function getPushState() {
  if (!isPushSupported()) return PUSH_STATE.UNSUPPORTED;
  const permission = Notification.permission;
  if (permission === 'denied') return PUSH_STATE.DENIED;
  if (permission === 'default') {
    try {
      const key = await fetchVapidPublicKey();
      return key ? PUSH_STATE.DEFAULT : PUSH_STATE.UNCONFIGURED;
    } catch {
      return PUSH_STATE.DEFAULT;
    }
  }
  const reg = await navigator.serviceWorker.getRegistration();
  if (!reg) return PUSH_STATE.GRANTED_PENDING;
  const sub = await reg.pushManager.getSubscription();
  return sub ? PUSH_STATE.GRANTED_SUBSCRIBED : PUSH_STATE.GRANTED_PENDING;
}

export async function enablePush() {
  if (!isPushSupported()) return PUSH_STATE.UNSUPPORTED;
  const key = await fetchVapidPublicKey();
  if (!key) return PUSH_STATE.UNCONFIGURED;

  const permission = await Notification.requestPermission();
  if (permission === 'denied') return PUSH_STATE.DENIED;
  if (permission !== 'granted') return PUSH_STATE.DEFAULT;

  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key),
    });
  }
  await api.post('notifications/subscribe/', sub.toJSON());
  return PUSH_STATE.GRANTED_SUBSCRIBED;
}

export async function disablePush() {
  if (!isPushSupported()) return PUSH_STATE.UNSUPPORTED;
  const reg = await navigator.serviceWorker.getRegistration();
  if (!reg) return PUSH_STATE.GRANTED_PENDING;
  const sub = await reg.pushManager.getSubscription();
  if (sub) {
    await api.post('notifications/unsubscribe/', { endpoint: sub.endpoint }).catch(() => undefined);
    await sub.unsubscribe();
  }
  return PUSH_STATE.DEFAULT;
}

/** On sign-out: drop this browser's push subscription. The server has already
 * deactivated it with the session; unsubscribing here as well stops the next
 * person who signs in on this browser from being re-registered (by
 * reportDeviceActivity) on the previous user's permission. Never throws. */
export async function forgetThisDevice() {
  if (!isPushSupported()) return;
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    const sub = await reg?.pushManager.getSubscription();
    if (sub) await sub.unsubscribe();
  } catch {
    // Nothing to forget.
  }
}

/** Push a test notification to this user's devices (POST notifications/test/). */
export const sendTestNotification = () => api.post('notifications/test/');

// How often a tab tells the server the device is in use. The server keeps its
// own one-hour resolution; this just saves the request.
const ACTIVITY_REPORT_INTERVAL_MS = 60 * 60 * 1000;
let lastActivityReport = 0;

/** Tell the server this device has the app open. A device seen in the last 14
 * days gets notifications as pushes; one that hasn't gets them by email. If
 * the server no longer holds this device's subscription (it expired, or this
 * user's session here was ended), re-register it. Never throws. */
export async function reportDeviceActivity() {
  if (!isPushSupported() || Notification.permission !== 'granted') return;
  const now = Date.now();
  if (now - lastActivityReport < ACTIVITY_REPORT_INTERVAL_MS) return;
  lastActivityReport = now;
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    const sub = await reg?.pushManager.getSubscription();
    if (!sub) return;
    const res = await api.post('notifications/seen/', { endpoint: sub.endpoint });
    if (!res.data?.active) await api.post('notifications/subscribe/', sub.toJSON());
  } catch {
    lastActivityReport = 0; // try again on the next visit
  }
}
