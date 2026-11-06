import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    host: true,
    port: 5173,
    // Allow access through SSH local port-forwarding (Host header may vary).
    allowedHosts: true,
    // Dev mode: same-origin relative paths are proxied to FastAPI. /edge is
    // served by the brain's edge gateway (which then reaches 8080); /uploads
    // holds images saved by the upload route. Both are same-origin in the
    // production build and only need a proxy here under the Vite dev server.
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/mock': { target: 'http://localhost:8000', changeOrigin: true },
      '/edge': { target: 'http://localhost:8000', changeOrigin: true },
      '/middle': { target: 'http://localhost:8000', changeOrigin: true },
      '/uploads': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
