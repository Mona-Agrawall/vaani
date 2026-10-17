import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Forward /api to the FastAPI backend, so the browser never makes cross-origin requests.
// 127.0.0.1 (not "localhost") avoids hitting a different server listening on IPv6 ::1.
const proxy = { '/api': process.env.BACKEND_URL || 'http://127.0.0.1:8000' }

export default defineConfig({
  plugins: [react()],
  server: { port: 3000, proxy },
  preview: { port: 3000, proxy },
})
