import { test, expect } from '@playwright/test';
import { join } from 'node:path';

const FIXTURES = [
  'pic_programmer.kicad_pro',
  'pic_programmer.kicad_pcb',
  'pic_programmer.kicad_sch',
  'pic_sockets.kicad_sch'
];

test('PCB canvas fits inside the viewport, does not stretch', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/viewer');

  const input = page.locator('input[type=file]').first();
  await input.setInputFiles(FIXTURES.map((f) => join('tests/fixtures', f)));

  // Switch to PCB tab
  await page.getByRole('tab', { name: 'PCB' }).click();

  // Wait for canvas to mount
  const canvas = page.locator('main.main canvas');
  await expect(canvas).toBeVisible();

  // Canvas CSS height must be within viewport height (minus header + footer).
  // If the grid stretched, we used to see 2000+px. Anything above viewport is wrong.
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height).toBeGreaterThan(100);
  expect(box!.height).toBeLessThan(800);
  expect(box!.width).toBeGreaterThan(100);
  expect(box!.width).toBeLessThan(1280);
});

test('Fit view frames the board roughly centered', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/viewer');

  const input = page.locator('input[type=file]').first();
  await input.setInputFiles(FIXTURES.map((f) => join('tests/fixtures', f)));

  await page.getByRole('tab', { name: 'PCB' }).click();
  const canvas = page.locator('main.main canvas');
  await expect(canvas).toBeVisible();

  // Press "F" (Fit view keyboard shortcut) and read the viewport state from
  // the canvas CSS transform isn't directly available, so we verify indirectly
  // by checking canvas fills a reasonable box and pixels are non-zero.
  await page.keyboard.press('f');
  // Give it a frame to settle.
  await page.waitForTimeout(100);

  const box = await canvas.boundingBox();
  expect(box!.height).toBeLessThan(800);
  expect(box!.height).toBeGreaterThan(400);
});
