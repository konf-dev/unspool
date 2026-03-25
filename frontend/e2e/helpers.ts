import { type Page, expect } from '@playwright/test'

const isRemote = !!(process.env.PLAYWRIGHT_BASE_URL && !process.env.PLAYWRIGHT_BASE_URL.includes('localhost'))
const hasTestCredentials = !!(process.env.PLAYWRIGHT_TEST_EMAIL && process.env.PLAYWRIGHT_TEST_OTP)

/**
 * Whether authenticated tests can run.
 * On remote (prod), we need PLAYWRIGHT_TEST_EMAIL + PLAYWRIGHT_TEST_OTP.
 * On local (mock mode), auth always works via the mock OTP flow.
 */
export const canAuthenticate = !isRemote || hasTestCredentials

/**
 * Authenticate for e2e tests.
 *
 * - Remote + credentials: real OTP flow
 * - Local (mock mode): walk through OTP UI which auto-succeeds
 */
export async function authenticate(page: Page) {
  const testEmail = process.env.PLAYWRIGHT_TEST_EMAIL
  const testOtp = process.env.PLAYWRIGHT_TEST_OTP

  if (isRemote && testEmail && testOtp) {
    // Real auth flow for prod testing
    await page.goto('/login')
    await page.getByPlaceholder('your@email.com').fill(testEmail)
    await page.getByRole('button', { name: 'send login code' }).click()
    await expect(page.getByLabel('Login code')).toBeVisible({ timeout: 15000 })
    await page.getByLabel('Login code').fill(testOtp)
    await page.waitForURL(/\/chat/, { timeout: 15000 })
  } else if (!isRemote) {
    // Mock mode: sendOtp is no-op, verifyOtp sets mock state instantly
    await page.goto('/login')
    await page.getByPlaceholder('your@email.com').fill('test@e2e.local')
    await page.getByRole('button', { name: 'send login code' }).click()
    await expect(page.getByLabel('Login code')).toBeVisible({ timeout: 5000 })
    await page.getByLabel('Login code').fill('123456')
    await page.waitForURL(/\/chat/, { timeout: 10000 })
  } else {
    throw new Error(
      'Cannot authenticate: running against remote but PLAYWRIGHT_TEST_EMAIL and PLAYWRIGHT_TEST_OTP are not set. ' +
      'Set these env vars or run against localhost.'
    )
  }

  await page.waitForSelector('[aria-label="Message input"]', { timeout: 10000 })
}

/**
 * Inject coarse pointer media query to simulate mobile touch device.
 * Must be called BEFORE navigating to the page (before authenticate).
 */
export async function simulateMobilePointer(page: Page) {
  await page.addInitScript(() => {
    const original = window.matchMedia
    window.matchMedia = (query: string) => {
      if (query === '(pointer: coarse)') {
        return {
          matches: true,
          media: query,
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        } as MediaQueryList
      }
      return original(query)
    }
  })
}
