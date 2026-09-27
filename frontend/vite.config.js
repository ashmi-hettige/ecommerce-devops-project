import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    // Dev-only reverse proxy: one browser origin, two backend microservices.
    // In Docker/Kubernetes, Nginx / an Ingress does this same routing.
    proxy: {
      '/api/auth': 'http://127.0.0.1:8001',      // auth-service
      '/api/inventory': 'http://127.0.0.1:8002', // inventory-service
    },
  },
})
