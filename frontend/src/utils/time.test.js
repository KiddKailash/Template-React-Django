import { describe, expect, it } from 'vitest';

import { timeAgo } from './time';

describe('timeAgo', () => {
  const now = Date.parse('2026-11-03T12:00:00Z');
  it.each([
    ['2026-11-03T11:59:30Z', 'just now'],
    ['2026-11-03T11:55:00Z', '5m ago'],
    ['2026-11-03T09:00:00Z', '3h ago'],
    ['2026-11-01T12:00:00Z', '2d ago'],
  ])('%s -> %s', (iso, expected) => {
    expect(timeAgo(iso, now)).toBe(expected);
  });
});
