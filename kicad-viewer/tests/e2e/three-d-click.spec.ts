import { test, expect } from '@playwright/test';
import { existsSync } from 'node:fs';

// This spec exercises the real-world failure modes the user hit: loading a
// populated kicad-cli GLB (thousands of meshes), confirming refdes matching
// survives the optimize-on-load pass, and that raycast clicks dispatched at
// the projected screen coordinate of a known component actually select it.
//
// Uses the user's local project + GLB. Skipped automatically on machines
// where those files aren't present.

const OHM_DIR = '/home/mlaustin/electronics/ohm_kicad_designs/ohm_lamp_v2_usb_r3';
const OHM_PCB = `${OHM_DIR}/ohm_lamp_v2_usb_r3.kicad_pcb`;
const OHM_SCH = `${OHM_DIR}/ohm_lamp_v2_usb_r3.kicad_sch`;
const OHM_PRO = `${OHM_DIR}/ohm_lamp_v2_usb_r3.kicad_pro`;
const OHM_GLB = `${OHM_DIR}/usb_3-1.glb`;

const haveFixtures = [OHM_PCB, OHM_SCH, OHM_PRO, OHM_GLB].every((p) => existsSync(p));

test.describe('ohm-lamp GLB click-to-select (requires local fixture)', () => {
  test.skip(!haveFixtures, 'Local ohm-lamp fixture or GLB not present on this machine');

  test('refdes matching survives the merge-optimize pass', async ({ page }) => {
    test.setTimeout(60_000);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/viewer');

    const projInput = page.locator('input[type=file]').first();
    await projInput.setInputFiles([OHM_PCB, OHM_SCH, OHM_PRO]);
    await expect(page.getByText('kicad-viewer').first()).toBeVisible();

    await page.getByRole('tab', { name: '3D' }).click();

    // Pick the GLB via the empty-state input.
    const modelInput = page.locator('[aria-label="Drop a 3D model file"] input[type=file]');
    await modelInput.setInputFiles(OHM_GLB);

    // Wait for the loading overlay to go away. (GLB is fast, STEP is slow.)
    // Wait for the model to finish loading AND refdes matching to complete.
    // Checking the debug hook directly is more reliable than watching DOM
    // transients like the loading overlay which can flash too fast.
    await page.waitForFunction(
      () => (window as unknown as { __kv3d?: { refdesCount: number } }).__kv3d?.refdesCount != null,
      { timeout: 45_000 }
    );

    const info = await page.evaluate(() => {
      const kv = (window as unknown as { __kv3d?: { refdesCount: number; refdesList: string[] } }).__kv3d;
      if (!kv) return null;
      return { refdesCount: kv.refdesCount, first5: kv.refdesList.slice(0, 5) };
    });
    expect(info).not.toBeNull();
    expect(info!.refdesCount).toBeGreaterThan(10);
    console.log(`matched ${info!.refdesCount} refdes, first 5: ${info!.first5.join(', ')}`);
  });

  test('clicking a component in the 3D canvas stays on 3D and selects in the Inspector', async ({ page }) => {
    test.setTimeout(60_000);
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`);
    });

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/viewer');

    const projInput = page.locator('input[type=file]').first();
    await projInput.setInputFiles([OHM_PCB, OHM_SCH, OHM_PRO]);
    await expect(page.getByText('kicad-viewer').first()).toBeVisible();

    await page.getByRole('tab', { name: '3D' }).click();
    const modelInput = page.locator('[aria-label="Drop a 3D model file"] input[type=file]');
    await modelInput.setInputFiles(OHM_GLB);
    await page.waitForFunction(
      () => (window as unknown as { __kv3d?: { refdesCount: number } }).__kv3d?.refdesCount != null,
      { timeout: 45_000 }
    );

    // Sanity: 3D tab is currently selected.
    await expect(page.getByRole('tab', { name: '3D' })).toHaveAttribute('aria-selected', 'true');

    // Pick a refdes that lives inside the viewport. The default iso framing
    // zooms to the whole board so nearly any component is in-frame; we still
    // try a handful in case the first lands behind a taller neighbor.
    const clickPlan = await page.evaluate(() => {
      const kv = (window as unknown as {
        __kv3d?: {
          refdesList: string[];
          screenPosFor(refdes: string): { x: number; y: number } | null;
        };
      }).__kv3d;
      if (!kv) return null;
      // Prefer larger parts (ICs, connectors) — more reliable raycast targets.
      const priority = ['U', 'J', 'D', 'Q', 'C', 'R'];
      const byPrefix = (r: string) => priority.findIndex((p) => r.startsWith(p));
      const sorted = [...kv.refdesList].sort((a, b) => {
        const ap = byPrefix(a); const bp = byPrefix(b);
        return (ap === -1 ? 99 : ap) - (bp === -1 ? 99 : bp);
      });
      for (const r of sorted) {
        const pos = kv.screenPosFor(r);
        if (pos && pos.x > 50 && pos.y > 50 && pos.x < 1200 && pos.y < 750) {
          return { refdes: r, pos };
        }
      }
      return null;
    });
    expect(clickPlan, 'expected at least one refdes with a screen-space position').not.toBeNull();
    console.log(`clicking refdes ${clickPlan!.refdes} at (${clickPlan!.pos.x}, ${clickPlan!.pos.y})`);

    // Screenshot the 3D view before click so we can eyeball the render quality.
    await page.screenshot({
      path: 'test-results/ohm-lamp-3d-before-click.png',
      fullPage: false
    });

    await page.mouse.click(clickPlan!.pos.x, clickPlan!.pos.y);

    // Inspector should now show the clicked refdes in its heading.
    const h3 = page.locator('aside.side.right h3');
    await expect(h3).toHaveText(clickPlan!.refdes, { timeout: 5_000 });

    // After selection settles, screenshot again to confirm the highlight landed.
    await page.waitForTimeout(300);
    await page.screenshot({
      path: 'test-results/ohm-lamp-3d-after-click.png',
      fullPage: false
    });

    // Still on the 3D tab — we should NOT have been booted to schematic.
    await expect(page.getByRole('tab', { name: '3D' })).toHaveAttribute('aria-selected', 'true');

    // Tab buttons must still be functional — click PCB, ensure it switches.
    await page.getByRole('tab', { name: 'PCB' }).click();
    await expect(page.getByRole('tab', { name: 'PCB' })).toHaveAttribute('aria-selected', 'true');

    // And back to 3D.
    await page.getByRole('tab', { name: '3D' }).click();
    await expect(page.getByRole('tab', { name: '3D' })).toHaveAttribute('aria-selected', 'true');

    if (errors.length > 0) {
      console.log('Page errors during test:\n' + errors.join('\n'));
    }
    expect(errors, 'No JS errors should fire during the 3D click flow').toEqual([]);
  });
});
