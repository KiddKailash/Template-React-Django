/**
 * The SSE chat client (ported from LLMStockAnalysis's streamAgentTurn tests).
 * Small but unforgiving: a missed frame separator loses an answer, and a wrong
 * retry decision either strands the user or bills (and saves) a turn twice.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { StreamUnauthorized, parseSseFrame, sendChatTurn, streamChatTurn } from './chat';

const encoder = new TextEncoder();

/** A Response-alike whose body yields the given string chunks in order. */
const streamingResponse = (chunks, { status = 200 } = {}) => ({
  ok: status >= 200 && status < 300,
  status,
  body: {
    getReader() {
      let i = 0;
      return {
        read: async () =>
          i < chunks.length
            ? { done: false, value: encoder.encode(chunks[i++]) }
            : { done: true, value: undefined },
      };
    },
  },
});

const jsonResponse = (status, body) => ({
  ok: false,
  status,
  body: null,
  json: async () => body,
});

const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const DONE = {
  user_message: { id: 1, role: 'user', content: 'q' },
  assistant_message: { id: 2, role: 'assistant', content: 'the answer' },
  cost_capped: false,
};

// Node test environment: a minimal localStorage for the bearer token.
const store = new Map();
beforeEach(() => {
  store.clear();
  vi.stubGlobal('localStorage', {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  });
});
afterEach(() => vi.unstubAllGlobals());

const run = (chunks, extra = {}) => {
  const events = [];
  const fetchImpl = vi.fn(async () => streamingResponse(chunks, extra));
  const promise = streamChatTurn({ message: 'q', onEvent: (e) => events.push(e), fetchImpl });
  return { promise, events, fetchImpl };
};

describe('parseSseFrame', () => {
  it('reads event and JSON data, skipping comments', () => {
    expect(parseSseFrame(': keep-alive\nevent: tool_start\ndata: {"name":"x"}')).toEqual({
      event: 'tool_start',
      data: { name: 'x' },
    });
    expect(parseSseFrame(': keep-alive')).toBeNull();
    expect(parseSseFrame('event: x\ndata: not json')).toBeNull();
  });
});

describe('streamChatTurn framing', () => {
  it('delivers each frame and resolves with done', async () => {
    const { promise, events } = run([
      frame('start', { status: 'working' }),
      frame('tool_start', { name: 'current_time_utc' }),
      frame('done', DONE),
    ]);
    await expect(promise).resolves.toEqual(DONE);
    expect(events.map((e) => e.event)).toEqual(['start', 'tool_start']);
  });

  it('reassembles a frame split across chunks, and several frames in one chunk', async () => {
    const whole = frame('iteration', { iteration: 1 }) + frame('done', DONE);
    const { promise, events } = run([whole.slice(0, 10), whole.slice(10, 30), whole.slice(30)]);
    await expect(promise).resolves.toEqual(DONE);
    expect(events.map((e) => e.event)).toEqual(['iteration']);
  });

  it('ignores keep-alive comments and tolerates CRLF', async () => {
    const crlf = (s) => s.replace(/\n/g, '\r\n');
    const { promise, events } = run([': keep-alive\r\n\r\n', crlf(frame('done', DONE))]);
    await expect(promise).resolves.toEqual(DONE);
    expect(events).toEqual([]);
  });

  it('sends the bearer token, JSON body and Accept header', async () => {
    store.set('access_token', 'tok');
    const { promise, fetchImpl } = run([frame('done', DONE)]);
    await promise;
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toMatch(/\/api\/chat\/stream\/$/);
    expect(init.method).toBe('POST');
    expect(init.headers.Authorization).toBe('Bearer tok');
    expect(init.headers.Accept).toBe('text/event-stream');
    expect(JSON.parse(init.body)).toEqual({ message: 'q' });
  });
});

