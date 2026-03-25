import { test, expect } from '@playwright/test'

test.describe('Accessibility', () => {
  test('landing page has proper heading hierarchy', async ({ page }) => {
    await page.goto('/')
    const h1 = page.locator('h1')
    await expect(h1.first()).toBeVisible()
  })

  test('login page has accessible form elements', async ({ page }) => {
    await page.goto('/login')
    // Login page has email input + submit button
    await expect(page.getByPlaceholder('your@email.com')).toBeVisible()
    await expect(page.getByRole('button', { name: 'send login code' })).toBeVisible()
  })

  test('privacy page has content', async ({ page }) => {
    await page.goto('/privacy')
    await expect(page.getByText('Privacy Policy')).toBeVisible()
  })
})
