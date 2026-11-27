<!--
  一筆維克洛交易（資料庫 › 維克洛 WikeloDatabase、物品／藍圖／艦船的「維克洛」視窗 WikeloButton 共用）：
  標題、獎勵、要交的物品與數量、維克洛聲望、前置任務。物品中文名稱是後端對主檔補的（name_zh），沒有就英文。
  highlight＝要標出來的物品 uuid（視窗裡標「就是這個物品」）。
-->
<template>
  <article class="card scifi-card wk-card h-100">
    <div class="card-body">
      <h3 class="wk-title">
        {{ trade.title_zh || trade.title }}
        <span v-if="trade.title_zh" class="sf-name__en">{{ trade.title }}</span>
      </h3>
      <div class="wk-tags">
        <span v-if="trade.reputation_amount" class="sf-chip sf-chip--accent">維克洛聲望 +{{ fmtInt(trade.reputation_amount) }}</span>
        <span v-if="trade.once_only" class="sf-chip">只能換一次</span>
      </div>

      <div class="wk-label">獎勵</div>
      <ul class="wk-list wk-list--reward">
        <li v-for="(r, i) in trade.rewards" :key="r.item_uuid || i" :class="{ 'wk-hit': isHit(r) }">
          <span class="wk-name">{{ r.name_zh || r.name }}<span v-if="r.name_zh" class="sf-name__en">{{ r.name }}</span></span>
          <span v-if="r.amount && r.amount !== 1" class="wk-amount">× {{ r.amount }}</span>
        </li>
        <li v-if="!trade.rewards?.length" class="text-muted">—</li>
      </ul>

      <div class="wk-label">需要</div>
      <ul class="wk-list">
        <li v-for="(r, i) in trade.requirements" :key="r.item_uuid || i" :class="{ 'wk-hit': isHit(r) }">
          <span class="wk-name">{{ r.name_zh || r.name }}<span v-if="r.name_zh" class="sf-name__en">{{ r.name }}</span></span>
          <span class="wk-amount">{{ wikeloAmount(r) }}</span>
        </li>
        <li v-if="!trade.requirements?.length" class="text-muted">—</li>
      </ul>

      <template v-if="preMissions.length || preTags.length">
        <div class="wk-label">前置條件</div>
        <div class="wk-pre">
          <span v-for="m in preMissions" :key="m.uuid" class="sf-chip">{{ m.title }}</span>
          <span v-for="t in preTags" :key="t" class="sf-chip">{{ t }}</span>
        </div>
      </template>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { wikeloAmount } from '@/utils/wikelo'

const props = defineProps({
  trade: { type: Object, required: true },
  highlight: { type: Array, default: () => [] },
})
const fmtInt = n => Number(n).toLocaleString('zh-TW')
const isHit = r => !!r.item_uuid && props.highlight.includes(r.item_uuid)
const preMissions = computed(() => (props.trade.prerequisite_groups || []).flatMap(g => g.missions || []))
const preTags = computed(() => [...new Set((props.trade.prerequisite_groups || []).flatMap(g => g.required_tags || []))])
</script>

<style scoped>
.wk-title { font-size: var(--sf-fs-md); font-weight: 700; margin: 0 0 .35rem; }
.wk-title .sf-name__en { display: block; font-size: var(--sf-fs-sm); font-weight: 400; }
.wk-tags { display: flex; flex-wrap: wrap; gap: .3rem; margin-bottom: .25rem; }
.wk-label { margin: .6rem 0 .25rem; color: var(--sf-text-muted); font-size: var(--sf-fs-sm); font-weight: 700; }
.wk-list { list-style: none; margin: 0; padding: 0; }
.wk-list li {
  display: flex; align-items: baseline; justify-content: space-between; gap: .75rem;
  padding: .3rem .5rem; border-bottom: 1px solid rgba(var(--sf-accent-rgb), .12);
}
.wk-list li:last-child { border-bottom: 0; }
.wk-list--reward li { font-weight: 700; color: var(--sf-text-strong); }
.wk-name .sf-name__en { display: block; font-size: var(--sf-fs-xs); font-weight: 400; }
.wk-amount { flex: none; font-weight: 700; color: var(--sf-accent-2-text, var(--sf-accent-2)); white-space: nowrap; }
.wk-hit { background: rgba(var(--sf-accent-rgb), .18); border-radius: .35rem; }
.wk-pre { display: flex; flex-wrap: wrap; gap: .3rem; }
</style>
