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

test('cross-probe: selecting a bottom-side part switches PCB active layer to B.Cu', async ({ page }) => {
  // JP1 is on B.Cu in the pic_programmer fixture.
  await loadProject(page);

  // Pick JP1 from the schematic (it lives on the root sheet).
  const jp1 = page.locator('[data-refdes="JP1"]').first();
  await expect(jp1).toBeAttached({ timeout: 10_000 });
  await jp1.click({ force: true });

  // Move to PCB — active layer in the layer panel should show B.Cu active.
  await page.getByRole('tab', { name: 'PCB' }).click();
  await page.getByRole('tab', { name: 'Layers' }).click();
  await expect(page.locator('#layer-panel .row.active')).toHaveAttribute('data-layer-id', 'B.Cu');
});

test('cross-probe: selecting a top-side part returns active layer to F.Cu', async ({ page }) => {
  // JP1 is bottom (B.Cu). J1 is top and lives on the root sheet (F.Cu).
  await loadProject(page);

  await page.getByRole('tab', { name: 'PCB' }).click();
  await page.getByRole('tab', { name: 'Layers' }).click();
  const activeRow = page.locator('#layer-panel .row.active');
  await expect(activeRow).toHaveAttribute('data-layer-id', 'F.Cu');

  // Flip to B.Cu manually, cross-probe to a top-side part, verify flip back.
  await page.locator('#layer-panel [data-layer-id="B.Cu"]').click();
  await expect(activeRow).toHaveAttribute('data-layer-id', 'B.Cu');

  await page.getByRole('tab', { name: 'Schematic' }).first().click();
  const j1 = page.locator('[data-refdes="J1"]').first();
  await expect(j1).toBeAttached({ timeout: 10_000 });
  await j1.click({ force: true });

  await page.getByRole('tab', { name: 'PCB' }).click();
  await expect(activeRow).toHaveAttribute('data-layer-id', 'F.Cu');
});

test('cross-probe: selecting in PCB centers the part in Schematic on next visit', async ({ page }) => {
  await loadProject(page);

  await page.getByRole('tab', { name: 'PCB' }).click();
  await page.getByRole('tab', { name: 'Components' }).click();

  // Click J1 (a connector on the root sheet) from the components list.
  const j1Btn = page.locator('.item', { has: page.locator('.refdes', { hasText: /^J1$/ }) }).first();
  await j1Btn.click();

  // Panel clicks no longer auto-switch tabs. Navigate to Schematic manually
  // to verify the sheet was prepped and J1 is centered.
  await page.getByRole('tab', { name: 'Schematic' }).first().click();
  const j1 = page.locator('[data-refdes="J1"]').first();
  await expect(j1).toBeVisible({ timeout: 5_000 });
  // Give the rAF-deferred cross-probe zoom time to commit.
  await page.waitForTimeout(200);

  const stageBox = await page.locator('.schematic-stage').boundingBox();
  const elBox = await j1.boundingBox();
  expect(stageBox).not.toBeNull();
  expect(elBox).not.toBeNull();
  const stageCenterX = stageBox!.x + stageBox!.width / 2;
  const stageCenterY = stageBox!.y + stageBox!.height / 2;
  const elCenterX = elBox!.x + elBox!.width / 2;
  const elCenterY = elBox!.y + elBox!.height / 2;

  // Symbol center should be within 100px of stage center.
  expect(Math.abs(elCenterX - stageCenterX)).toBeLessThan(100);
  expect(Math.abs(elCenterY - stageCenterY)).toBeLessThan(100);
});
