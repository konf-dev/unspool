import { test, expect } from '@playwright/test'

test.describe('The Plate', () => {
  test.skip('drag handle reveals plate overlay', async ({ page }) => {
    await page.goto('/chat')
    // Would need auth + messages with plate data
    // Plate overlay appears on drag gesture
  })

  test.skip('plate snaps back on release', async ({ page }) => {
    await page.goto('/chat')
    // Verify the anti-guilt snap-back behavior
  })
})
