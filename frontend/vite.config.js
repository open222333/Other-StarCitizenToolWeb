import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { makeProxy } from './vite.api-prefixes.mjs'

export default defineConfig({
  plugins: [vue()],

  // 讓打包後的所有資源路徑都以 /admin/ 為基底
  base: '/admin/',

  // 這個 build 是「管理後台」；玩家/藍圖/戰利品那個站是「星際公民工具」，
  // 見 vite.config.web.js 的 VITE_APP_TITLE
  define: {
    'import.meta.env.VITE_APP_TITLE': JSON.stringify('管理後台'),
  },

  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },

  build: {
    // ⚠️ 輸出到專案根目錄的 web-admin/，**刻意不放在 app/ 裡面**。
    //
    // 原本是 '../app/static/admin'，但 docker-compose.api.yml 為了讓 Python
    // 程式碼即時生效而掛了 `./app:/app/app` —— 那個 bind mount 會把
    // Dockerfile 在容器裡建好的前端整個遮住，結果 `docker compose build api`
    // 永遠不會更新後台畫面，必須另外手動建置到 host。
    //
    // 移到 app/ 外面之後，web-admin/ 不被任何 mount 覆蓋，容器裡建好的版本
    // 就是實際被服務的版本，「重新 build image」成為唯一的前端建置方式。
    // 對應 app/admin/view.py 的 _dist_dir() 與 docker/Dockerfile 的 COPY。
    outDir:      '../web-admin',
    emptyOutDir: true,
  },

  server: {
    port: 5173,
    // 開發時將 API 請求代理到 Flask（port 5000）。
    // 清單集中在 vite.api-prefixes.mjs，避免兩份 config 漂移。
    proxy: makeProxy(),
  },
})
