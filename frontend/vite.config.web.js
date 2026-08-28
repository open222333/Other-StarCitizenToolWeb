import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { makeProxy } from './vite.api-prefixes.mjs'

// 「web」是給一般玩家用的主站（玩家／藍圖／戰利品），跟 vite.config.js（後台管理，
// 掛在 /admin/）共用同一份 src/，差別只在 base path 跟輸出目錄。
// 對應 docker-compose.web.yml 的 web 容器（nginx 直接吃這個 build 輸出）。
//
// ⚠️ 目前 router 裡的 users/logs/settings（後台限定頁面）也會一起打包進這個 build，
// 因為兩邊共用同一個 router.js。之後若要把「公開頁面」與「後台頁面」完全切開，
// 需要把 router 拆成兩份，這裡先不做（見規格書第 17.1 節的待確認事項）。
export default defineConfig({
  plugins: [vue()],

  base: '/',

  // 讓 router/index.js 讀到 import.meta.env.VITE_ROUTER_BASE 後改用 '/' 而不是 '/admin/'；
  // VITE_APP_TITLE 用來跟 vite.config.js（管理後台）區分站名，見 DashboardLayout.vue
  define: {
    'import.meta.env.VITE_ROUTER_BASE': JSON.stringify('/'),
    'import.meta.env.VITE_APP_TITLE':   JSON.stringify('星際公民工具'),
  },

  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },

  build: {
    // 純靜態輸出，交給 docker-compose.web.yml 裡的 nginx 容器服務，不進 Flask static
    outDir:      'dist-web',
    emptyOutDir: true,
  },

  server: {
    port: 5174,
    // 清單集中在 vite.api-prefixes.mjs，避免跟 vite.config.js 漂移
    proxy: makeProxy(),
  },
})
