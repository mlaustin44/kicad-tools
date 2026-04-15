# Deploying kicad-viewer to Cloudflare Pages

## One-time setup

1. In the Cloudflare dashboard, create a Pages project connected to the GitHub
   repo `mlaustin44/kicad-tools`.
2. Build settings:
   - **Root directory:** `kicad-viewer`
   - **Build command:** `npm ci && npm run build`
   - **Output directory:** `build`
   - **Node version:** `20` — either set `NODE_VERSION=20` in the Pages env
     or rely on the repo's `.nvmrc`.
3. **Production branch:** `main`. All other branches get preview deploys.

## Per-deploy

Push to the branch. Cloudflare picks it up:

- `main` → production URL updates.
- PR branches → preview URLs posted on the PR.

## Custom domain (optional)

Add a CNAME from your domain to the Pages project once you have one.

## Local preview (matching production)

```
cd kicad-viewer
npm run build
npm run preview
```

The preview server serves the static `build/` directory — same shape that
Cloudflare Pages serves.

## No env vars in v1

The viewer is a pure client-side SPA. No backend, no secrets. A future v2
that adds upload-and-share would bind a Cloudflare R2 bucket via
`wrangler.toml` and add Pages Functions.
