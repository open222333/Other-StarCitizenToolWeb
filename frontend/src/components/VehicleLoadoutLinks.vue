<!--
  配件網址（玩家在「我的艦隊」自己的船上填，erkul.games 的分享代碼或完整網址，見
  src/models/fleet.py 的 clean_loadout_links）。玩家頁的艦隊、船艦搜尋的持有者、
  後台「玩家擁有艦船」共用。滑過連結看加入日期（外部計算器的配置是當時版本的）。
-->
<template>
  <div v-if="links?.length" class="small loadout-links d-flex flex-wrap align-items-center gap-1 mt-1">
    <span><i class="bi bi-wrench-adjustable me-1" aria-hidden="true"></i>配件網址：</span>
    <a v-for="(link, i) in links" :key="link.url" :href="link.url" target="_blank" rel="noopener noreferrer"
      class="btn btn-sm btn-primary py-0 px-2"
      :title="`${link.url}${link.added_at ? `（${fmtDate(link.added_at)} 加入）` : ''}`">
      <i class="bi bi-box-arrow-up-right me-1" aria-hidden="true"></i>{{ linkLabel(link, i) }}
    </a>
  </div>
</template>

<script setup>
defineProps({ links: { type: Array, default: () => [] } })

function linkLabel(link, i) {
  if (link.label) return link.label
  try {
    const url = new URL(link.url)
    // erkul 分享連結直接顯示代碼（https://erkul.games/s/abcd1234 → abcd1234）
    const share = url.hostname.replace(/^www\./, '') === 'erkul.games' && url.pathname.match(/^\/s\/([^/]+)/)
    if (share) return share[1]
    return url.hostname.replace(/^www\./, '')
  } catch {
    return `配置 ${i + 1}`
  }
}

function fmtDate(value) {
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('zh-TW')
}
</script>

<style scoped>
.loadout-links a { word-break: break-all; }
</style>
