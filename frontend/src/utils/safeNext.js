/** Where to go after sign-in: `?next=` if it is a path on this site, else home.
 * Anything else (`//evil.example`, `/\evil.example`, `https://...`) would be an
 * open redirect, so it falls back to `/`. */
export const safeNext = (value) =>
  typeof value === 'string' &&
  value.startsWith('/') &&
  !value.startsWith('//') &&
  !value.startsWith('/\\')
    ? value
    : '/';
