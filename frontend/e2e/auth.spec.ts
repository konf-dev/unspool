import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test('landing page shows brand and CTA', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('unspool')).toBeVisible()
    await expect(page.getByText('Get Started')).toBeVisible()
  })

  test('login page shows email input and send code button', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByPlaceholder('your@email.com')).toBeVisible()
    await expect(page.getByRole('button', { name: 'send login code' })).toBeVisible()
  })

  test('send code button disabled with empty email', async ({ page }) => {
    await page.goto('/login')
    const btn = page.getByRole('button', { name: 'send login code' })
    await expect(btn).toBeDisabled()
  })

  test('unauthenticated user redirected from /chat to /login', async ({ page }) => {
    await page.goto('/chat')
    await expect(page).toHaveURL(/\/login/)
  })

  test('email input persists across page reload', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('your@email.com').fill('test@example.com')
    await page.reload()
    // Email stored in sessionStorage should survive reload
    await expect(page.getByPlaceholder('your@email.com')).toHaveValue('test@example.com')
  })

  test('privacy and terms links work from login', async ({ page }) => {
    await page.goto('/login')
    await page.getByText('privacy').click()
    await expect(page.getByText('Privacy Policy')).toBeVisible()
    await page.goto('/login')
    await page.getByText('terms').click()
    await expect(page.getByText('Terms of Service')).toBeVisible()
  })

  test('login page shows tagline', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByText('I listen. I remember.')).toBeVisible()
  })
})
