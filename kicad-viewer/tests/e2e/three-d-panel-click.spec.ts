import { test, expect } from '@playwright/test';
import { existsSync } from 'node:fs';

const OHM_DIR = '/home/mlaustin/electronics/ohm_kicad_designs/ohm_lamp_v2_usb_r3';
const OHM_PCB = `${OHM_DIR}/ohm_lamp_v2_usb_r3.kicad_pcb`;
const OHM_SCH = `${OHM_DIR}/ohm_lamp_v2_usb_r3.kicad_sch`;
const OHM_PRO = `${OHM_DIR}/ohm_lamp_v2_usb_r3.kicad_pro`;
const OHM_GLB = `${OHM_DIR}/usb_3-1.glb`;
const haveFixtures = [OHM_PCB, OHM_SCH, OHM_PRO, OHM_GLB].every((p) => existsSync(p));

test.describe('3D panel click repro', () => {
  test.skip(!haveFixtures, 'Requires local ohm-lamp fixture');

  test('clicking component from sidebar keeps 3D view visible', async ({ page }) => {
    test.setTimeout(90_000);
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/viewer');

    // Load project
    await page.locator('input[type=file]').first().setInputFiles([OHM_PCB, OHM_SCH, OHM_PRO]);
    await expect(page.getByText('kicad-viewer').first()).toBeVisible();

    // Switch to 3D, load GLB
    await page.getByRole('tab', { name: '3D' }).click();
    const modelInput = page.locator('[aria-label="Drop a 3D model file"] input[type=file]');
    await modelInput.setInputFiles(OHM_GLB);
    await page.waitForFunction(
      () => (window as unknown as { __kv3d?: { refdesCount: number } }).__kv3d?.refdesCount != null,
      { timeout: 45_000 }
    );

    // Screenshot before panel click
    await page.screenshot({ path: 'test-results/panel-click-1-before.png' });

    // Click a component from the sidebar Components tab
    await page.getByRole('tab', { name: 'Components' }).click();
    const item = page.locator('.item', { has: page.locator('.refdes', { hasText: /^U3$/ }) }).first();
    await item.click();

    // Wait a beat for camera to settle
    await page.waitForTimeout(500);

    // Dump camera state to help diagnose black viewport
    const camState = await page.evaluate(() => {
      const kv = (window as unknown as {
        __kv3d?: {
          screenPosFor: (r: string) => { x: number; y: number } | null;
          getCameraState: () => unknown;
        };
      }).__kv3d;
      return {
        screenPos: kv?.screenPosFor?.('U3'),
        camera: kv?.getCameraState?.()
      };
    });
    console.log('camera state after panel click:', JSON.stringify(camState, null, 2));

    // Screenshot after panel click
    await page.screenshot({ path: 'test-results/panel-click-2-after.png' });

    // Must still be on 3D tab
    await expect(page.getByRole('tab', { name: '3D' })).toHaveAttribute('aria-selected', 'true');

    // Inspector should show U3
    await expect(page.locator('aside.side.right h3')).toHaveText('U3');

    // PCB tab must still work
    await page.getByRole('tab', { name: 'PCB' }).click();
    await page.waitForTimeout(200);
    await page.screenshot({ path: 'test-results/panel-click-3-pcb.png' });
    await expect(page.getByRole('tab', { name: 'PCB' })).toHaveAttribute('aria-selected', 'true');

    // Back to 3D should also work
    await page.getByRole('tab', { name: '3D' }).click();
    await page.waitForTimeout(200);
    await expect(page.getByRole('tab', { name: '3D' })).toHaveAttribute('aria-selected', 'true');

    if (errors.length > 0) console.log('Page errors:', errors);
    expect(errors).toEqual([]);
  });
});
