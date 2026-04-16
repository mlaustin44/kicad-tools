<script lang="ts">
  import { settings } from '$lib/stores/settings';

  interface Props {
    open: boolean;
    onClose: () => void;
  }
  let { open, onClose }: Props = $props();

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') onClose();
  }

  function onOpacityInput(e: Event) {
    const v = Number((e.target as HTMLInputElement).value);
    settings.update((s) => ({ ...s, inactiveLayerOpacity: v }));
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if open}
  <div class="backdrop" onclick={onClose} role="presentation">
    <div
      class="modal"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-label="Settings"
      aria-modal="true"
      tabindex="-1"
    >
      <header>
        <h3>Settings</h3>
        <button class="close" onclick={onClose} aria-label="Close settings">✕</button>
      </header>

      <section>
        <h4>Display</h4>
        <label class="field">
          <span class="label-text">Inactive layer opacity</span>
          <input
            type="range"
            min="0"
            max="0.8"
            step="0.05"
            value={$settings.inactiveLayerOpacity}
            oninput={onOpacityInput}
          />
          <span class="value">{Math.round($settings.inactiveLayerOpacity * 100)}%</span>
        </label>
      </section>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5);
    display: flex; align-items: center; justify-content: center;
    z-index: 100;
  }
  .modal {
    background: var(--kv-surface);
    border: 1px solid var(--kv-border);
    border-radius: 8px;
    min-width: 360px;
    max-width: 480px;
    color: var(--kv-text);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.75rem 1rem; border-bottom: 1px solid var(--kv-border);
  }
  header h3 { margin: 0; font-size: 0.95rem; }
  .close {
    background: transparent; border: none; color: var(--kv-text-dim);
    cursor: pointer; font-size: 1rem; padding: 2px 6px;
  }
  .close:hover { color: var(--kv-text); }
  section { padding: 1rem; }
  section h4 {
    margin: 0 0 0.75rem;
    font-size: 0.7rem; letter-spacing: 0.08em;
    color: var(--kv-text-dim); text-transform: uppercase;
  }
  .field {
    display: grid; grid-template-columns: 1fr 160px auto; gap: 0.75rem;
    align-items: center; font-size: 0.85rem;
  }
  .value { color: var(--kv-text-dim); min-width: 3ch; text-align: right; }
</style>
