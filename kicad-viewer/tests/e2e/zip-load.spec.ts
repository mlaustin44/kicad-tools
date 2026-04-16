import { test, expect } from '@playwright/test';
import { existsSync } from 'node:fs';

// Test with the real full-size project zip to catch OOM / crashes.
const LARGE_ZIP = '/tmp/test-project.zip';

test.describe('zip loading', () => {
  test.skip(!existsSync(LARGE_ZIP), 'Requires /tmp/test-project.zip');

  test('loads full project from zip without crashing', async ({ page }) => {
    test.setTimeout(120_000);
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.on('crash', () => errors.push('PAGE CRASHED'));

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/viewer');

    const input = page.locator('input[type=file]').first();
    await input.setInputFiles(LARGE_ZIP);

    // Wait for the project to load — schematic symbols appearing means
    // parsing succeeded without crashing.
    await page.waitForSelector('[data-refdes]', { timeout: 60_000 });

    // No error toast
    const toastCount = await page.locator('.toast').count();
    expect(toastCount).toBe(0);

    console.log('Page errors:', errors);
    expect(errors).toEqual([]);
  });
});
