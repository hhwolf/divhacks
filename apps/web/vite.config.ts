import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { cpSync, createReadStream, mkdirSync, statSync, writeFileSync } from 'node:fs';
import type { Plugin } from 'vite';
const here = dirname(fileURLToPath(import.meta.url));
const MIME: Record<string, string> = { '.json': 'application/json', '.glb': 'model/gltf-binary', '.png': 'image/png', '.jpg': 'image/jpeg', '.html': 'text/html', '.txt': 'text/plain' };
/**
 * Dev: serve /assets and /fixtures from the repo root. public/assets and public/fixtures are git symlinks, which a
 * Windows checkout (core.symlinks=false) turns into plain text files, so without this the GLBs/manifest 404 there.
 */
const serveRepoDirs = (): Plugin => ({
  name: 'arp-serve-repo-dirs',
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const url = decodeURIComponent((req.url ?? '').split('?')[0]);
      if (!/^\/(assets|fixtures)\//.test(url) || url.includes('..')) return next();
      const file = resolve(here, '../..', `.${url}`);
      try { if (!statSync(file).isFile()) return next(); } catch { return next(); }
      res.setHeader('Content-Type', MIME[url.slice(url.lastIndexOf('.'))] ?? 'application/octet-stream');
      createReadStream(file).pipe(res);
    });
  },
});
/** Copies ../../assets and ../../fixtures into dist so the static deploy doesn't depend on the dev-server symlinks. */
const copyAssets = () => ({
  name: 'arp-copy-assets',
  closeBundle() {
    for (const dir of ['assets', 'fixtures']) { mkdirSync(resolve(here, 'dist', dir), { recursive: true }); cpSync(resolve(here, '../..', dir), resolve(here, 'dist', dir), { recursive: true, dereference: true }); }
    // SPA rewrites for a static Vercel deploy of dist/
    writeFileSync(resolve(here, 'dist/vercel.json'), JSON.stringify({ rewrites: [{ source: '/(.*)', destination: '/index.html' }] }));
  },
});
export default defineConfig({
  plugins: [react(), serveRepoDirs(), copyAssets()],
  publicDir: 'public',
  server: { host: true, port: 5173, fs: { allow: [resolve(here, '../..')] } },
  resolve: { alias: { '@': resolve(here, 'src') } },
  build: { outDir: 'dist', sourcemap: false },
});
