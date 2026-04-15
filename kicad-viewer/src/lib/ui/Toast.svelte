<script lang="ts">
  import { toasts, dismissToast } from '$lib/stores/toasts';
</script>

<div class="stack" role="status" aria-live="polite">
  {#each $toasts as t (t.id)}
    <div class="toast {t.kind}" onclick={() => dismissToast(t.id)}>
      {t.message}
    </div>
  {/each}
</div>

<style>
  .stack { position: fixed; right: 1rem; bottom: 1rem; display: grid; gap: 0.5rem; z-index: 100; }
  .toast {
    padding: 0.6rem 0.9rem; border-radius: 8px;
    background: var(--kv-surface-2); border: 1px solid var(--kv-border);
    color: var(--kv-text); font-size: 0.85rem; cursor: pointer; max-width: 340px;
  }
  .toast.error { border-color: #d14b4b; }
</style>
