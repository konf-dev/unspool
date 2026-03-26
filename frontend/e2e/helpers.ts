import { type Page, expect } from '@playwright/test'

const isRemote = !!(process.env.PLAYWRIGHT_BASE_URL && !process.env.PLAYWRIGHT_BASE_URL.includes('localhost'))

const hasAdminAuth = !!(
  process.env.SUPABASE_URL &&
  (process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY) &&
  process.env.PLAYWRIGHT_TEST_EMAIL
)
export const canAuthenticate = !isRemote || hasAdminAuth

export async function authenticate(page: Page) {
  if (hasAdminAuth) {
    await authenticateViaAdmin(page)
  } else if (!isRemote) {
    await authenticateViaMockOtp(page)
  } else {
    throw new Error(
      'Cannot authenticate: set SUPABASE_URL, SUPABASE_SECRET_KEY, and PLAYWRIGHT_TEST_EMAIL for prod testing.'
    )
  }

  await page.waitForSelector('[aria-label="Message input"]', { timeout: 15000 })
}

/**
 * Admin API auth: generate a magic link, navigate to it directly.
 * Supabase verifies the token and sets the session, then redirects to the app.
 */
async function authenticateViaAdmin(page: Page) {
  const supabaseUrl = process.env.SUPABASE_URL!
  const serviceRoleKey = (process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY)!
  const testEmail = process.env.PLAYWRIGHT_TEST_EMAIL!
  const baseURL = process.env.PLAYWRIGHT_BASE_URL!

  // Generate a magic link via Admin API
  const res = await fetch(`${supabaseUrl}/auth/v1/admin/generate_link`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${serviceRoleKey}`,
      'apikey': serviceRoleKey,
    },
    body: JSON.stringify({
      type: 'magiclink',
      email: testEmail,
      options: {
        redirectTo: baseURL + '/chat',
      },
    }),
  })

  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Admin generate_link failed (${res.status}): ${body}`)
  }

  const data = await res.json() as { action_link: string }

  if (!data.action_link) {
    throw new Error(`Admin generate_link response missing action_link: ${JSON.stringify(data).slice(0, 200)}`)
  }

  // Navigate to the magic link — Supabase verifies token, sets session via hash fragment
  await page.goto(data.action_link)

  // Wait for redirect chain to settle
  await page.waitForLoadState('networkidle', { timeout: 15000 })

  // Supabase PKCE flow redirects to: {redirectTo}#access_token=...&refresh_token=...
  // The Supabase JS client's onAuthStateChange picks up the hash and sets session.
  // If the app processed it, we should be on /chat now.
  // If not, give the SPA a moment to process the auth state change.
  const maxWait = 10000
  const start = Date.now()
  while (Date.now() - start < maxWait) {
    if (page.url().includes('/chat')) break
    await page.waitForTimeout(500)
  }

  // Final fallback: if we're still not on /chat, try navigating directly
  if (!page.url().includes('/chat')) {
    await page.goto(baseURL + '/chat')
    await page.waitForTimeout(2000)
  }
}

async function authenticateViaMockOtp(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder('your@email.com').fill('test@e2e.local')
  await page.getByRole('button', { name: 'send login code' }).click()
  await expect(page.getByLabel('Login code')).toBeVisible({ timeout: 5000 })
  await page.getByLabel('Login code').fill('123456')
  await page.waitForURL(/\/chat/, { timeout: 10000 })
}

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
