import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: parseInt(process.env.PORT || '5174'),
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://localhost:32055',
        changeOrigin: true,
      },
    },
  },
})
