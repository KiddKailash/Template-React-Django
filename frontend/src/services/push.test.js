import { afterEach, describe, expect, it, vi } from 'vitest';

import { PUSH_STATE, getPushState, isPushSupported, urlBase64ToUint8Array } from './push';
import { pushDescription } from '../utils/pushCopy';

describe('urlBase64ToUint8Array', () => {
  it('decodes unpadded URL-safe base64 (the VAPID public key format)', () => {
    // bytes 0xfb 0xff 0xbf -> standard "+/+/" alphabet shows as "-_-_" URL-safe
    expect(Array.from(urlBase64ToUint8Array('-_-_'))).toEqual([0xfb, 0xff, 0xbf]);
    expect(Array.from(urlBase64ToUint8Array('AQI'))).toEqual([1, 2]);
  });
});

describe('push support', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('is unsupported without window / service workers (node, old browsers, iOS tabs)', async () => {
    expect(isPushSupported()).toBe(false);
    expect(await getPushState()).toBe(PUSH_STATE.UNSUPPORTED);
  });

  it('reports a denied permission without asking the server', async () => {
    vi.stubGlobal('window', { PushManager: class {}, Notification: class {} });
    vi.stubGlobal('navigator', { serviceWorker: {} });
    vi.stubGlobal('Notification', { permission: 'denied' });
    expect(await getPushState()).toBe(PUSH_STATE.DENIED);
  });
});

describe('pushDescription', () => {
  it('has a sentence for every state', () => {
    for (const state of Object.values(PUSH_STATE)) {
      expect(pushDescription(state)).toMatch(/\w/);
    }
    expect(pushDescription(PUSH_STATE.UNSUPPORTED)).toContain('Home Screen');
  });
});
