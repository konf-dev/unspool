import { test, expect } from '@playwright/test'

test.describe('Accessibility', () => {
  test('landing page has proper heading hierarchy', async ({ page }) => {
    await page.goto('/')
    const h1 = page.locator('h1')
    await expect(h1.first()).toBeVisible()
  })

  test('login page has accessible buttons', async ({ page }) => {
    await page.goto('/login')
    const buttons = page.getByRole('button')
    const count = await buttons.count()
    expect(count).toBeGreaterThan(0)
  })

  test('privacy page has semantic structure', async ({ page }) => {
    await page.goto('/privacy')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    const h2s = page.getByRole('heading', { level: 2 })
    const count = await h2s.count()
    expect(count).toBeGreaterThan(0)
  })
})
