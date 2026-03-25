import { test, expect } from '@playwright/test'

test.describe('Landing Page', () => {
  test('shows title and tagline', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('unspool')).toBeVisible()
    await expect(page.getByText("you don't organize anything")).toBeVisible()
  })

  test('demo chat auto-plays messages', async ({ page }) => {
    await page.goto('/')
    // Wait for first demo message to appear
    await page.waitForTimeout(2000)
    const messages = page.locator('[class*="animate-fade-in"]')
    await expect(messages.first()).toBeVisible()
  })

  test('get started navigates to login', async ({ page }) => {
    await page.goto('/')
    await page.getByText('Get Started').click()
    await expect(page).toHaveURL(/\/login/)
  })

  test('footer links navigate to legal pages', async ({ page }) => {
    await page.goto('/')
    await page.getByText('privacy').last().click()
    await expect(page.getByText('Privacy Policy')).toBeVisible()
  })
})
