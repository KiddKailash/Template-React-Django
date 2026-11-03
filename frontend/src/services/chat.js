// Chat API: today's thread, and one turn, streamed (from LLMStockAnalysis).
//
// A turn can take minutes (several model calls and tools). A plain JSON
// request says nothing until the end, and nginx (60 s) and Cloudflare (~100 s)
// cut it off: the user got an error while the server kept working and paying.
// So turns stream as server-sent events (POST chat/stream/): progress frames,
// a keep-alive at least every 15 s, and a final `done` frame carrying exactly
// the JSON body of POST chat/, which stays as the fallback.
//
// fetch(), not EventSource: EventSource cannot POST or send an Authorization
// header. That also bypasses the axios refresh interceptor, so a 401 is
// handled here: refresh through `api`, then retry the stream once.

import api, { API_URL } from './api';

export const fetchTodayThread = () => api.get('chat/today/');
export const sendChatMessageJson = (message) => api.post('chat/', { message });

export class StreamUnauthorized extends Error {}

export const parseSseFrame = (frame) => {
  let event = 'message';
  const dataLines = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue; // keep-alive comment
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) };
  } catch {
    return null;
  }
};

/**
 * Drive one streamed turn. Calls `onEvent({ event, data })` for each progress
 * frame and resolves with the `done` payload.
 *
 * A rejection carries `streamStarted`: true once any frame has arrived. Past
 * that point the turn is running on the server and will be saved (or fail) on
 * its own, so re-sending it would run and bill it twice and could save the
 * exchange twice. Only a failure before the first frame is safe to retry.
 */
export const streamChatTurn = async ({ message, onEvent, signal, fetchImpl = fetch }) => {
  const token = localStorage.getItem('access_token');
  const response = await fetchImpl(`${API_URL}/chat/stream/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message }),
    signal,
  });

  if (response.status === 401) throw new StreamUnauthorized('Unauthorized');
  if (!response.ok || !response.body) {
    // Bad input and misconfiguration are refused with JSON before streaming.
    let detail = 'The assistant request failed. Please try again.';
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // not JSON: keep the default
    }
    const error = new Error(detail);
    error.status = response.status;
    error.streamStarted = false;
    throw error;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result = null;
  let failure = null;
  let started = false;

  const fail = (text) => {
    const error = new Error(text);
    error.streamStarted = started;
    return error;
  };

  while (true) {
    let chunk;
    try {
      chunk = await reader.read();
    } catch (err) {
      throw fail(err?.message || 'The connection to the assistant was lost.');
    }
    if (chunk.done) break;
    // Normalise CRLF: an intermediary may rewrite line endings, and the frame
    // separator is the one piece of SSE framing we cannot afford to miss.
    buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, '\n');
    let split = buffer.indexOf('\n\n');
    while (split !== -1) {
      const parsed = parseSseFrame(buffer.slice(0, split));
      buffer = buffer.slice(split + 2);
      if (parsed) {
        started = true;
        if (parsed.event === 'done') result = parsed.data;
        else if (parsed.event === 'error') failure = parsed.data?.error;
        else onEvent?.(parsed);
      }
      split = buffer.indexOf('\n\n');
    }
  }

  if (failure) throw fail(failure);
  if (!result) throw fail('The assistant stopped before answering. Please try again.');
  return result;
};

const canStream = () =>
  typeof window !== 'undefined' &&
  typeof window.fetch === 'function' &&
  typeof window.ReadableStream === 'function';

/**
 * One chat turn: streamed when the browser can, the JSON endpoint otherwise.
 * Resolves with `{ user_message, assistant_message, cost_capped }`.
 *
 * Retry rules (from LLMStockAnalysis):
 *   - 401 before streaming: refresh the token via `api` (its interceptor
 *     refreshes, or sends the user to sign in) and stream once more.
 *   - a failure before the first frame (network, 5xx): fall back to JSON.
 *   - never after a frame arrived (the turn is already running), and never on
 *     a deliberate 4xx (the JSON endpoint would refuse the same input).
 */
export const sendChatTurn = async ({ message, onEvent, signal, deps = {} }) => {
  const stream = deps.streamChatTurn ?? streamChatTurn;
  const refresh = deps.refresh ?? (() => api.get('me/'));
  const json = deps.sendChatMessageJson ?? sendChatMessageJson;
  const streamingAvailable = deps.canStream ?? canStream();

  if (streamingAvailable) {
    try {
      try {
        return await stream({ message, onEvent, signal });
      } catch (err) {
        if (!(err instanceof StreamUnauthorized)) throw err;
        await refresh();
        return await stream({ message, onEvent, signal });
      }
    } catch (err) {
      const deliberate =
        err.status >= 400 && err.status < 500 && !(err instanceof StreamUnauthorized);
      if (err.streamStarted || deliberate || err.name === 'AbortError') throw err;
    }
  }
  const response = await json(message);
  return response.data;
};
