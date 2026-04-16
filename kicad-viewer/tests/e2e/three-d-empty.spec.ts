import { test, expect } from '@playwright/test';
import { join } from 'node:path';

const FIXTURES = [
  'pic_programmer.kicad_pro',
  'pic_programmer.kicad_pcb',
  'pic_programmer.kicad_sch',
  'pic_sockets.kicad_sch'
];

async function loadProject(page: import('@playwright/test').Page) {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/viewer');
  const input = page.locator('input[type=file]').first();
  await input.setInputFiles(FIXTURES.map((f) => join('tests/fixtures', f)));
  await expect(page.getByText('kicad-viewer').first()).toBeVisible();
}

test('3D tab: shows drop-to-load state when no STEP or GLB in the project', async ({ page }) => {
  await loadProject(page);
  await page.getByRole('tab', { name: '3D' }).click();

  // Empty region should be visible with the new STEP-aware copy.
  const empty = page.locator('[aria-label="Drop a 3D model file"]');
  await expect(empty).toBeVisible();
  await expect(empty).toContainText(/\.step/i);
  await expect(empty).toContainText(/\.glb/i);

  // The file picker accepts STEP + GLB.
  const picker = empty.locator('input[type=file]');
  await expect(picker).toHaveAttribute('accept', /\.step|\.stp|\.glb/);
});
