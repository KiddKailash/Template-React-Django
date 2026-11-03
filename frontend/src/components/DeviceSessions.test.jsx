import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ThemeProvider, createTheme } from '@mui/material/styles';

import DeviceSessions from './DeviceSessions';

// Server-rendered so every state is exercised without a DOM (LLMStockAnalysis).
const theme = createTheme();
// React separates adjacent text nodes with <!-- -->; strip them so text reads as shown.
const render = (node) =>
  renderToStaticMarkup(<ThemeProvider theme={theme}>{node}</ThemeProvider>).replace(
    /<!-- -->/g,
    '',
  );

const session = (overrides) => ({
  id: 'a',
  device: { browser: 'Safari', os: 'iPhone', kind: 'mobile', label: 'Safari on iPhone' },
  ip_address: '203.0.113.7',
  created_at: '2026-10-01T09:00:00Z',
  last_seen_at: new Date().toISOString(),
  current: false,
  ...overrides,
});

const noop = () => {};

describe('DeviceSessions', () => {
  it('lists devices, marks this one, and offers sign-out only for others', () => {
    const html = render(
      <DeviceSessions
        overview={{
          sessions: [
            session({
              id: 'here',
              current: true,
              device: { kind: 'desktop', label: 'Chrome on macOS' },
            }),
            session({ id: 'phone' }),
          ],
        }}
        onRevoke={noop}
        onRevokeOthers={noop}
      />,
    );
    expect(html).toContain('Chrome on macOS');
    expect(html).toContain('This device');
    expect(html).toContain('Active now');
    expect(html).toContain('203.0.113.7');
    expect(html).toContain('aria-label="Sign out Safari on iPhone"');
    expect(html).not.toContain('aria-label="Sign out Chrome on macOS"');
    expect(html).toContain('Sign out the other device');
  });

  it('pluralises sign-out-all', () => {
    const html = render(
      <DeviceSessions
        overview={{
          sessions: [session({ id: 'here', current: true }), session({ id: 'b' }), session({ id: 'c' })],
        }}
        onRevoke={noop}
        onRevokeOthers={noop}
      />,
    );
    expect(html).toContain('Sign out all 2 other devices');
  });

  it('has no sign-out-all when this is the only device', () => {
    const html = render(
      <DeviceSessions
        overview={{ sessions: [session({ current: true })] }}
        onRevoke={noop}
        onRevokeOthers={noop}
      />,
    );
    expect(html).not.toContain('Sign out the other device');
    expect(html).not.toContain('other devices');
  });

  it('shows placeholders while loading', () => {
    const html = render(<DeviceSessions loading onRevoke={noop} onRevokeOthers={noop} />);
    expect(html).toContain('MuiSkeleton');
    expect(html).not.toContain('role="list"');
  });
});
