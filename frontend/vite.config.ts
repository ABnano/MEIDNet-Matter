/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The built app is served by the FastAPI backend from matter/static at the site root; in development Vite serves
// the sources and proxies the API to uvicorn on port 8000.  Mode "mirror" (npm run build:mirror) builds the static
// mirror for GitHub Pages into build/mirror with relative asset paths, so any folder of any static host can serve it
// (scripts/build_mirror.py then adds the pre-rendered API).
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === 'mirror' ? './' : '/',
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000', '/openapi.json': 'http://127.0.0.1:8000' },
  },
  build: {
    outDir: mode === 'mirror' ? '../build/mirror' : '../matter/static',
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: false,
    rollupOptions: { output: { manualChunks: { react: ['react', 'react-dom', 'react-router'] } } },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    css: false,
  },
}));
