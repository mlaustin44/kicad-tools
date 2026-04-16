import { test, expect } from '@playwright/test';

test('landing page renders hero and CTA', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('h1')).toContainText('kicad-viewer');
  await expect(page.locator('a', { hasText: 'Open viewer' })).toHaveAttribute('href', '/viewer');
  await expect(page.locator('.credit')).toContainText('Matthew Austin');
});
