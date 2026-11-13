<!--
  後台「系統設定」：分成幾個分頁（記在網址 ?tab=），全站設定跟「只存在這台瀏覽器」的外觀分開。
    玩家頁（components/PlayerTabOrderCard.vue）、物品分組（ItemTypeGroupsCard.vue）、
    AI 問答（AiSettingsCard.vue，admin）、備份（BackupCard.vue，admin）、外觀（這個檔案，存在瀏覽器，見 stores/theme.js）。
  各卡片用 components/SettingsSaveBar.vue 的儲存列；有未儲存的變更時分頁標籤上有圓點，離開頁面前會先問。
  卡片用 v-show 切換（不是 v-if），切分頁時沒存的修改還在。
-->
<template>
  <div>
    <h4 class="fw-bold mb-3"><i class="bi bi-gear me-2"></i>系統設定</h4>

    <ul class="nav nav-tabs mb-3" role="tablist">
      <li v-for="t in tabs" :key="t.key" class="nav-item" role="presentation">
        <button :id="`settings-tab-${t.key}`" type="button" class="nav-link" role="tab"
          :class="{ active: tab === t.key }" :aria-selected="tab === t.key" :aria-controls="`settings-panel-${t.key}`"
          @click="setTab(t.key)">
          <i :class="t.icon" class="me-1" aria-hidden="true"></i>{{ t.label }}
          <span v-if="dirty[t.key]" class="settings-dirty" title="有未儲存的變更" aria-label="有未儲存的變更"></span>
        </button>
      </li>
    </ul>

    <p class="settings-scope small mb-3">
      <span v-if="currentTab.local" class="badge text-bg-light border"><i class="bi bi-laptop me-1"></i>只存在這台瀏覽器</span>
      <span v-else class="badge text-bg-primary"><i class="bi bi-globe2 me-1"></i>全站設定</span>
      <span class="text-body-secondary ms-2">{{ currentTab.scope }}</span>
    </p>

    <div v-show="tab === 'player'" id="settings-panel-player" role="tabpanel" aria-labelledby="settings-tab-player">
      <PlayerTabOrderCard @dirty="v => dirty.player = v" />
    </div>
    <div v-show="tab === 'items'" id="settings-panel-items" role="tabpanel" aria-labelledby="settings-tab-items">
      <ItemTypeGroupsCard @dirty="v => dirty.items = v" />
    </div>
    <div v-if="auth.isAdmin" v-show="tab === 'ai'" id="settings-panel-ai" role="tabpanel" aria-labelledby="settings-tab-ai">
      <AiSettingsCard @dirty="v => dirty.ai = v" />
    </div>
    <div v-if="auth.isAdmin" v-show="tab === 'backup'" id="settings-panel-backup" role="tabpanel" aria-labelledby="settings-tab-backup">
      <BackupCard />
    </div>

    <!-- 外觀：模式、背景、主題色合成一張卡（都存在這台瀏覽器，點了就生效，不用儲存） -->
    <div v-show="tab === 'appearance'" id="settings-panel-appearance" role="tabpanel" aria-labelledby="settings-tab-appearance">
      <div class="card border-0 shadow-sm mb-3">
        <div class="card-body p-4">
          <section class="look-section">
            <h6 class="fw-semibold mb-1">外觀模式</h6>
            <p class="text-body-secondary small mb-3">深色、淺色，或自動跟隨系統設定。</p>
            <div class="mode-row" role="radiogroup" aria-label="外觀模式">
              <button
                v-for="m in theme.modes"
                :key="m.id"
                type="button"
                class="mode-btn"
                role="radio"
                :aria-checked="theme.mode === m.id"
                :class="{ active: theme.mode === m.id }"
                @click="theme.setMode(m.id)"
              >
                <i :class="['bi', m.icon, 'mode-icon']" aria-hidden="true"></i>
                <span>{{ m.name }}</span>
              </button>
            </div>
          </section>

          <section class="look-section">
            <h6 class="fw-semibold mb-1">主題色彩</h6>
            <p class="text-body-secondary small mb-3">側邊欄高亮與強調色，深色和淺色模式都適用。</p>
            <div class="accent-grid" role="radiogroup" aria-label="主題色彩">
              <button
                v-for="a in theme.accents"
                :key="a.id"
                type="button"
                class="accent-card"
                role="radio"
                :aria-checked="theme.accentId === a.id && !theme.isCustom"
                :class="{ active: theme.accentId === a.id && !theme.isCustom }"
                @click="theme.setAccent(a.id)"
              >
                <div class="accent-preview">
                  <div class="ap-half" :style="{ background: a.dark.sbBg }">
                    <div class="ap-dot" :style="{ background: a.accent }"></div>
                    <div class="ap-dot dim"></div>
                  </div>
                  <div class="ap-half ap-light">
                    <div class="ap-dot" :style="{ background: a.accent }"></div>
                    <div class="ap-dot dim light"></div>
                  </div>
                </div>
                <div class="accent-label">
                  {{ a.name }}
                  <i v-if="theme.accentId === a.id && !theme.isCustom"
                     class="bi bi-check-circle-fill text-success ms-1" aria-hidden="true"></i>
                </div>
              </button>

              <!-- 自訂色票 -->
              <label class="accent-card" :class="{ active: theme.isCustom }" title="自訂色彩">
                <div class="accent-preview custom-preview">
                  <div class="ap-half" :style="{ background: '#1e2130' }">
                    <div class="ap-dot" :style="{ background: theme.customColor }"></div>
                    <div class="ap-dot dim"></div>
                  </div>
                  <div class="ap-half ap-light">
                    <div class="ap-dot" :style="{ background: theme.customColor }"></div>
                    <div class="ap-dot dim light"></div>
                  </div>
                  <input
                    type="color"
                    class="color-input"
                    aria-label="自訂主題色彩"
                    :value="theme.customColor"
                    @input="e => theme.setCustomColor(e.target.value)"
                  />
                </div>
                <div class="accent-label">
                  自訂
                  <i v-if="theme.isCustom" class="bi bi-check-circle-fill text-success ms-1" aria-hidden="true"></i>
                </div>
              </label>
            </div>
          </section>

          <section class="look-section">
            <h6 class="fw-semibold mb-1">頁面背景顏色</h6>
            <p class="text-body-secondary small mb-3">內容區的背景色，可以選色票或自訂；「預設」跟著外觀模式。</p>
            <div class="bg-swatches" role="radiogroup" aria-label="頁面背景顏色">
              <button
                type="button"
                class="bg-swatch reset-swatch"
                role="radio"
                :aria-checked="!theme.isCustomBg"
                :class="{ active: !theme.isCustomBg }"
                title="跟隨主題預設"
                @click="theme.resetContentBg()"
              >
                <i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i>
                <span>預設</span>
              </button>
              <button
                v-for="sw in BG_SWATCHES"
                :key="sw.hex"
                type="button"
                class="bg-swatch"
                role="radio"
                :aria-checked="theme.isCustomBg && theme.contentBg === sw.hex"
                :aria-label="sw.name"
                :class="{ active: theme.isCustomBg && theme.contentBg === sw.hex }"
                :style="{ background: sw.hex }"
                :title="sw.name"
                @click="theme.setContentBg(sw.hex)"
              >
                <i v-if="theme.isCustomBg && theme.contentBg === sw.hex" class="bi bi-check2 check-icon" aria-hidden="true"></i>
              </button>
              <label
                class="bg-swatch custom-swatch"
                :class="{ active: customBgActive }"
                title="自訂顏色"
                :style="customBgActive ? { background: theme.contentBg } : {}"
              >
                <i class="bi bi-eyedropper" aria-hidden="true"></i>
                <span>自訂</span>
                <input type="color"
                  class="color-input"
                  aria-label="自訂背景顏色"
                  :value="theme.contentBg || '#f5f6fa'"
                  @input="e => theme.setContentBg(e.target.value)"
                />
              </label>
            </div>
          </section>
        </div>
      </div>
    </div>

    <ConfirmModal ref="confirmRef" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import ConfirmModal from '@/components/ConfirmModal.vue'
