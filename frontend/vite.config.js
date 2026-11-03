import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      includeAssets: ['app-icon.svg'],
      manifest: {
        name: 'Template App',
        short_name: 'Template',
        description: 'Django + React template.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: '#ffffff',
        theme_color: '#2563EB',
        orientation: 'portrait',
        icons: [
          {
            src: 'app-icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any',
          },
        ],
      },
      workbox: {
        mode: 'development',
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        skipWaiting: true,
        maximumFileSizeToCacheInBytes: 1024 * 1024 * 10, // 10MB
        navigateFallbackDenylist: [/^\/media\//, /^\/api\//, /^\/admin\//, /^\/static\//],
        // No runtime caching of /api/ (it used to be NetworkFirst, 24 h). API
        // responses are per-user and authenticated: a cache keyed by URL alone
        // serves one account's data to the next person who signs in on the
        // device, and keeps it readable offline after "Sign out" or after the
        // session is ended from another device. Add a narrowly scoped route
        // (public, non-personal endpoints only) if a project needs offline reads.
      },
    }),
  ],
})
