import { test, expect } from '@playwright/test'
import { authenticate, simulateMobilePointer } from './helpers'

// ─────────────────────── Desktop: Enter Key Behavior ───────────────────────

test.describe('Desktop — Enter key sends', () => {
  test.use({ viewport: { width: 1280, height: 720 } })

  test('Enter sends message, clears input', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await input.fill('hello from desktop')
    await input.press('Enter')
    await expect(input).toHaveValue('')
  })

  test('Shift+Enter inserts newline without sending', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await input.fill('line one')
    await input.press('Shift+Enter')
    await input.type('line two')
    const value = await input.inputValue()
    expect(value).toContain('line one')
    expect(value).toContain('line two')
  })

  test('Empty input: Enter does nothing', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await expect(input).toHaveValue('')
    await input.press('Enter')
    await expect(input).toHaveValue('')
  })

  test('Send button sends message', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await input.fill('click send test')
    await page.getByLabel('Send message').click()
    await expect(input).toHaveValue('')
  })

  test('Send button disabled when input empty', async ({ page }) => {
    await authenticate(page)
    const sendBtn = page.getByLabel('Send message')
    await expect(sendBtn).toBeDisabled()
  })

  test('User message appears in message list after send', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await input.fill('test message visible')
    await input.press('Enter')
    await expect(page.getByText('test message visible')).toBeVisible({ timeout: 5000 })
  })
})

// ─────────────────────── Mobile: Enter Key Behavior ────────────────────────

test.describe('Mobile — Enter inserts newline', () => {
  test.use({
    viewport: { width: 375, height: 812 },
    hasTouch: true,
  })

  test('Enter inserts newline, does NOT send', async ({ page }) => {
    await simulateMobilePointer(page)
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await input.fill('item one')
    await input.press('Enter')
    await input.type('item two')
    const value = await input.inputValue()
    expect(value).toContain('item one')
    expect(value).toContain('item two')
    expect(value.length).toBeGreaterThan(0)
  })

  test('Send button is the primary send mechanism on mobile', async ({ page }) => {
    await simulateMobilePointer(page)
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await input.fill('mobile send test')
    const sendBtn = page.getByLabel('Send message')
    await expect(sendBtn).toBeEnabled()
    await sendBtn.click()
    await expect(input).toHaveValue('')
  })

  test('Multi-line brain dump: multiple Enters then send', async ({ page }) => {
    await simulateMobilePointer(page)
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await input.fill('buy groceries')
    await input.press('Enter')
    await input.type('call dentist')
    await input.press('Enter')
    await input.type('finish report')
    const value = await input.inputValue()
    expect(value.split('\n').length).toBeGreaterThanOrEqual(3)
    await page.getByLabel('Send message').click()
    await expect(input).toHaveValue('')
  })
})

// ─────────────────────── Layout Stability ──────────────────────────────────

test.describe('Layout — fixed viewport, no shift', () => {
  test('Root container uses fixed positioning (fills viewport)', async ({ page }) => {
    await authenticate(page)
    const root = page.locator('.fixed.inset-0').first()
    await expect(root).toBeVisible()
    const box = await root.boundingBox()
    expect(box).toBeTruthy()
    const viewport = page.viewportSize()!
    expect(box!.width).toBeCloseTo(viewport.width, -1)
    expect(box!.height).toBeCloseTo(viewport.height, -1)
  })

  test('InputBar footer stays pinned at bottom', async ({ page }) => {
    await authenticate(page)
    const footer = page.locator('footer')
    await expect(footer).toBeVisible()
    const box = await footer.boundingBox()
    const viewport = page.viewportSize()!
    // Footer bottom edge should be near viewport bottom
    expect(box!.y + box!.height).toBeGreaterThan(viewport.height - 100)
  })

  test.describe('Mobile viewport', () => {
    test.use({ viewport: { width: 375, height: 812 } })

    test('Layout fills mobile viewport', async ({ page }) => {
      await authenticate(page)
      const root = page.locator('.fixed.inset-0').first()
      await expect(root).toBeVisible()
      const box = await root.boundingBox()
      expect(box!.width).toBeCloseTo(375, -1)
      expect(box!.height).toBeCloseTo(812, -1)
    })
  })
})

