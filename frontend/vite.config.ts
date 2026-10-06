import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build: ../static/spa (Django whitenoise shu yerdan beradi). Dev: `npm run dev` — Django 8000 portiga proksi.
export default defineConfig({
  plugins: [react()],
  base: '/static/spa/',
  build: { outDir: '../static/spa', emptyOutDir: true, chunkSizeWarningLimit: 900 },
  server: { port: 5173, proxy: { '^/(?!static/spa|@vite|src|node_modules).*': { target: 'http://127.0.0.1:8000', changeOrigin: true } } },
})
