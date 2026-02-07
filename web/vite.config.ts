import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/plotly.js') || id.includes('node_modules/react-plotly.js')) {
            return 'plotly'
          }
          if (id.includes('node_modules/react-markdown')) {
            return 'markdown'
          }
        },
      },
    },
  },
  server: {
    port: 3000,
    // 开发模式代理配置
    // 使用场景：npm run dev 时通过 Vite 代理访问后端
    // 生产模式（nini start）：前端静态文件直接由 FastAPI 提供，不使用代理
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
        // WebSocket 代理超时配置 - 2 分钟无数据传输才关闭
        timeout: 120000,
        // 允许代理长时间运行的 WebSocket 连接
        proxyTimeout: 120000,
      },
    },
  },
})
