import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // Listen on all addresses (needed for Docker)
    proxy: {
      '/health': process.env.API_TARGET || 'http://localhost:8000',
      '/upload': process.env.API_TARGET || 'http://localhost:8000',
      '/upload_temp': process.env.API_TARGET || 'http://localhost:8000',
      '/process_pdf': process.env.API_TARGET || 'http://localhost:8000',
      '/tasks': process.env.API_TARGET || 'http://localhost:8000',
      '/pdf': process.env.API_TARGET || 'http://localhost:8000',
      '/tts': process.env.API_TARGET || 'http://localhost:8000',
    }
  }
})
