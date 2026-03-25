import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test('landing page shows sign-in options', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('unspool')).toBeVisible()
    await expect(page.getByText('Get Started')).toBeVisible()
  })

  test('login page has Google and email options', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByText('Continue with Google')).toBeVisible()
    await expect(page.getByText('or use email')).toBeVisible()
  })

  test('unauthenticated user redirected from /chat to /login', async ({ page }) => {
    await page.goto('/chat')
    await expect(page).toHaveURL(/\/login/)
  })

  test('privacy and terms links work', async ({ page }) => {
    await page.goto('/login')
    await page.getByText('privacy').click()
    await expect(page.getByText('Privacy Policy')).toBeVisible()
  })
})
