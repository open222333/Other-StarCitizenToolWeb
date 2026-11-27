// 前端 lint（docs/現版本優化方案.md 3-8）：只開「抓錯誤」的規則（eslint:recommended＋vue 的 essential），
// 不管排版風格；跑法 `npm run lint`，CI 也會跑。
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  { ignores: ['dist/**', 'dist-web/**', 'node_modules/**', 'public/**'] },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.{js,mjs,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      // 底線開頭的參數／變數是刻意不用的
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' }],
      'no-empty': ['error', { allowEmptyCatch: true }],
      // 單字元件名（News、Toast…）是既有命名，不是錯誤
      'vue/multi-word-component-names': 'off',
      // 全形空白是刻意的排版（字串、樣板字串裡），只抓程式碼本身的
      'no-irregular-whitespace': ['error', { skipStrings: true, skipTemplates: true, skipComments: true, skipRegExps: true }],
      // 「v-for="c in [card(g)]"」是在樣板裡取一次別名的寫法，key 用外層變數是刻意的；缺 key 仍由 require-v-for-key 抓
      'vue/valid-v-for': 'off',
    },
  },
]
