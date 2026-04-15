<script lang="ts">
  import DropZone from '$lib/ui/DropZone.svelte';
  import Toast from '$lib/ui/Toast.svelte';
  import { project } from '$lib/stores/project';
</script>

<svelte:head><title>Viewer — kicad-viewer</title></svelte:head>

<main class="viewer">
  {#if $project}
    <p>Loaded: {$project.name} ({$project.components.length} components)</p>
  {:else}
    <DropZone />
  {/if}
</main>
<Toast />

<style>
  .viewer { padding: 2rem; min-height: 100dvh; }
</style>
