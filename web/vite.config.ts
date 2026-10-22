import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the API runs on :8000. Proxying keeps the browser on one origin,
// exactly like the nginx proxy in Docker, so the sign-in cookie works the same way.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/media': 'http://localhost:8000',
    },
  },
})
