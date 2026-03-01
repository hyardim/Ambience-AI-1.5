import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'

// Use 'backend' service name in Docker, fallback to localhost for local dev
const backendUrl = process.env.DOCKER_ENV === 'true'
  ? 'http://backend:8000'
  : 'http://localhost:8000';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: true,
    },
    proxy: {
      '/auth': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/chats': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/specialist/queue': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/specialist/assigned': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/specialist/chats': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/notifications': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/admin': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/search': {
        target: backendUrl,
        changeOrigin: true,
      },
      '/health': {
        target: backendUrl,
        changeOrigin: true,
      },
    },
  },
})