describe('streamChatTurn outcomes and retry safety', () => {
  it('an error frame rejects with the server message, after the stream started', async () => {
    const { promise } = run([frame('start', {}), frame('error', { error: 'took too long' })]);
    await expect(promise).rejects.toMatchObject({ message: 'took too long', streamStarted: true });
  });

  it('a stream that ends without done or error rejects as started', async () => {
    const { promise } = run([frame('start', {})]);
    await expect(promise).rejects.toMatchObject({ streamStarted: true });
  });

  it('a connection lost before any frame is retryable', async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      body: { getReader: () => ({ read: async () => Promise.reject(new Error('reset')) }) },
    }));
    await expect(streamChatTurn({ message: 'q', fetchImpl })).rejects.toMatchObject({
      streamStarted: false,
    });
  });

  it('a JSON rejection carries status and detail, not started', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(400, { detail: 'message is required' }));
    await expect(streamChatTurn({ message: '', fetchImpl })).rejects.toMatchObject({
      message: 'message is required',
      status: 400,
      streamStarted: false,
    });
  });

  it('401 raises StreamUnauthorized', async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(401, {}));
    await expect(streamChatTurn({ message: 'q', fetchImpl })).rejects.toBeInstanceOf(
      StreamUnauthorized,
    );
  });
});

describe('sendChatTurn fallback rules', () => {
  const deps = (overrides) => ({
    canStream: true,
    refresh: vi.fn(async () => {}),
    sendChatMessageJson: vi.fn(async () => ({ data: { ...DONE, via: 'json' } })),
    ...overrides,
  });
  const failing = (props) => Object.assign(new Error('x'), props);

  it('streams when it can', async () => {
    const d = deps({ streamChatTurn: vi.fn(async () => DONE) });
    await expect(sendChatTurn({ message: 'q', deps: d })).resolves.toEqual(DONE);
    expect(d.sendChatMessageJson).not.toHaveBeenCalled();
  });

  it('401: refreshes the token and streams again (not the JSON path)', async () => {
    const stream = vi
      .fn()
      .mockRejectedValueOnce(new StreamUnauthorized('Unauthorized'))
      .mockResolvedValueOnce(DONE);
    const d = deps({ streamChatTurn: stream });
    await expect(sendChatTurn({ message: 'q', deps: d })).resolves.toEqual(DONE);
    expect(d.refresh).toHaveBeenCalledOnce();
    expect(stream).toHaveBeenCalledTimes(2);
    expect(d.sendChatMessageJson).not.toHaveBeenCalled();
  });

  it('falls back to JSON when the stream failed before any frame', async () => {
    const d = deps({
      streamChatTurn: vi.fn(async () => {
        throw failing({ streamStarted: false, status: 502 });
      }),
    });
    await expect(sendChatTurn({ message: 'q', deps: d })).resolves.toMatchObject({ via: 'json' });
  });

  it('never re-sends once a frame arrived (it would run and bill twice)', async () => {
    const d = deps({
      streamChatTurn: vi.fn(async () => {
        throw failing({ streamStarted: true });
      }),
    });
    await expect(sendChatTurn({ message: 'q', deps: d })).rejects.toMatchObject({
      streamStarted: true,
    });
    expect(d.sendChatMessageJson).not.toHaveBeenCalled();
  });

  it('never re-sends a deliberate 4xx (the JSON endpoint would refuse it too)', async () => {
    const d = deps({
      streamChatTurn: vi.fn(async () => {
        throw failing({ streamStarted: false, status: 400 });
      }),
    });
    await expect(sendChatTurn({ message: 'q', deps: d })).rejects.toMatchObject({ status: 400 });
    expect(d.sendChatMessageJson).not.toHaveBeenCalled();
  });

  it('uses JSON where the browser cannot stream', async () => {
    const d = deps({ canStream: false, streamChatTurn: vi.fn() });
    await expect(sendChatTurn({ message: 'q', deps: d })).resolves.toMatchObject({ via: 'json' });
    expect(d.streamChatTurn).not.toHaveBeenCalled();
  });
});
