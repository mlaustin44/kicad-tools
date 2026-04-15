<script lang="ts">
  import { onMount } from 'svelte';
  import { installKeyboardShortcuts } from '$lib/keys';
  import Shell from '$lib/ui/Shell.svelte';
  import DropZone from '$lib/ui/DropZone.svelte';
  import Toast from '$lib/ui/Toast.svelte';
  import Inspector from '$lib/ui/Inspector.svelte';
  import SchematicView from '$lib/views/SchematicView.svelte';
  import { project } from '$lib/stores/project';

  let tab = $state('sch');
  let searchOpen = $state(false);
  let fitRequested = $state(0);
  let activeSheet = $derived.by(() => $project?.sheets[0]?.uuid ?? null);

  onMount(() =>
    installKeyboardShortcuts({
      setTab: (t) => (tab = t),
      onSearch: () => (searchOpen = true),
      onFit: () => fitRequested++,
      onPrevSheet: () => { /* wired in Task 20 */ },
      onNextSheet: () => { /* wired in Task 20 */ },
      onFocusLayers: () => { /* wired in Task 25 */ }
    })
  );
</script>

<svelte:head><title>Viewer — kicad-viewer</title></svelte:head>

{#if $project}
  <Shell {tab} onTabChange={(v) => (tab = v)}>
    {#snippet sidebar()}<div class="panel">sidebar ({tab})</div>{/snippet}
    {#snippet inspector()}<Inspector />{/snippet}
    {#if tab === 'sch'}
      <SchematicView activeSheetUuid={activeSheet} />
    {:else}
      <div class="stage">render area ({tab})</div>
    {/if}
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
