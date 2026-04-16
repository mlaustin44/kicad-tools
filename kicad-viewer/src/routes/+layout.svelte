<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { theme } from '$lib/stores/theme';
  let { children } = $props();

  onMount(() => {
    document.body.setAttribute('data-theme', $theme);
  });

  $effect(() => {
    if (typeof document !== 'undefined') {
      document.body.setAttribute('data-theme', $theme);
    }
  });
</script>

{@render children()}
