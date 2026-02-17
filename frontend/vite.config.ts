import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0', // 👈 This allows the container to talk to your Mac
    port: 5173,      // 👈 Matches the port in your docker-compose
    strictPort: true,
    watch: {
      usePolling: true, // 👈 Ensures hot-reload works on macOS Docker
    }
  }
})