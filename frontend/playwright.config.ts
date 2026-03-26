import { defineConfig, devices } from '@playwright/test'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// Load root .env so Playwright tests get SUPABASE_URL/SECRET_KEY for admin auth
try {
  const rootEnv = readFileSync(resolve(__dirname, '../.env'), 'utf-8')
  for (const line of rootEnv.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eqIdx = trimmed.indexOf('=')
    if (eqIdx === -1) continue
    const key = trimmed.slice(0, eqIdx)
    const value = trimmed.slice(eqIdx + 1)
    if (!process.env[key]) process.env[key] = value
  }
} catch {
  // Root .env not found — rely on existing env vars
}

// Default test email if not set
if (!process.env.PLAYWRIGHT_TEST_EMAIL) {
  process.env.PLAYWRIGHT_TEST_EMAIL = 'test@e2e.local'
}

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173'
const isRemote = !baseURL.includes('localhost')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
  ],
  // Only start local dev server when testing against localhost
  ...(!isRemote && {
    webServer: {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
    },
  }),
})
