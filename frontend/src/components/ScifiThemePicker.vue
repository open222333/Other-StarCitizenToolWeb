<!--
  玩家端配色選擇器。放在 MyPlayerView 頂端工具列，點齒輪展開。

  只改 CSS 變數，存在各自瀏覽器的 localStorage（見 stores/scifiTheme.js），
  不進伺服器 —— 配色是個人偏好，不需要同步給公會其他人。
-->
<template>
  <div class="sf-picker" ref="rootEl">
    <button
      class="btn btn-sm btn-scifi-outline"
      :aria-expanded="open"
      aria-label="配色設定"
      title="配色設定"
      @click="open = !open"
    >
      <i class="bi bi-palette"></i>
      <span class="d-none d-sm-inline ms-1">配色</span>
    </button>

    <div v-if="open" class="sf-panel scifi-card p-3">
      <!-- 強調色 -->
      <div class="sf-label">強調色</div>
      <div class="sf-swatches mb-3">
        <button
          v-for="a in theme.accents"
          :key="a.id"
          class="sf-swatch"
          :class="{ active: theme.accentId === a.id }"
          :style="{ background: `linear-gradient(135deg, ${a.accent} 60%, ${a.accent2} 60%)` }"
          :title="a.name"
          :aria-label="a.name"
          @click="theme.setAccent(a.id)"
        >
          <i v-if="theme.accentId === a.id" class="bi bi-check2 sf-check"></i>
        </button>

        <label
          class="sf-swatch sf-custom"
          :class="{ active: theme.isCustomAccent }"
          :style="theme.isCustomAccent ? { background: theme.currentAccent.accent } : {}"
          title="自訂顏色"
        >
          <i class="bi bi-eyedropper"></i>
          <input
            type="color"
            class="sf-color-input"
            :value="theme.isCustomAccent ? theme.currentAccent.accent : '#3ea6ff'"
            aria-label="自訂強調色"
            @input="e => theme.setCustomAccent(e.target.value)"
          />
        </label>
      </div>

      <!-- 底色（深色／亮色分組，因為兩者的文字色是整組翻轉的） -->
      <div class="sf-label">底色</div>
      <div class="sf-bg-list mb-3">
        <template v-for="group in bgGroups" :key="group.mode">
          <div class="sf-group">
            <i :class="group.icon"></i> {{ group.label }}
          </div>
          <button
            v-for="b in group.items"
            :key="b.id"
            class="sf-bg-item"
            :class="{ active: theme.bgId === b.id }"
            @click="theme.setBg(b.id)"
          >
            <span
              class="sf-bg-preview"
              :style="{ background: `linear-gradient(135deg, ${b.vars.bg1} 40%, ${b.vars.panel} 40%)` }"
            ></span>
            <span class="sf-bg-name">{{ b.name }}</span>
            <i v-if="theme.bgId === b.id" class="bi bi-check2 ms-auto"></i>
          </button>
        </template>
      </div>

      <!-- 密度 -->
      <div class="sf-label">資訊密度</div>
      <div class="btn-group btn-group-sm w-100 mb-3">
        <button
          class="btn"
          :class="theme.density === 'comfortable' ? 'btn-scifi' : 'btn-scifi-outline'"
          @click="theme.setDensity('comfortable')"
        >寬鬆</button>
        <button
          class="btn"
          :class="theme.density === 'compact' ? 'btn-scifi' : 'btn-scifi-outline'"
          @click="theme.setDensity('compact')"
        >緊湊</button>
      </div>

      <button class="btn btn-sm btn-link p-0" @click="theme.reset()">
        <i class="bi bi-arrow-counterclockwise me-1"></i>恢復預設
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useScifiThemeStore } from '@/stores/scifiTheme'

const theme = useScifiThemeStore()

// 深色與亮色分開列 —— 兩者不只是背景不同，文字／邊框／陰影是整組翻轉的，
// 混在一份清單裡使用者會以為只是換個顏色。
const bgGroups = computed(() => [
  {
    mode: 'dark',
    label: '深色',
    icon: 'bi bi-moon-stars',
    items: theme.backgrounds.filter(b => b.mode !== 'light'),
  },
  {
    mode: 'light',
    label: '亮色',
    icon: 'bi bi-brightness-high',
    items: theme.backgrounds.filter(b => b.mode === 'light'),
  },
].filter(g => g.items.length))
const open = ref(false)
const rootEl = ref(null)

// 點面板外面就收起來
function onDocClick(e) {
  if (open.value && rootEl.value && !rootEl.value.contains(e.target)) open.value = false
}
function onEsc(e) {
  if (e.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onEsc)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onEsc)
})
</script>

<style scoped>
.sf-picker { position: relative; }

.sf-panel {
  position: absolute;
  top: calc(100% + .5rem);
  right: 0;
  z-index: 1050;
  width: 260px;
}

.sf-label {
  font-size: .7rem;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--sf-text-dim);
  margin-bottom: .4rem;
}

/* ── 強調色色票 ── */
.sf-swatches { display: flex; flex-wrap: wrap; gap: .4rem; }

.sf-swatch {
  position: relative;
  width: 30px; height: 30px;
  border-radius: 6px;
  border: 1px solid var(--sf-border);
  cursor: pointer;
  padding: 0;
  display: flex; align-items: center; justify-content: center;
  transition: transform .1s, box-shadow .15s, border-color .15s;
}
.sf-swatch:hover { transform: translateY(-1px); border-color: var(--sf-border-hi); }
.sf-swatch.active {
  border-color: var(--sf-text);
  box-shadow: 0 0 0 2px rgba(var(--sf-accent-rgb), .45);
}
.sf-swatch:focus-visible {
  outline: 2px solid var(--sf-accent);
  outline-offset: 2px;
}

.sf-check {
  color: #fff;
  text-shadow: 0 0 4px rgba(0, 0, 0, .8);
  font-size: 1rem;
}

.sf-custom {
  background: conic-gradient(#f87171, #fbbf24, #34d399, #22d3ee, #3ea6ff, #a78bfa, #f87171);
  color: #fff;
  text-shadow: 0 0 3px rgba(0, 0, 0, .7);
}
.sf-color-input {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  opacity: 0; cursor: pointer;
}

/* ── 底色清單 ── */
.sf-bg-list { display: flex; flex-direction: column; gap: .25rem; }

.sf-bg-item {
  display: flex; align-items: center; gap: .5rem;
  padding: .35rem .5rem;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--sf-text);
  font-size: .85rem;
  cursor: pointer;
  text-align: left;
}
.sf-bg-item:hover { background: var(--sf-hover-bg); }
.sf-bg-item.active {
  border-color: var(--sf-accent);
  background: rgba(var(--sf-accent-rgb), .1);
}
.sf-bg-item:focus-visible {
  outline: 2px solid var(--sf-accent);
  outline-offset: 1px;
}

.sf-bg-preview {
  width: 26px; height: 18px;
  border-radius: 3px;
  border: 1px solid var(--sf-border);
  flex: 0 0 auto;
}
.sf-bg-name { white-space: nowrap; }

.sf-group {
  font-size: .68rem;
  letter-spacing: .06em;
  color: var(--sf-text-dim);
  margin: .35rem 0 .15rem;
  display: flex; align-items: center; gap: .3rem;
}
.sf-group:first-child { margin-top: 0; }
</style>
