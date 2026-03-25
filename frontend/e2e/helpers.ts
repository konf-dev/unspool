import { type Page, expect } from '@playwright/test'

/**
 * Authenticate for e2e tests.
 *
 * Strategy depends on environment:
 * - PLAYWRIGHT_TEST_EMAIL + PLAYWRIGHT_TEST_OTP: real OTP flow (for prod)
 * - Default (local/mock mode): walk through the OTP UI which auto-succeeds
 */
export async function authenticate(page: Page) {
  const testEmail = process.env.PLAYWRIGHT_TEST_EMAIL
  const testOtp = process.env.PLAYWRIGHT_TEST_OTP

  if (testEmail && testOtp) {
    // Real auth flow for prod testing
    await page.goto('/login')
    await page.getByPlaceholder('your@email.com').fill(testEmail)
    await page.getByRole('button', { name: 'send login code' }).click()
    // Wait for OTP stage
    await expect(page.getByLabel('Login code')).toBeVisible({ timeout: 10000 })
    await page.getByLabel('Login code').fill(testOtp)
    // Auto-submits on 6 digits, redirects to /chat
    await page.waitForURL(/\/chat/, { timeout: 15000 })
  } else {
    // Mock mode: walk through the UI — sendOtp is a no-op, verifyOtp sets mock state
    await page.goto('/login')
    await page.getByPlaceholder('your@email.com').fill('test@e2e.local')
    await page.getByRole('button', { name: 'send login code' }).click()
    // In mock mode, sendOtp returns immediately → OTP stage appears
    await expect(page.getByLabel('Login code')).toBeVisible({ timeout: 5000 })
    await page.getByLabel('Login code').fill('123456')
    // verifyOtp in mock mode sets auth state → App redirects to /chat
    await page.waitForURL(/\/chat/, { timeout: 10000 })
  }

  await page.waitForSelector('[aria-label="Message input"]', { timeout: 10000 })
}

/**
 * Inject coarse pointer media query to simulate mobile touch device.
 * Must be called BEFORE navigating to the page.
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
