import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
const here = dirname(fileURLToPath(import.meta.url));
export default defineConfig({
  plugins: [react()],
  publicDir: 'public',
  server: { host: true, port: 5173, fs: { allow: [resolve(here, '../..')] } },
  resolve: { alias: { '@': resolve(here, 'src') } },
  build: { outDir: 'dist', sourcemap: false },
});