import { useThemeStore } from '@/stores/theme'
import PlayerTabOrderCard from '@/components/PlayerTabOrderCard.vue'
import ItemTypeGroupsCard from '@/components/ItemTypeGroupsCard.vue'
import BackupCard from '@/components/BackupCard.vue'
import AiSettingsCard from '@/components/AiSettingsCard.vue'
import { useAuthStore } from '@/stores/auth'

const theme = useThemeStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const confirmRef = ref(null)

// ── 分頁（記在網址 ?tab=，重新整理或貼連結都停在同一頁）──
const ALL_TABS = [
  { key: 'player', label: '玩家頁', icon: 'bi bi-window-sidebar', scope: '玩家頁分頁的順序與開放狀態，所有玩家生效。' },
  { key: 'items', label: '物品分組', icon: 'bi bi-collection', scope: '物品類型篩選的分組，後台與玩家頁都生效。' },
  { key: 'ai', label: 'AI 問答', icon: 'bi bi-robot', admin: true, scope: 'Discord /ask 的開關、供應商與限流。' },
  { key: 'backup', label: '備份', icon: 'bi bi-database-down', admin: true, scope: '匯出或還原帳號、會員與設定資料。' },
  { key: 'appearance', label: '外觀', icon: 'bi bi-palette', local: true, scope: '後台的配色，點了就生效，不用儲存；換電腦或瀏覽器要重新設定。' },
]
const tabs = computed(() => ALL_TABS.filter(t => !t.admin || auth.isAdmin))
const tab = ref(tabs.value.some(t => t.key === route.query.tab) ? String(route.query.tab) : 'player')
const currentTab = computed(() => tabs.value.find(t => t.key === tab.value) || tabs.value[0])
function setTab(key) {
  tab.value = key
  router.replace({ query: { ...route.query, tab: key } })
}

