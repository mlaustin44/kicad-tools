import { test, expect } from '@playwright/test';

test('landing page renders hero and CTA', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('h1')).toContainText('KiCad project viewer');
  await expect(page.locator('a', { hasText: 'Open viewer' })).toHaveAttribute('href', '/viewer');
  await expect(page.locator('.credit')).toContainText('Matthew Austin');
});
