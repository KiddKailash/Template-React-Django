# Frontend — React + Vite + MUI PWA

See the root [README](../README.md) and [ARCHITECTURE.md](../ARCHITECTURE.md) for context.

## Commands

```bash
npm install
cp .env.example .env
npm run dev       # http://localhost:5173
npm run build     # -> dist/
npm run lint
npm run preview
```

## Conventions (see CLAUDE.md at repo root)

- Functional components only.
- MUI imports are individual: `import Box from '@mui/material/Box'`.
- Never hardcode colours — use `theme.palette.*`.
- Page-level state in the page component, props down.

## Auth flow

`UserContext` reads/writes JWT pairs to `localStorage` and exposes `login` / `logout`.
`services/api.js` attaches the access token and auto-refreshes on 401 via `/api/token/refresh/`.
Failed refresh clears credentials and redirects to `/login`.

## Adding pages

1. Drop the page into `src/pages/`.
2. Register a route in `src/App.jsx` (wrap in `PrivateRoute` unless public).
3. Endpoint wrappers live in `src/services/api.js`.
