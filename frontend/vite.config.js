import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev the Vite server proxies /api to FastAPI, so no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
  test: { environment: 'jsdom', setupFiles: './src/setupTests.js', globals: true },
})