// ── 未儲存的變更：分頁標籤上的圓點，離開頁面前先問 ──
const dirty = reactive({ player: false, items: false, ai: false })
const anyDirty = computed(() => Object.values(dirty).some(Boolean))
onBeforeRouteLeave(async () => {
  if (!anyDirty.value) return true
  return confirmRef.value.confirm('有設定還沒儲存，離開後會不見。確定要離開？', { title: '尚未儲存', okText: '離開' })
})
function beforeUnload(e) {
  if (!anyDirty.value) return
  e.preventDefault()
  e.returnValue = ''
}
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))

const customBgActive = computed(() => theme.isCustomBg && !BG_SWATCHES.some(sw => sw.hex === theme.contentBg))

const BG_SWATCHES = [
  { hex: '#f5f6fa', name: '藍白（深色預設）' },
  { hex: '#eef0f5', name: '淺藍白（淺色預設）' },
  { hex: '#ffffff', name: '純白' },
  { hex: '#fafafa', name: '暖白' },
  { hex: '#f0f4f8', name: '冷藍灰' },
  { hex: '#f5f0eb', name: '暖米' },
  { hex: '#1e1e2e', name: '深藍黑' },
  { hex: '#1e1e1e', name: '深灰' },
]
</script>

<style scoped>
/* ── 分頁、範圍說明 ── */
.settings-dirty {
  display: inline-block; width: .5rem; height: .5rem; margin-left: .35rem; vertical-align: middle;
  border-radius: 50%; background: var(--bs-warning);
}
.settings-scope { display: flex; flex-wrap: wrap; align-items: center; }

/* ── 外觀卡片：三段用分隔線隔開 ── */
.look-section + .look-section { margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid var(--bs-border-color); }

/* ── Mode ── */
.mode-row { display: flex; gap: .75rem; flex-wrap: wrap; }

