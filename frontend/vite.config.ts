/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'
import { writeFileSync, mkdirSync } from 'fs'
import { execSync } from 'child_process'

function versionJsonPlugin() {
  return {
    name: 'version-json',
    closeBundle() {
      const sha = process.env.VERCEL_GIT_COMMIT_SHA
        || (() => { try { return execSync('git rev-parse HEAD', { encoding: 'utf8' }).trim() } catch { return 'dev' } })()
      const data = {
        git_sha: sha,
        built_at: new Date().toISOString(),
      }
      mkdirSync('dist', { recursive: true })
      writeFileSync('dist/version.json', JSON.stringify(data))
    },
  }
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    versionJsonPlugin(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Unspool',
        short_name: 'Unspool',
        description: 'Your mind, but reliable.',
        theme_color: '#0d0e0d',
        background_color: '#0d0e0d',
        display: 'standalone',
        start_url: '/',
        icons: [
          {
            src: '/icons/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: '/icons/icon-512.svg',
            sizes: '512x512',
            type: 'image/svg+xml',
          },
          {
            src: '/icons/icon-192.svg',
            sizes: '192x192',
            type: 'image/svg+xml',
          },
        ],
      },
      workbox: {
        // Force immediate activation of new service worker — no stale cache during dev
        skipWaiting: true,
        clientsClaim: true,
        // Don't precache index.html — let it always hit the network
        navigateFallback: null,
        runtimeCaching: [
          {
            urlPattern: /\/api\/.*/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 300,
              },
            },
          },
          {
            urlPattern: /\/fonts\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'font-cache',
              expiration: {
                maxEntries: 10,
                maxAgeSeconds: 60 * 60 * 24 * 365,
              },
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'framer-motion', '@supabase/supabase-js'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './test/setup.ts',
    exclude: ['e2e/**', 'node_modules/**'],
    css: true,
  },
})
