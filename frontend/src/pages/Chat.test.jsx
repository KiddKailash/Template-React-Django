import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ThemeProvider, createTheme } from '@mui/material/styles';

import Chat from './Chat';
import { SnackbarContext } from '../contexts/SnackbarContext';
import { featurePages } from '../featurePages';

const render = () =>
  renderToStaticMarkup(
    <ThemeProvider theme={createTheme()}>
      <SnackbarContext.Provider value={{ showSnackbar: () => {} }}>
        <Chat />
      </SnackbarContext.Provider>
    </ThemeProvider>,
  );

describe('Chat page', () => {
  it('renders the conversation log and the composer', () => {
    const html = render();
    expect(html).toContain('role="log"');
    expect(html).toContain('aria-label="Message"');
    expect(html).toContain('aria-label="Send"');
  });

  it('is registered as a page with a header button', () => {
    const chat = featurePages.find((p) => p.path === '/chat');
    expect(chat).toBeDefined();
    expect(chat.icon).toBeDefined();
    expect(chat.Component).toBe(Chat);
  });
});