.mode-btn {
  display: flex; flex-direction: column; align-items: center;
  gap: .35rem; padding: .85rem 1.5rem;
  border: 2px solid var(--bs-border-color); border-radius: .75rem;
  background: none; cursor: pointer; min-width: 90px;
  transition: border-color .15s, box-shadow .15s;
}
.mode-btn:hover  { border-color: var(--bs-secondary-color); }
.mode-btn.active { border-color: var(--sb-active-color, #6384ff); box-shadow: 0 0 0 3px color-mix(in srgb, var(--sb-active-color, #6384ff) 22%, transparent); }
.mode-icon       { font-size: 1.5rem; color: var(--bs-secondary-color); }
.mode-btn.active .mode-icon { color: var(--sb-active-color, #6384ff); }
.mode-btn span   { font-size: .85rem; color: var(--bs-body-color); }

/* ── Accent ── */
.accent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
  gap: 1rem;
}
.accent-card {
  background: none;
  border: 2px solid var(--bs-border-color); border-radius: .75rem;
  padding: .5rem; cursor: pointer;
  transition: border-color .15s, transform .12s, box-shadow .15s;
  text-align: center;
}
.accent-card:hover  { transform: translateY(-2px); border-color: var(--bs-secondary-color); }
.accent-card.active { border-color: var(--sb-active-color, #6384ff); box-shadow: 0 0 0 3px color-mix(in srgb, var(--sb-active-color, #6384ff) 22%, transparent); }

.accent-preview {
  width: 100%; aspect-ratio: 3 / 2;
  border-radius: .4rem; overflow: hidden;
  display: flex; border: 1px solid rgba(0,0,0,.08);
  position: relative;
}
.ap-half {
  flex: 1; display: flex; flex-direction: column;
  gap: 3px; padding: 5px 4px;
}
.ap-light { background: #f8f9fa; }
.ap-dot   { height: 4px; border-radius: 2px; }
.ap-dot.dim       { background: rgba(255,255,255,.25); }
.ap-dot.dim.light { background: rgba(0,0,0,.15); }

.custom-preview { cursor: pointer; }
.color-input {
  position: absolute; inset: 0;
  opacity: 0; width: 100%; height: 100%;
  cursor: pointer;
}

.accent-label {
  margin-top: .4rem; font-size: .8rem; color: var(--bs-body-color);
}

/* ── Background swatches ── */
.bg-swatches {
  display: flex; flex-wrap: wrap; gap: .6rem; align-items: center;
}

.bg-swatch {
  width: 48px; height: 48px;
  border-radius: .5rem;
  border: 2px solid var(--bs-border-color);
  cursor: pointer;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  transition: border-color .15s, transform .1s, box-shadow .15s;
  font-size: .65rem; color: var(--bs-secondary-color); gap: 2px;
  position: relative; overflow: hidden;
}
.bg-swatch:hover  { transform: translateY(-2px); border-color: var(--bs-secondary-color); }
.bg-swatch:focus-visible, .mode-btn:focus-visible, .accent-card:focus-visible, .accent-card:focus-within {
  outline: 2px solid var(--sb-active-color, #6384ff); outline-offset: 2px;
}
.bg-swatch.active { border-color: var(--sb-active-color, #6384ff); box-shadow: 0 0 0 3px color-mix(in srgb, var(--sb-active-color, #6384ff) 22%, transparent); }

.reset-swatch  { background: linear-gradient(135deg, #f5f6fa 50%, #eef0f5 50%); }
.custom-swatch { background: conic-gradient(red, yellow, lime, cyan, blue, magenta, red); }
.custom-swatch.active { background: v-bind("theme.contentBg"); }
.custom-swatch .bi-eyedropper, .custom-swatch span { text-shadow: 0 0 3px rgba(255,255,255,.8); }

.check-icon {
  position: absolute; font-size: 1.1rem;
  color: #fff; text-shadow: 0 0 4px rgba(0,0,0,.5);
}
.color-input {
  position: absolute; inset: 0; opacity: 0;
  width: 100%; height: 100%; cursor: pointer;
}

</style>
