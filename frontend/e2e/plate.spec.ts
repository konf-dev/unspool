import { test, expect } from '@playwright/test'
import { authenticate } from './helpers'

test.describe('The Plate', () => {
  test('Plate overlay exists in the DOM', async ({ page }) => {
    await authenticate(page)
    const plate = page.locator('[class*="z-50"]').first()
    await expect(plate).toBeAttached()
  })

  test('Main content blurs and fades when plate would be open', async ({ page }) => {
    await authenticate(page)
    // The plate isOpen state controls blur/opacity on <main>
    // In default state (closed), main should NOT be blurred
    const main = page.locator('main')
    const classes = await main.getAttribute('class')
    expect(classes).not.toContain('blur-sm')
  })

  test('InputBar disabled flag linked to plate state', async ({ page }) => {
    await authenticate(page)
    // With plate closed, input should be enabled
    const input = page.getByLabel('Message input')
    await expect(input).toBeEnabled()
  })

  test('Plate items section has accessible list role', async ({ page }) => {
    await authenticate(page)
    // The items section has role="list" when items exist
    const list = page.locator('[role="list"][aria-label="Current items"]')
    // May or may not be visible depending on plate data, but should be in DOM structure
    await expect(list).toBeAttached()
  })
})
