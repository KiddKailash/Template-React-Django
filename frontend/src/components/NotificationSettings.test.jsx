import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ThemeProvider, createTheme } from '@mui/material/styles';

import { NotificationDestination } from './NotificationSettings';

// Server-rendered, as in DeviceSessions.test.jsx (ported from LLMStockAnalysis).
const theme = createTheme();
const render = (node) =>
  renderToStaticMarkup(<ThemeProvider theme={theme}>{node}</ThemeProvider>).replace(
    /<!-- -->/g,
    '',
  );

const session = (overrides) => ({
  id: 'a',
  device: { browser: 'Safari', os: 'iPhone', kind: 'mobile', label: 'Safari on iPhone' },
  current: false,
  notifications: 'off',
  ...overrides,
});

const overview = (sessions, notifications) => ({
  sessions,
  notifications: {
    channel: 'email',
    email: 'me@example.com',
    devices: [],
    unlinked_devices: 0,
    ...notifications,
  },
});

describe('NotificationDestination', () => {
  it('names the devices push goes to', () => {
    const html = render(
      <NotificationDestination
        overview={overview(
          [
            session({ id: 'here', current: true, device: { kind: 'desktop', label: 'Chrome on macOS' } }),
            session({ id: 'phone' }),
          ],
          { channel: 'push', devices: ['here', 'phone'], unlinked_devices: 1 },
        )}
      />,
    );
    expect(html).toContain('Pushed to Chrome on macOS (this device), Safari on iPhone, 1 other device');
  });

  it('says email, and why, when push is idle', () => {
    const html = render(
      <NotificationDestination overview={overview([session({ notifications: 'idle' })])} />,
    );
    expect(html).toContain('Emailed to me@example.com');
    expect(html).toContain('hasn&#x27;t opened the app in 14 days');
  });

  it('says email, and how to get push, when no device has it', () => {
    const html = render(<NotificationDestination overview={overview([session()])} />);
    expect(html).toContain('No device has push on');
  });

  it('warns when there is nowhere to send', () => {
    const html = render(
      <NotificationDestination overview={overview([], { channel: null, email: '' })} />,
    );
    expect(html).toContain('Nowhere');
  });

  it('shows a placeholder while loading', () => {
    expect(render(<NotificationDestination loading />)).toContain('MuiSkeleton');
  });
});
