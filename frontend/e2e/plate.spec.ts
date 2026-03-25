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

  authTest('Plate items section has accessible list role', async ({ page }) => {
    await authenticate(page)
    const list = page.locator('[role="list"][aria-label="Current items"]')
    await expect(list).toBeAttached()
  })
})
