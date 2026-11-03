import { describe, expect, it } from 'vitest';

import { describeProgress } from './chatProgress';

describe('describeProgress', () => {
  it.each([
    [null, 'Thinking…'],
    [{ event: 'start', data: {} }, 'Thinking…'],
    [{ event: 'iteration', data: { iteration: 1 } }, 'Thinking…'],
    [{ event: 'iteration', data: { iteration: 2 } }, 'Thinking about the results…'],
    [{ event: 'tool_start', data: { name: 'list_recent_users' } }, 'Using list recent users…'],
    [{ event: 'tool_result', data: { name: 'current_time_utc', ok: true } }, 'Read current time utc'],
    [{ event: 'tool_result', data: { name: 'lookup', ok: false } }, 'Lookup failed; working around it…'],
    [{ event: 'finalising', data: {} }, 'Writing the answer…'],
    [{ event: 'something_new', data: {} }, 'Working…'],
  ])('%j -> %s', (frame, expected) => {
    expect(describeProgress(frame)).toBe(expected);
  });
});
