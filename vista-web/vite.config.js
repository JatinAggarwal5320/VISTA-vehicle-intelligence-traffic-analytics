import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  resolve: { conditions: ['onnxruntime-web-use-extern-wasm'] },
  build: {
    rollupOptions: {
      input: {
        dashboard: resolve(process.cwd(), 'index.html'),
        browser: resolve(process.cwd(), 'browser.html'),
      },
    },
  },
});
