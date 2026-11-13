<!--
  戰術小隊分配表的唯讀版面：工具箱 › 戰術小隊（不是建立者開啟時）和分享連結的公開頁（views/SquadSharedView.vue）共用。
  board 的格式見 utils/squadBoard.js；公開頁的資料只有名字、職位、是否註冊（src/models/squad.py 的 public_view）。
-->
<template>
  <div>
    <div :class="[cardClass, 'mb-3']">
      <div class="card-body py-3">
        <div class="d-flex flex-wrap align-items-baseline gap-2">
          <h2 class="sqv-title mb-0">{{ board.title }}</h2>
          <span v-if="board.event_at" class="sf-chip sf-chip--accent"><i class="bi bi-calendar-event me-1"></i>{{ fmtEventAt(board.event_at) }}</span>
          <span class="small text-muted ms-auto">{{ board.squads.length }} 個小隊 · {{ countShips(board) }} 艘船 · {{ countPeople(board) }} 人</span>
        </div>
        <p v-if="board.note" class="sqv-note mb-0 mt-2">{{ board.note }}</p>
        <div v-if="board.owner_name" class="small text-muted mt-2">建立者：{{ board.owner_name }}</div>
      </div>
    </div>

    <div v-if="!board.squads.length" class="text-muted text-center py-4">還沒有小隊。</div>
    <div class="row g-3">
      <div v-for="(s, si) in board.squads" :key="s.id" class="col-12 col-lg-6 col-xxl-4">
        <section :class="[cardClass, 'h-100']" :aria-label="s.name">
          <div class="card-body">
            <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
              <span class="sqv-no">{{ si + 1 }}</span>
              <h3 class="sqv-squad mb-0">{{ s.name }}</h3>
              <span class="small text-muted ms-auto">{{ s.ships.length }} 艘 · {{ squadPeople(s).length }} 人</span>
            </div>
            <div v-if="leaderName(s)" class="small mb-1"><i class="bi bi-star-fill sqv-star me-1" aria-hidden="true"></i>隊長：{{ leaderName(s) }}</div>
            <p v-if="s.note" class="sqv-note small mb-2">{{ s.note }}</p>

            <div v-for="v in s.ships" :key="v.id" class="sqv-ship">
              <div class="sqv-ship__head">
                <i class="bi bi-rocket-takeoff me-1" aria-hidden="true"></i>
                <span class="fw-semibold">{{ v.label || v.vehicle_name }}</span>
                <span v-if="v.label" class="small text-muted ms-1">{{ v.vehicle_name }}</span>
                <span class="sf-chip ms-auto" :class="{ 'sf-chip--warn': overCrew(v) }"
                  :title="v.crew_max ? `建議乘員 ${v.crew_max} 人` : ''">{{ v.crew.length }}{{ v.crew_max ? ` / ${v.crew_max}` : '' }} 人</span>
              </div>
              <ul class="sqv-people">
                <li v-for="p in v.crew" :key="p.id"><PersonLine :p="p" :leader="s.leader === p.id" :dup="isDup(p)" /></li>
                <li v-if="!v.crew.length" class="text-muted small">（尚未分配人員）</li>
              </ul>
            </div>

            <div v-if="s.members.length" class="sqv-ship sqv-ship--off">
              <div class="sqv-ship__head"><i class="bi bi-person-walking me-1" aria-hidden="true"></i><span class="fw-semibold">不在船上</span>
                <span class="sf-chip ms-auto">{{ s.members.length }} 人</span></div>
              <ul class="sqv-people">
                <li v-for="p in s.members" :key="p.id"><PersonLine :p="p" :leader="s.leader === p.id" :dup="isDup(p)" /></li>
              </ul>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, h } from 'vue'
import { countPeople, countShips, duplicateScids, fmtEventAt, squadPeople } from '@/utils/squadBoard'

const props = defineProps({
  board: { type: Object, required: true },
  cardClass: { type: String, default: 'card scifi-card' },
})

const dupes = computed(() => duplicateScids(props.board))
const isDup = p => !!p.scid && dupes.value.has(p.scid)
const overCrew = v => !!v.crew_max && v.crew.length > v.crew_max
const leaderName = s => squadPeople(s).find(p => p.id === s.leader)?.name || ''

// 人員一列：名字（隊長星號、未註冊、重複）＋職位
const PersonLine = (p) => h('span', { class: 'sqv-person' }, [
  p.leader ? h('i', { class: 'bi bi-star-fill sqv-star me-1', title: '隊長', 'aria-label': '隊長' }) : null,
  h('span', { class: 'fw-semibold' }, p.p.name),
  p.p.registered === false ? h('span', { class: 'sf-chip sf-chip--todo ms-1' }, '未註冊') : null,
  p.dup ? h('span', { class: 'sf-chip sf-chip--warn ms-1' }, '重複') : null,
  p.p.role ? h('span', { class: 'sqv-role ms-auto' }, p.p.role) : null,
])
PersonLine.props = ['p', 'leader', 'dup']
</script>

<style scoped>
.sqv-title { font-size: 1.35rem; font-weight: 700; color: var(--sf-text-strong, var(--sf-text)); }
.sqv-note { white-space: pre-wrap; color: var(--sf-text-muted); }
.sqv-no {
  display: inline-flex; align-items: center; justify-content: center; width: 1.6rem; height: 1.6rem;
  border-radius: 50%; background: var(--sf-accent-2); color: #0b1020; font-weight: 700; font-size: .9rem; flex: 0 0 auto;
}
.sqv-squad { font-size: 1.1rem; font-weight: 700; color: var(--sf-accent-text, var(--sf-accent)); }
.sqv-star { color: var(--sf-accent); }
.sqv-ship { border: 1px solid var(--sf-border-hi); border-radius: .5rem; padding: .5rem .65rem; margin-top: .5rem; background: var(--sf-chip-bg); }
.sqv-ship--off { border-style: dashed; }
.sqv-ship__head { display: flex; align-items: center; flex-wrap: wrap; gap: .25rem; }
.sqv-people { list-style: none; margin: .35rem 0 0; padding: 0; }
.sqv-people li { padding: .2rem 0; border-top: 1px solid var(--sf-border); }
.sqv-person { display: flex; align-items: center; flex-wrap: wrap; gap: .15rem; }
.sqv-role { color: var(--sf-text-muted); font-size: .9rem; }
</style>
