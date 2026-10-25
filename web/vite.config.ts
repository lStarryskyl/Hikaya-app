import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the API runs on :8000. Proxying keeps the browser on one origin,
// exactly like the nginx proxy in Docker, so the sign-in cookie works the same way.
export default defineConfig({
  plugins: [react()],
  // MapLibre loads its tile worker from a URL relative to its own module. Pre-bundling moves
  // the module, so the worker would 404 in development.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  server: {
    proxy: {
      '/api': process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
      '/media': process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000',
    },
  },
})
