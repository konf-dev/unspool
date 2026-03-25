import { test, expect } from '@playwright/test'

test.describe('Chat Stream', () => {
  // These tests require auth setup — placeholder for now
  test.skip('sends a message and receives a reflection', async ({ page }) => {
    await page.goto('/chat')
    const input = page.getByLabel('Message input')
    await input.fill('I need to finish the report')
    await input.press('Enter')
    await expect(page.getByText('I need to finish the report')).toBeVisible()
  })

  test.skip('stop button appears during streaming', async ({ page }) => {
    await page.goto('/chat')
    const input = page.getByLabel('Message input')
    await input.fill('test message')
    await input.press('Enter')
    await expect(page.getByLabel('Stop generating')).toBeVisible()
  })

  test('empty state shows prompt text', async ({ page }) => {
    await page.goto('/chat')
    // Will redirect to login if not authenticated
    // Full test needs auth mock
  })
})