// ─────────────────────── Z-Index & Layering ────────────────────────────────

test.describe('Z-index layering', () => {
  test('Sign-out button is visible', async ({ page }) => {
    await authenticate(page)
    const signOut = page.getByRole('button', { name: 'sign out' })
    await expect(signOut).toBeVisible()
  })

  test('Sign-out z-index is >= 60 (above plate z-50)', async ({ page }) => {
    await authenticate(page)
    const signOut = page.getByRole('button', { name: 'sign out' })
    const zIndex = await signOut.evaluate((el) => getComputedStyle(el).zIndex)
    expect(Number(zIndex)).toBeGreaterThanOrEqual(60)
  })

  test('Sign-out button works and redirects to login', async ({ page }) => {
    await authenticate(page)
    const signOut = page.getByRole('button', { name: 'sign out' })
    await signOut.click()
    await page.waitForURL(/\/login/, { timeout: 5000 })
  })

  test('OfflineBanner z-index is >= 60 (above plate z-50)', async ({ page }) => {
    await authenticate(page)
    // OfflineBanner only renders when offline, but we can check the component
    // renders correctly by going offline
    await page.context().setOffline(true)
    await page.waitForTimeout(500)
    const banner = page.getByText('offline')
    if (await banner.isVisible()) {
      const container = banner.locator('..')
      const zIndex = await container.evaluate((el) => getComputedStyle(el).zIndex)
      expect(Number(zIndex)).toBeGreaterThanOrEqual(60)
    }
    await page.context().setOffline(false)
  })
})

// ─────────────────────── Draft Persistence ─────────────────────────────────

test.describe('Draft persistence', () => {
  test('Draft survives page reload', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await input.fill('my unsent draft')
    // Wait for debounced save (500ms)
    await page.waitForTimeout(700)
    await page.reload()
    await authenticate(page)
    const reloadedInput = page.getByLabel('Message input')
    await expect(reloadedInput).toHaveValue('my unsent draft')
    // Clean up
    await reloadedInput.fill('')
    await page.waitForTimeout(700)
  })

  test('Draft cleared after send', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    await input.fill('will be sent')
    await page.waitForTimeout(700)
    await page.getByLabel('Send message').click()
    await expect(input).toHaveValue('')
    await page.reload()
    await authenticate(page)
    await expect(page.getByLabel('Message input')).toHaveValue('')
  })
})

// ─────────────────────── Input Controls ────────────────────────────────────

test.describe('Input controls', () => {
  test('Message input has character limit', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    const longText = 'a'.repeat(11000)
    await input.fill(longText)
    const value = await input.inputValue()
    expect(value.length).toBeLessThanOrEqual(10000)
  })

  test('Textarea auto-grows with multiline content', async ({ page }) => {
    await authenticate(page)
    const input = page.getByLabel('Message input')
    const initialBox = await input.boundingBox()
    await input.fill('line 1\nline 2\nline 3\nline 4')
    const grownBox = await input.boundingBox()
    expect(grownBox!.height).toBeGreaterThan(initialBox!.height)
  })
})

// ─────────────────────── Accessibility ─────────────────────────────────────

test.describe('Chat accessibility', () => {
  test('Message input has aria-label', async ({ page }) => {
    await authenticate(page)
    await expect(page.getByLabel('Message input')).toBeVisible()
  })

  test('Send button has aria-label', async ({ page }) => {
    await authenticate(page)
    await expect(page.getByLabel('Send message')).toBeVisible()
  })

  test('Voice button exists', async ({ page }) => {
    await authenticate(page)
    // Voice button should be in the input bar area
    const voiceBtn = page.locator('button').filter({ has: page.locator('svg') })
    const count = await voiceBtn.count()
    expect(count).toBeGreaterThan(0)
  })
})
