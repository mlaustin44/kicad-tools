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
}

test('left sidebar shows Layers/Nets/Components on PCB view', async ({ page }) => {
  await loadProject(page);
  await page.getByRole('tab', { name: 'PCB' }).click();

  await expect(page.getByRole('tab', { name: 'Layers' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Nets' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Components' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Pages' })).toHaveCount(0);
});

test('left sidebar shows Pages/Nets/Components on Schematic view', async ({ page }) => {
  await loadProject(page);
  // Schematic tab is the default, but click to be explicit.
  await page.getByRole('tab', { name: 'Schematic' }).first().click();

  await expect(page.getByRole('tab', { name: 'Pages' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Nets' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Components' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Layers' })).toHaveCount(0);
});

test('clicking a component in the panel selects it (Inspector shows refdes)', async ({ page }) => {
  await loadProject(page);
  await page.getByRole('tab', { name: 'PCB' }).click();
  await page.getByRole('tab', { name: 'Components' }).click();

  // Expand any collapsed group if needed; just click the first refdes button we can find.
  // Refdes items render as <strong class="refdes">U1</strong> etc.
  const firstRefdes = page.locator('.refdes').first();
  const refdesText = await firstRefdes.textContent();
  await firstRefdes.click();

  // Inspector's h3 should show that refdes.
  const inspectorHeading = page.locator('aside.side.right h3');
  await expect(inspectorHeading).toHaveText(refdesText!.trim());
});

test('nets panel groups power rails separately from signals', async ({ page }) => {
  await loadProject(page);
  await page.getByRole('tab', { name: 'PCB' }).click();
  await page.getByRole('tab', { name: 'Nets' }).click();

  // The fixture project has at least GND and other nets.
  const groupHeaders = page.locator('.group-hdr .group-name');
  const texts = await groupHeaders.allTextContents();
  expect(texts).toContain('Power');
  expect(texts).toContain('Signals');
});
