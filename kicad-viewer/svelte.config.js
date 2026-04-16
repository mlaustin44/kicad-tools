import adapter from '@sveltejs/adapter-cloudflare';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      routes: {
        // Let the Worker handle all routes (SPA with client-side routing).
        include: ['/*'],
        exclude: ['<all>']
      }
    })
  }
};
