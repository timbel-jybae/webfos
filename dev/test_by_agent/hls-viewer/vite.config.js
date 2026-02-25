import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // .env 파일 로드 (VITE_ 접두사 변수만 클라이언트에 노출)
  const env = loadEnv(mode, process.cwd(), '')
  const apiPort = env.VITE_API_PORT || '32055'
  const apiHost = env.VITE_API_HOST || 'localhost'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      host: true,
      proxy: {
        '/api': {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})
