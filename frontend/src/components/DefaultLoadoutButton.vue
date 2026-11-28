<!--
  艦船資料列上的「預設配件」按鈕＋跳出視窗（資料庫 › 艦船、登記船艦資料）：
  有配裝資料（utils/loadoutShips.js，GET /item/loadout/ships）的船才出現按鈕；按了才抓這艘船的掛點樹
  （GET /item/loadout/ships/<id>，跟配裝模擬同一份），依區塊（駕駛武器、砲塔、飛彈、護盾、電源、冷卻、量子引擎…）
  列出出廠配件，同款的合併成「× 數量」，砲塔／飛彈架底下裝的東西縮排列在下面。
  視窗是共用的 SfModal（手機全螢幕）；區塊在寬螢幕排兩欄、窄螢幕一欄，每一列名稱可換行，不會撐破畫面。
  「在配裝模擬打開」切到工具箱 › 配裝模擬並選好這艘船。
-->
<template>
  <button v-if="available" type="button" class="btn btn-sm btn-info" :class="buttonClass"
    :aria-label="`${name} 的預設配件`" aria-haspopup="dialog" @click="show">
    <i class="bi bi-cpu me-1"></i>配件</button>
  <Teleport v-if="available" to="body">
    <div class="scifi-page dlb-host">
      <SfModal :id="uid" v-model:open="open" :title="`${name} 預設配件`" icon="bi bi-cpu" width="1100px">
        <template #head>
          <button type="button" class="btn btn-sm btn-primary" @click="openSimulator">
            <i class="bi bi-sliders me-1"></i>在配裝模擬打開</button>
        </template>
        <SfState :loading="loading" :error="error" :empty="!loading && !error && !sections.length" empty-text="這艘船沒有可以換的配件。"
          @retry="load">
          <div class="dlb-grid">
            <section v-for="s in sections" :key="s.key" class="dlb-sec">
              <h4 class="dlb-sec__h"><i :class="s.icon" class="me-1" aria-hidden="true"></i>{{ s.label }}
                <span class="dlb-sec__n">{{ s.count }}</span></h4>
              <ul class="dlb-list">
                <li v-for="(r, i) in s.rows" :key="i" class="dlb-row" :style="{ '--dlb-depth': r.depth }">
                  <span class="dlb-size">{{ r.size != null ? `S${r.size}` : '—' }}</span>
                  <span class="dlb-name">
                    <span class="fw-semibold">{{ r.label }}</span>
                    <span v-if="r.en" class="dlb-en">{{ r.en }}</span>
                    <span v-if="r.meta" class="dlb-meta">{{ r.meta }}</span>
                  </span>
                  <span v-if="r.count > 1" class="dlb-count">× {{ r.count }}</span>
                </li>
              </ul>
            </section>
          </div>
        </SfState>
      </SfModal>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import { getJson } from '@/utils/getJson'
import { SECTIONS, childGroups, groupNodes, sectionOf } from '@/utils/loadoutCalc'
import { classLabel, loadLoadoutZh, typeLabel } from '@/utils/loadoutLabels'
import { loadLoadoutShipIds, loadoutShipIds } from '@/utils/loadoutShips'
import { manufacturerShort } from '@/utils/vehicle'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 載具主檔 uuid（跟配裝資料的船 id 同一套） */
  vehicleUuid: { type: String, default: '' },
  name: { type: String, default: '' },
  buttonClass: { type: String, default: '' },
})

const router = useRouter()
const uid = `dlb-${Math.random().toString(36).slice(2, 8)}`
const open = ref(false)
const loading = ref(false)
const error = ref('')
const ship = ref(null)
const available = computed(() => !!props.vehicleUuid && loadoutShipIds.value.has(props.vehicleUuid))
onMounted(() => loadLoadoutShipIds(props.fetcher))

async function load() {
  loading.value = true
  error.value = ''
  const { ok, data, message } = await getJson(props.fetcher, `/item/loadout/ships/${encodeURIComponent(props.vehicleUuid)}`,
    undefined, '讀取配件資料失敗')
  loading.value = false
  if (!ok) { error.value = message; return }
  ship.value = data
  loadLoadoutZh(Object.values(data?.items || {}), [])
}
function show() {
  open.value = true
  if (!ship.value && !loading.value) load()
}
function openSimulator() {
  open.value = false
  router.push({ query: { tab: 'toolbox', sub: 'loadout', ship: props.vehicleUuid } })
}

const itemOf = id => (id && ship.value?.items?.[id]) || null

/** 一組同款槽位 → 一列（同款合併成 × 數量），子槽縮排列在下面 */
function rowsOf(group, depth, out) {
  const first = group[0]
  const it = itemOf(first.item)
  const zh = it?.name_zh && it.name_zh !== it.name ? it.name_zh : ''
  out.push({
    depth,
    count: group.length,
    size: it?.size ?? first.max ?? null,
    label: it ? (zh || it.name) : (first.name || first.item_class_name || '（空）'),
    en: zh ? it.name : '',
    meta: it ? [typeLabel([`${it.type}.${it.sub_type}`]), it.grade, it.item_class ? classLabel(it.item_class) : '',
      manufacturerShort(it.manufacturer_name, it.manufacturer)].filter(x => x && x !== '—').join(' · ') : '',
  })
  for (const g of childGroups(group, itemOf)) if (g.length) rowsOf(g, depth + 1, out)
}

const sections = computed(() => {
  const slots = ship.value?.slots || []
  return SECTIONS.map((s) => {
    const nodes = slots.filter(n => sectionOf(n, itemOf) === s.key && (n.item || n.children?.length))
    const rows = []
    for (const g of groupNodes(nodes, itemOf)) rowsOf(g, 0, rows)
    return { ...s, rows, count: nodes.length }
  }).filter(s => s.rows.length)
})
</script>

<style scoped>
/* Teleport 到 body 的外框只為了吃 .scifi-page 主題，本身不佔版面（.scifi-page 有 min-height: 100vh） */
.dlb-host { display: contents; }
/* 區塊：寬螢幕兩欄、窄螢幕一欄 */
.dlb-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: .75rem; }
@media (min-width: 992px) { .dlb-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; } }
.dlb-sec { border: 1px solid var(--sf-border); border-radius: .6rem; padding: .6rem .75rem; background: var(--sf-inset); min-width: 0; }
.dlb-sec__h { display: flex; align-items: center; gap: .25rem; margin: 0 0 .45rem; font-size: var(--sf-fs-sm); font-weight: 800; color: var(--sf-text-strong); }
.dlb-sec__n { margin-left: auto; font-size: var(--sf-fs-xs); font-weight: 700; color: var(--sf-text-muted); }
.dlb-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .3rem; }
.dlb-row {
  display: flex; align-items: flex-start; gap: .5rem; min-width: 0;
  padding-left: calc(var(--dlb-depth, 0) * 1.1rem);
}
.dlb-row + .dlb-row { border-top: 1px dashed var(--sf-border); padding-top: .3rem; }
.dlb-size {
  flex: none; min-width: 2.2rem; text-align: center; font-size: var(--sf-fs-xs); font-weight: 800;
  border: 1px solid rgba(var(--sf-accent-rgb), .5); border-radius: .35rem; padding: .05rem .3rem; color: var(--sf-text-strong);
}
.dlb-name { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; overflow-wrap: anywhere; }
.dlb-en, .dlb-meta { font-size: var(--sf-fs-xs); color: var(--sf-text-muted); }
.dlb-count { flex: none; font-weight: 800; color: var(--sf-accent-2-text, var(--sf-accent-2)); white-space: nowrap; }
</style>
