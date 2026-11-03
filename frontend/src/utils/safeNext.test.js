import { describe, expect, it } from 'vitest';

import { safeNext } from './safeNext';

describe('safeNext', () => {
  it('keeps a path on this site', () => {
    expect(safeNext('/settings')).toBe('/settings');
    expect(safeNext('/a/b?c=1#d')).toBe('/a/b?c=1#d');
  });

  it.each([
    [null],
    [undefined],
    [''],
    ['settings'],
    ['//evil.example'],
    ['/\\evil.example'],
    ['https://evil.example/'],
    ['javascript:alert(1)'],
  ])('refuses %s', (value) => {
    expect(safeNext(value)).toBe('/');
  });
});
