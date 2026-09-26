import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { cpSync, mkdirSync, writeFileSync } from 'node:fs';
const here = dirname(fileURLToPath(import.meta.url));
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
  plugins: [react(), copyAssets()],
  publicDir: 'public',
  server: { host: true, port: 5173, fs: { allow: [resolve(here, '../..')] } },
  resolve: { alias: { '@': resolve(here, 'src') } },
  build: { outDir: 'dist', sourcemap: false },
});
