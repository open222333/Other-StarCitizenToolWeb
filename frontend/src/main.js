import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useScifiThemeStore } from './stores/scifiTheme'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'
import 'bootstrap/dist/js/bootstrap.bundle.min.js'
// 玩家端公開頁面（登入／註冊／個人頁）用的深色科幻主題，見檔案內註解
import './assets/scifi-theme.css'

// 兩套 build 站名不同：管理後台 / 星際公民工具，見 vite.config.js / vite.config.web.js
document.title = import.meta.env.VITE_APP_TITLE || '管理後台'

const pinia = createPinia()

createApp(App)
  .use(pinia)
  .use(router)
  .mount('#app')

// 玩家自己存的配色要在第一次繪製時就套上，否則登入／註冊頁會先閃一下
// 預設色再跳成使用者選的色。
// （只有公開站需要 —— 後台有自己的 stores/theme.js。）
if (import.meta.env.VITE_APP_TITLE !== '管理後台') {
  useScifiThemeStore(pinia).apply()
}
