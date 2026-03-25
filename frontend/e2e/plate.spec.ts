import { test, expect } from '@playwright/test'
import { authenticate, canAuthenticate } from './helpers'

const authTest = canAuthenticate ? test : test.skip

test.describe('The Plate', () => {
  authTest('Plate overlay exists in DOM', async ({ page }) => {
    await authenticate(page)
    const plate = page.locator('[class*="z-50"]').first()
    await expect(plate).toBeAttached()
  })

  authTest('Main content is NOT blurred when plate is closed', async ({ page }) => {
    await authenticate(page)
    const main = page.locator('main')
    const classes = await main.getAttribute('class')
    expect(classes).not.toContain('blur-sm')
  })

  authTest('Input enabled when plate is closed', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await expect(input).toBeEnabled()
  })

  authTest('Empty plate shows placeholder text', async ({ page }) => {
    await authenticate(page)
    // With no items, the plate content exists but shows empty state
    // The list role only renders when items are present
    const emptyText = page.getByText('nothing on your plate right now')
    await expect(emptyText).toBeAttached()
  })
})
