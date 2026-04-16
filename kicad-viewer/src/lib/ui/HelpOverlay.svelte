<script lang="ts">
  interface Props {
    open: boolean;
    onClose: () => void;
  }
  let { open, onClose }: Props = $props();

  interface Row { keys: string[]; label: string; }
  interface Section { title: string; rows: Row[]; }

  const sections: Section[] = [
    {
      title: 'Tabs',
      rows: [
        { keys: ['1'], label: 'Schematic' },
        { keys: ['2'], label: 'PCB' },
        { keys: ['3'], label: '3D' },
        { keys: ['4'], label: 'Split' }
      ]
    },
    {
      title: 'Navigation',
      rows: [
        { keys: ['/'], label: 'Search components / nets' },
        { keys: ['f', 'Home'], label: 'Fit view' },
        { keys: ['Esc'], label: 'Clear selection' },
        { keys: ['[', ']'], label: 'Previous / next schematic sheet' },
        { keys: ['l'], label: 'Focus layers panel (PCB)' }
      ]
    },
    {
      title: '3D View',
      rows: [
        { keys: ['t'], label: 'Top view' },
        { keys: ['b'], label: 'Bottom view' },
        { keys: ['i'], label: 'Isometric view' }
      ]
    },
    {
      title: 'Mouse',
      rows: [
        { keys: ['Wheel'], label: 'Zoom at cursor' },
        { keys: ['Left-drag'], label: 'Pan (2D) / Rotate (3D)' },
        { keys: ['Middle-drag'], label: 'Pan (all views)' },
        { keys: ['Right-drag'], label: 'Pan (3D)' },
        { keys: ['Click'], label: 'Select component' },
        { keys: ['Double-click'], label: 'Enter sheet (schematic)' }
      ]
    },
    {
      title: 'Help',
      rows: [
        { keys: ['?', 'h'], label: 'Toggle this help' }
      ]
    }
  ];
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="overlay" onclick={onClose}>
    <div class="box" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Keyboard shortcuts" tabindex="-1">
      <header>
        <h2>Keyboard shortcuts</h2>
        <button type="button" onclick={onClose} aria-label="Close">&times;</button>
      </header>
      <div class="sections">
        {#each sections as section}
          <section>
            <h3>{section.title}</h3>
            <dl>
              {#each section.rows as row}
                <dt>
                  {#each row.keys as k, i}
                    <kbd>{k}</kbd>{#if i < row.keys.length - 1}<span class="sep">/</span>{/if}
                  {/each}
                </dt>
                <dd>{row.label}</dd>
              {/each}
            </dl>
          </section>
        {/each}
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed; inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: grid; place-items: center;
    z-index: 60;
    padding: 2rem;
  }
  .box {
    width: min(720px, 100%);
    max-height: 80vh; overflow: auto;
    background: var(--kv-surface); border: 1px solid var(--kv-border);
    border-radius: 10px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
  }
  header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.75rem 1.25rem; border-bottom: 1px solid var(--kv-border);
  }
  header h2 { margin: 0; font-size: 1rem; font-weight: 600; }
  header button {
    background: transparent; border: none; color: var(--kv-text-dim);
    font-size: 1.4rem; line-height: 1; cursor: pointer; padding: 0;
  }
  .sections {
    padding: 1rem 1.25rem;
    display: grid; gap: 1.25rem;
    grid-template-columns: 1fr 1fr;
  }
  section h3 {
    margin: 0 0 0.5rem; font-size: 0.7rem; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--kv-text-dim);
  }
  dl {
    display: grid; grid-template-columns: auto 1fr;
    gap: 0.25rem 0.75rem; margin: 0; font-size: 0.85rem;
  }
  dt { display: flex; gap: 0.25rem; align-items: center; }
  dd { margin: 0; color: var(--kv-text-dim); }
  .sep { color: var(--kv-text-dim); font-size: 0.8rem; }
  kbd {
    display: inline-block;
    padding: 1px 6px;
    font-family: var(--kv-font-mono);
    font-size: 0.75rem;
    background: var(--kv-surface-2);
    border: 1px solid var(--kv-border);
    border-radius: 4px;
  }
</style>
