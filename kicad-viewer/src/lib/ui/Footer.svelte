<script lang="ts">
  interface Props { projectName?: string; cursorMm?: { x: number; y: number } | null; }
  let { projectName = '', cursorMm = null }: Props = $props();
</script>

<footer>
  <span>{projectName}</span>
  <span>{cursorMm ? `${cursorMm.x.toFixed(3)}, ${cursorMm.y.toFixed(3)} mm` : ''}</span>
  <span class="credit">Built by Matthew Austin, 2026</span>
</footer>

<style>
  footer {
    display: grid; grid-template-columns: 1fr auto auto;
    gap: 1rem; padding: 4px 12px;
    border-top: 1px solid var(--kv-border);
    background: var(--kv-surface);
    font-size: 0.72rem; color: var(--kv-text-dim);
  }
  .credit { font-style: italic; }
</style>
