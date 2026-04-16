<script lang="ts">
  import { toggleTheme, theme } from '$lib/stores/theme';
</script>

<svelte:head>
  <title>kicad-viewer — by Matthew Austin</title>
  <meta name="description" content="Browser-based KiCad project viewer with schematic, PCB, and 3D views and cross-probing." />
</svelte:head>

<main class="landing">
  <header class="top">
    <span class="eyebrow">KICAD-VIEWER / MATTHEW AUSTIN</span>
    <button class="theme" onclick={toggleTheme} aria-label="Toggle theme">
      {$theme === 'dark' ? '☾' : '☀'}
    </button>
  </header>

  <section class="hero">
    <h1>A browser-based KiCad project viewer.</h1>
    <p>
      Schematic, PCB, and 3D views in one place, with full cross-probing between them.
      Drop a project folder or <code>.zip</code> and it renders — no upload, no install,
      runs entirely in your browser.
    </p>
    <nav class="cta">
      <a class="btn btn-primary" href="/viewer">Open viewer →</a>
      <a class="btn btn-secondary" href="https://github.com/mlaustin44/kicad-tools">GitHub</a>
    </nav>
  </section>

  <footer class="credit">Built by Matthew Austin, 2026</footer>
</main>

<style>
  .landing {
    min-height: 100dvh;
    display: grid;
    grid-template-rows: auto 1fr auto;
    padding: 2rem 4rem;
    max-width: 1100px; margin: 0 auto;
  }
  .top { display: flex; justify-content: space-between; align-items: center; }
  .eyebrow {
    font-size: 0.7rem; letter-spacing: 0.2em; color: var(--kv-text-dim);
  }
  .theme {
    background: transparent; border: 1px solid var(--kv-border);
    border-radius: 8px; padding: 6px 10px; color: var(--kv-text);
  }
  .hero { align-self: center; max-width: 640px; }
  .hero h1 {
    font-size: clamp(1.75rem, 4vw, 2.75rem);
    line-height: 1.1; font-weight: 600; margin: 0 0 1rem;
  }
  .hero p {
    color: var(--kv-text-dim); max-width: 52ch; line-height: 1.55;
    margin: 0 0 1.5rem;
  }
  .cta { display: flex; gap: 0.75rem; }
  .btn {
    padding: 0.6rem 1.1rem; border-radius: 8px;
    font-size: 0.9rem; text-decoration: none;
    border: 1px solid var(--kv-border);
  }
  .btn-primary { background: var(--kv-text); color: var(--kv-bg); border-color: var(--kv-text); }
  .btn-secondary { background: var(--kv-surface); color: var(--kv-text); }
  .credit { font-size: 0.75rem; color: var(--kv-text-dim); padding-top: 2rem; }
</style>
