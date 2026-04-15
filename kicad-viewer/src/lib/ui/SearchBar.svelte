<script lang="ts">
  import { componentsByRefdes, netsByName } from '$lib/stores/project';
  import { selectComponent, selectNet } from '$lib/stores/selection';

  interface Props { open: boolean; onClose: () => void; }
  let { open, onClose }: Props = $props();

  let query = $state('');

  type Result =
    | { k: 'c'; uuid: string; refdes: string; value: string }
    | { k: 'n'; name: string };

  let results = $derived.by<Result[]>(() => {
    if (!query.trim()) return [];
    const q = query.toUpperCase();
    const comps = [...$componentsByRefdes.values()]
      .filter((c) => c.refdes.toUpperCase().includes(q) || c.value.toUpperCase().includes(q))
      .slice(0, 8)
      .map((c): Result => ({ k: 'c', uuid: c.uuid, refdes: c.refdes, value: c.value }));
    const nets = [...$netsByName.values()]
      .filter((n) => n.name.toUpperCase().includes(q))
      .slice(0, 8)
      .map((n): Result => ({ k: 'n', name: n.name }));
    return [...comps, ...nets];
  });

  function pick(r: Result) {
    if (r.k === 'c') selectComponent({ uuid: r.uuid, source: 'search' });
    else selectNet({ name: r.name, source: 'search' });
    onClose();
    query = '';
  }
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="overlay" onclick={onClose} role="presentation">
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <!-- svelte-ignore a11y_interactive_supports_focus -->
    <div class="box" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="Search">
      <!-- svelte-ignore a11y_autofocus -->
      <input
        placeholder="Search refdes or net..."
        bind:value={query}
        autofocus
        onkeydown={(e) => { if (e.key === 'Escape') onClose(); }}
      />
      <ul>
        {#each results as r}
          <li>
            <button type="button" onclick={() => pick(r)}>
              {#if r.k === 'c'}<strong>{r.refdes}</strong> {r.value}{:else}<em>{r.name}</em>{/if}
            </button>
          </li>
        {/each}
      </ul>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.4);
    display: grid; place-items: start center; padding-top: 15vh; z-index: 50;
  }
  .box {
    width: 520px; background: var(--kv-surface); border: 1px solid var(--kv-border);
    border-radius: 10px; padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);
  }
  input {
    width: 100%; padding: 8px 10px; font-size: 1rem;
    border: 1px solid var(--kv-border); border-radius: 6px;
    background: var(--kv-bg); color: var(--kv-text);
    box-sizing: border-box;
  }
  ul { list-style: none; padding: 0; margin: 8px 0 0; max-height: 280px; overflow: auto; }
  li button {
    display: block; width: 100%; text-align: left;
    padding: 6px 8px; border: none; background: transparent;
    color: var(--kv-text); font: inherit; border-radius: 4px;
  }
  li button:hover { background: var(--kv-surface-2); }
</style>
