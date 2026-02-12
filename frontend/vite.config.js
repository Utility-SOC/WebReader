import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // Listen on all addresses (needed for Docker)
    proxy: {
      '/health': { target: process.env.API_TARGET || 'http://localhost:8000', changeOrigin: true },
      '/upload': { target: process.env.API_TARGET || 'http://localhost:8000', changeOrigin: true },
      '/upload_temp': { target: process.env.API_TARGET || 'http://localhost:8000', changeOrigin: true },
      '/process_pdf': { target: process.env.API_TARGET || 'http://localhost:8000', changeOrigin: true },
      '/tasks': { target: process.env.API_TARGET || 'http://localhost:8000', changeOrigin: true },
      '/pdf': { target: process.env.API_TARGET || 'http://localhost:8000', changeOrigin: true },
      '/tts': { target: process.env.API_TARGET || 'http://localhost:8000', changeOrigin: true },
    }
  }
})
