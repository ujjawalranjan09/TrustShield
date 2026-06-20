import { test, expect } from '@playwright/test'

test.describe('Smoke Tests', () => {
  test('home page loads', async ({ page }) => {
    const response = await page.goto('/')
    expect(response?.status()).toBe(200)
  })

  test('report page renders form', async ({ page }) => {
    await page.goto('/en/report')
    await expect(page.locator('text=Report Fraudulent Activity')).toBeVisible()
    await expect(page.locator('text=Submit Report')).toBeVisible()
  })

  test('check page renders search input', async ({ page }) => {
    await page.goto('/en/check')
    await expect(page.locator('text=Check Reputation')).toBeVisible()
    await expect(page.locator('input[type="text"]')).toBeVisible()
  })

  test('login page renders login form', async ({ page }) => {
    await page.goto('/en/login')
    await expect(page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]')).toBeVisible()
  })
})
