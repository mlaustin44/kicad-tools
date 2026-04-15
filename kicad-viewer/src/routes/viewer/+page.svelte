<script lang="ts">
  import Shell from '$lib/ui/Shell.svelte';
  import DropZone from '$lib/ui/DropZone.svelte';
  import Toast from '$lib/ui/Toast.svelte';
  import { project } from '$lib/stores/project';

  let tab = $state('sch');
</script>

<svelte:head><title>Viewer — kicad-viewer</title></svelte:head>

{#if $project}
  <Shell {tab} onTabChange={(v) => (tab = v)}>
    {#snippet sidebar()}<div class="panel">sidebar ({tab})</div>{/snippet}
    {#snippet inspector()}<div class="panel">inspector</div>{/snippet}
    <div class="stage">render area ({tab})</div>
  </Shell>
{:else}
  <main class="empty"><DropZone /></main>
{/if}

<Toast />

<style>
  .empty { padding: 3rem; min-height: 100dvh; display: grid; place-items: center; background: var(--kv-bg); }
  .panel, .stage { padding: 1rem; color: var(--kv-text-dim); }
  .stage { color: var(--kv-text); }
</style>
