import { test, expect } from '@playwright/test';
import { join } from 'node:path';

const FIXTURES = [
  'pic_programmer.kicad_pro',
  'pic_programmer.kicad_pcb',
  'pic_programmer.kicad_sch',
  'pic_sockets.kicad_sch'
];

test('drop project, click a schematic symbol, PCB reacts to selection', async ({ page }) => {
  await page.goto('/viewer');

  // Seed files via the file-picker input that DropZone exposes (hidden input).
  const input = page.locator('input[type=file]').first();
  await input.setInputFiles(FIXTURES.map((f) => join('tests/fixtures', f)));

  // Shell should appear — top bar has 'kicad-viewer'.
  await expect(page.getByText('kicad-viewer').first()).toBeVisible();

  // Schematic tab should be active by default — find a refdes group, click it.
  const firstSymbol = page.locator('[data-refdes]').first();
  await expect(firstSymbol).toBeAttached({ timeout: 10_000 });
  const refdes = await firstSymbol.getAttribute('data-refdes');
  expect(refdes).toBeTruthy();
  await firstSymbol.click({ force: true });  // force: click even if occluded by pan surface

  // Inspector (right sidebar) should show the refdes in the header.
  await expect(page.locator('.side.right h3').first()).toContainText(refdes!);

  // Switch to PCB tab — the inspector retains the same selection (header still matches).
  await page.getByRole('tab', { name: 'PCB' }).click();
  await expect(page.locator('.side.right h3').first()).toContainText(refdes!);
});
