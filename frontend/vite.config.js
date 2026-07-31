import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],

  // 讓打包後的所有資源路徑都以 /admin/ 為基底
  base: '/admin/',

  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },

  build: {
    // 打包輸出到 Flask static 目錄，Flask 直接服務
    outDir:     '../app/static/admin',
    emptyOutDir: true,
  },

  server: {
    port: 5173,
    // 開發時將 API 請求代理到 Flask（port 5000）
    proxy: {
      '/auth':   { target: 'http://localhost:5000', changeOrigin: true },
      '/user':   { target: 'http://localhost:5000', changeOrigin: true },
      '/log':    { target: 'http://localhost:5000', changeOrigin: true },
      '/device': { target: 'http://localhost:5000', changeOrigin: true },
      '/sample': { target: 'http://localhost:5000', changeOrigin: true },
    },
  },
})
