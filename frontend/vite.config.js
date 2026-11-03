import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // Custom service worker (src/sw.js): precaches the app shell and handles
      // Web Push. Registered by src/pwa.js, which also polls for new builds.
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.js',
      registerType: 'autoUpdate',
      injectRegister: false,
      injectManifest: {
        maximumFileSizeToCacheInBytes: 1024 * 1024 * 10, // 10MB
      },
      includeAssets: ['app-icon.svg', 'icon-192.png', 'icon-512.png'],
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
          { src: 'app-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          // PNGs too: Android's install prompt and notification icons need them.
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
        ],
      },
    }),
  ],
})
