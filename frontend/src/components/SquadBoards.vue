<!--
  玩家頁「工具箱 › 戰術小隊」：戰術小隊分配表（小隊 → 艦船 → 人員）。計劃見 docs/戰術小隊分配表實作計劃.md。

  - 列表：全部登入玩家的表都看得到；自己的可以刪除，任何表都可以複製一份變成自己的。
  - 開啟：建立者是編輯畫面（存檔才寫進資料庫，rev 不同回 409），其他人是唯讀（components/SquadBoardView.vue）。
  - 人員：打字出現玩家候選，選了就綁定那個玩家；選最後一項「加為未註冊人員」就只記名字。
  - 分享連結：開了之後 /player/squad/<分享碼> 不用登入就能看（views/SquadSharedView.vue）。
  - 開啟中的表記在網址 ?board=<id>（貼給隊友會直接打開那張）。
  API：/player/squads*（app/player/squad_view.py）。
-->
<template>
  <div>
    <!-- ══════════ 列表 ══════════ -->
    <template v-if="!board">
      <div class="sf-toolbar">
        <button type="button" class="btn btn-sm btn-success" :disabled="creating" @click="createBoard()">
          <i class="bi bi-plus-lg me-1"></i>新增分配表</button>
        <div class="form-check form-switch mb-0 ms-2">
          <input id="sqb-mine" v-model="mineOnly" class="form-check-input" type="checkbox">
          <label class="form-check-label small" for="sqb-mine">只看我建立的</label>
        </div>
        <input v-model="listQuery" type="search" class="form-control form-control-sm sqb-search ms-auto"
          placeholder="搜尋名稱、建立者" aria-label="搜尋分配表">
        <button type="button" class="btn btn-sm btn-outline-secondary" :disabled="listLoading" aria-label="重新整理"
          @click="loadList"><i class="bi bi-arrow-clockwise"></i></button>
      </div>
      <SfState :loading="listLoading && !boards.length" :error="listError" :empty="listLoaded && !shownBoards.length"
        :empty-text="boards.length ? '沒有符合條件的分配表。' : '還沒有分配表，按「新增分配表」建立第一張。'" @retry="loadList">
        <div :class="cardClass">
          <div class="card-body p-0">
            <div style="overflow-x: auto">
              <table class="table table-hover align-middle mb-0 sf-stack">
                <thead class="table-light">
                  <tr>
                    <th class="ps-3">名稱</th>
                    <th>行動時間</th>
                    <th class="text-end">小隊</th>
                    <th class="text-end">艦船</th>
                    <th class="text-end">人數</th>
                    <th>建立者</th>
                    <th>更新時間</th>
                    <th class="pe-3"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="b in shownBoards" :key="b.id">
                    <td class="ps-3 sf-stack__title">
                      <a href="#" class="fw-semibold" @click.prevent="openBoard(b.id)">{{ b.title }}</a>
                      <i v-if="b.shared" class="bi bi-link-45deg ms-1 text-muted" title="已開啟分享連結" aria-label="已開啟分享連結"></i>
                    </td>
                    <td data-label="行動時間" class="text-nowrap">{{ fmtEventAt(b.event_at) || '—' }}</td>
                    <td data-label="小隊" class="text-end">{{ b.squad_count }}</td>
                    <td data-label="艦船" class="text-end">{{ b.ship_count }}</td>
                    <td data-label="人數" class="text-end">{{ b.people_count }}</td>
                    <td data-label="建立者">{{ b.owner_name }}<span v-if="b.owner_scid === me" class="sf-chip sf-chip--accent ms-1">我</span></td>
                    <td data-label="更新時間" class="text-nowrap small">{{ fmtTs(b.updated_at) }}</td>
                    <td class="pe-3 text-end text-nowrap sf-stack__actions">
                      <button type="button" class="btn btn-sm btn-primary me-1" @click="openBoard(b.id)">開啟</button>
                      <button type="button" class="btn btn-sm btn-outline-secondary me-1" :disabled="creating"
                        @click="createBoard(b.id)">複製</button>
                      <button v-if="b.owner_scid === me" type="button" class="btn btn-sm btn-danger"
                        :aria-label="`刪除${b.title}`" @click="deleteBoard(b)"><i class="bi bi-trash"></i></button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </SfState>
    </template>

    <!-- ══════════ 開啟一張表 ══════════ -->
    <template v-else>
      <div class="sf-toolbar sqb-sticky">
        <button type="button" class="btn btn-sm btn-outline-secondary" @click="closeBoard"><i class="bi bi-arrow-left me-1"></i>列表</button>
        <template v-if="board.can_edit">
          <button type="button" class="btn btn-sm btn-success" :disabled="!dirty || saving" @click="save">
            <i class="bi bi-save me-1"></i>{{ saving ? '儲存中…' : '儲存' }}</button>
          <span v-if="dirty" class="small sqb-dirty"><i class="bi bi-dot"></i>有未儲存的變更</span>
          <span v-else class="small text-muted">已儲存</span>
        </template>
        <span v-else class="small text-muted"><i class="bi bi-eye me-1"></i>唯讀（{{ board.owner_name }} 建立）</span>
        <button type="button" class="btn btn-sm btn-outline-secondary ms-auto" :disabled="creating" @click="createBoard(board.id)">
          <i class="bi bi-files me-1"></i>複製成我的</button>
      </div>
      <div v-if="conflict" class="alert alert-warning py-2 small d-flex flex-wrap align-items-center gap-2">
        這張表已經在別的視窗改過，目前的修改沒有存進去。
        <button type="button" class="btn btn-sm btn-warning ms-auto" @click="openBoard(board.id, true)">重新載入（放棄目前的修改）</button>
      </div>

      <SquadBoardView v-if="!board.can_edit" :board="board" :card-class="cardClass" />

      <template v-else>
        <!-- 表頭 -->
        <div :class="[cardClass, 'mb-3']">
          <div class="card-body py-3">
            <div class="row g-2">
              <div class="col-12 col-md-6">
                <label class="form-label small fw-semibold mb-1" for="sqb-title">名稱</label>
                <input id="sqb-title" v-model="board.title" type="text" maxlength="60" class="form-control form-control-sm"
                  :class="{ 'is-invalid': !board.title.trim() }">
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label small fw-semibold mb-1" for="sqb-event">行動時間（選填）</label>
                <input id="sqb-event" v-model="board.event_at" type="datetime-local" class="form-control form-control-sm">
              </div>
              <div class="col-12">
                <label class="form-label small fw-semibold mb-1" for="sqb-note">備註（選填）</label>
                <textarea id="sqb-note" v-model="board.note" rows="2" maxlength="500" class="form-control form-control-sm"
                  placeholder="集合地點、通訊頻道、注意事項…"></textarea>
              </div>
            </div>
            <!-- 分享連結（立即生效，不用按儲存） -->
            <div class="sqb-share mt-3">
              <div class="form-check form-switch mb-1">
                <input id="sqb-share" class="form-check-input" type="checkbox" :checked="!!board.share_token"
                  :disabled="sharing" @change="setShare($event.target.checked)">
                <label class="form-check-label fw-semibold" for="sqb-share">分享連結</label>
              </div>
              <div class="small text-muted mb-2">知道連結的人不用登入就能看到這張表的人員名單（只有暱稱、職位；看不到 Discord、持有的船或物品）。</div>
              <div v-if="board.share_token" class="d-flex flex-wrap gap-2">
                <input :value="shareUrl" type="text" readonly class="form-control form-control-sm sqb-share__url" aria-label="分享連結"
                  @focus="$event.target.select()">
                <button type="button" class="btn btn-sm btn-primary" @click="copyShare">
                  <i class="bi me-1" :class="copied ? 'bi-check-lg' : 'bi-clipboard'"></i>{{ copied ? '已複製' : '複製連結' }}</button>
                <a class="btn btn-sm btn-outline-secondary" :href="shareUrl" target="_blank" rel="noopener"><i class="bi bi-box-arrow-up-right me-1"></i>預覽</a>
                <button type="button" class="btn btn-sm btn-warning" :disabled="sharing" @click="regenerateShare">
                  <i class="bi bi-arrow-repeat me-1"></i>重新產生（舊連結失效）</button>
              </div>
            </div>
            <div class="small text-muted mt-2">
              {{ board.squads.length }} 個小隊 · {{ countShips(board) }} 艘船 · {{ countPeople(board) }} 人
              <span v-if="dupes.size" class="sf-chip sf-chip--warn ms-1">{{ dupes.size }} 人重複出現</span>
            </div>
          </div>
        </div>

        <datalist id="sqb-roles"><option v-for="r in DEFAULT_ROLES" :key="r" :value="r" /></datalist>

        <!-- 小隊 -->
        <div class="row g-3">
          <div v-for="(s, si) in board.squads" :key="s.id" class="col-12 col-xl-6">
            <section :class="[cardClass, 'h-100']" :aria-label="s.name || `小隊 ${si + 1}`">
              <div class="card-body">
                <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
                  <span class="sqb-no">{{ si + 1 }}</span>
                  <input v-model="s.name" type="text" maxlength="40" class="form-control form-control-sm sqb-squad-name"
                    :aria-label="`小隊 ${si + 1} 名稱`">
                  <div class="btn-group btn-group-sm ms-auto">
                    <button type="button" class="btn btn-outline-secondary" :disabled="si === 0" aria-label="小隊上移"
                      @click="moveItem(board.squads, si, -1)"><i class="bi bi-arrow-up"></i></button>
                    <button type="button" class="btn btn-outline-secondary" :disabled="si === board.squads.length - 1"
                      aria-label="小隊下移" @click="moveItem(board.squads, si, 1)"><i class="bi bi-arrow-down"></i></button>
                  </div>
                  <button type="button" class="btn btn-sm btn-danger" :aria-label="`刪除${s.name}`" @click="removeSquad(si)">
                    <i class="bi bi-trash"></i></button>
                </div>
                <div class="row g-2 mb-2">
                  <div class="col-12 col-sm-5">
                    <label class="form-label small mb-1" :for="`sqb-leader-${s.id}`">隊長</label>
                    <select :id="`sqb-leader-${s.id}`" v-model="s.leader" class="form-select form-select-sm">
                      <option :value="null">（未指定）</option>
                      <option v-for="p in squadPeople(s)" :key="p.id" :value="p.id">{{ p.name }}</option>
                    </select>
                  </div>
                  <div class="col-12 col-sm-7">
                    <label class="form-label small mb-1" :for="`sqb-snote-${s.id}`">備註</label>
                    <input :id="`sqb-snote-${s.id}`" v-model="s.note" type="text" maxlength="500" class="form-control form-control-sm"
                      placeholder="任務、頻道…">
                  </div>
                </div>

                <!-- 艦船 -->
                <div v-for="(v, vi) in s.ships" :key="v.id" class="sqb-ship">
                  <div class="sqb-ship__head">
                    <i class="bi bi-rocket-takeoff" aria-hidden="true"></i>
                    <span class="fw-semibold">{{ v.vehicle_name }}</span>
                    <input v-model="v.label" type="text" maxlength="40" class="form-control form-control-sm sqb-label"
                      placeholder="識別名稱（例如一號機）" :aria-label="`${v.vehicle_name} 識別名稱`">
                    <span class="sf-chip" :class="{ 'sf-chip--warn': v.crew_max && v.crew.length > v.crew_max }"
                      :title="v.crew_max ? `建議乘員 ${v.crew_max} 人` : ''">{{ v.crew.length }}{{ v.crew_max ? ` / ${v.crew_max}` : '' }} 人</span>
                    <div class="btn-group btn-group-sm ms-auto">
                      <button type="button" class="btn btn-outline-secondary" :disabled="vi === 0" aria-label="艦船上移"
                        @click="moveItem(s.ships, vi, -1)"><i class="bi bi-arrow-up"></i></button>
                      <button type="button" class="btn btn-outline-secondary" :disabled="vi === s.ships.length - 1"
                        aria-label="艦船下移" @click="moveItem(s.ships, vi, 1)"><i class="bi bi-arrow-down"></i></button>
                    </div>
                    <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除${v.vehicle_name}`" @click="removeShip(s, vi)">
                      <i class="bi bi-x-lg"></i></button>
                  </div>
                  <PeopleRows :list="v.crew" :squad="s" />
                  <AutocompleteField :id="`sqb-add-${v.id}`" v-model="addText[v.id]" :search="searchPeople"
                    :get-label="personLabel" :get-meta="personMeta" :min-chars="1" :debounce-ms="0"
                    class="mt-1" placeholder="加入人員：打暱稱或遊戲ID" :aria-label="`加入人員到${shipTitle(v)}`"
                    @select="c => addPerson(v.crew, c, v.id)" />
                </div>

                <!-- 不在船上 -->
                <div class="sqb-ship sqb-ship--off">
                  <div class="sqb-ship__head"><i class="bi bi-person-walking" aria-hidden="true"></i>
                    <span class="fw-semibold">不在船上</span><span class="small text-muted">（地面隊、待命…）</span></div>
                  <PeopleRows :list="s.members" :squad="s" />
                  <AutocompleteField :id="`sqb-add-${s.id}`" v-model="addText[s.id]" :search="searchPeople"
                    :get-label="personLabel" :get-meta="personMeta" :min-chars="1" :debounce-ms="0"
                    class="mt-1" placeholder="加入人員：打暱稱或遊戲ID" :aria-label="`加入人員到${s.name}（不在船上）`"
                    @select="c => addPerson(s.members, c, s.id)" />
                </div>

                <!-- 加入艦船 -->
                <div class="mt-2">
                  <label class="form-label small mb-1" :for="`sqb-ship-${s.id}`">加入艦船</label>
                  <AutocompleteField :id="`sqb-ship-${s.id}`" v-model="shipText[s.id]" :search="searchShips"
                    :get-label="c => c.name" :get-meta="shipMeta" :min-chars="0" :debounce-ms="250"
                    placeholder="船名（自己機庫的船排前面）" :aria-label="`加入艦船到${s.name}`"
                    @select="c => addShip(s, c)" />
                </div>
              </div>
            </section>
          </div>
        </div>
        <button type="button" class="btn btn-sm btn-success mt-3" :disabled="board.squads.length >= MAX_SQUADS" @click="addSquad">
          <i class="bi bi-plus-lg me-1"></i>新增小隊</button>
      </template>
    </template>

    <ConfirmModal ref="confirmRef" />
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AutocompleteField from '@/components/AutocompleteField.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'
import SfState from '@/components/SfState.vue'
import SquadBoardView from '@/components/SquadBoardView.vue'
import { toast } from '@/utils/toast'
import {
  DEFAULT_ROLES, MAX_PEOPLE, MAX_SHIPS_PER_SQUAD, MAX_SQUADS, boardPayload, countPeople, countShips,
  duplicateScids, emptySquad, fmtEventAt, moveItem, movePerson, newId, personLocation, personTargets,
  shipTitle, squadPeople,
} from '@/utils/squadBoard'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
  // 自己機庫的船（vehicle UUID）：加入艦船時排前面
  fleetUuids: { type: Array, default: () => [] },
  // 自己的遊戲ID（判斷哪些表是自己的）
  me: { type: String, default: '' },
  cardClass: { type: String, default: 'card scifi-card' },
})

const route = useRoute()
const router = useRouter()
const confirmRef = ref(null)

// ── 訊息：全站的 toast（utils/toast.js）──
const flash = (msg, type = 'success') => toast(msg, type)

async function api(path, options = {}) {
  const res = await props.fetcher(path, options)
  if (!res) return { ok: false, status: 0, data: { message: '網路錯誤，請稍後再試' } }
  const data = await res.json().catch(() => null)
  return { ok: res.ok && !!data?.success, status: res.status, data: data || {} }
}

const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
function fmtTs(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString('zh-TW', { hour12: false })
}

// ══════════ 列表 ══════════
const boards = ref([])
const listLoading = ref(false)
const listLoaded = ref(false)
const listError = ref('')
const mineOnly = ref(false)
const listQuery = ref('')
const shownBoards = computed(() => {
  const q = listQuery.value.trim().toLowerCase()
  return boards.value.filter(b => (!mineOnly.value || b.owner_scid === props.me)
    && (!q || `${b.title} ${b.owner_name} ${b.owner_scid}`.toLowerCase().includes(q)))
})

async function loadList() {
  listLoading.value = true
  listError.value = ''
  const { ok, data } = await api('/player/squads')
  listLoading.value = false
  if (!ok) { listError.value = data.message || '讀取失敗。'; return }
  boards.value = data.data || []
  listLoaded.value = true
}

const creating = ref(false)
async function createBoard(copyFrom = '') {
  if (creating.value) return
  if (board.value && dirty.value && !(await confirmLeave())) return
  creating.value = true
  const body = copyFrom ? { copy_from: copyFrom } : { title: '新的分配表' }
  const { ok, data } = await api('/player/squads', { method: 'POST', body: JSON.stringify(body) })
  creating.value = false
  if (!ok) { flash(data.message || '新增失敗', 'alert-warning'); return }
  setBoard(data.data)
  flash(copyFrom ? '已複製一份，現在是你的分配表。' : '已新增，填好後記得按「儲存」。')
  loadList()
}

async function deleteBoard(b) {
  const ok = await confirmRef.value.confirm(`確定要刪除分配表 <strong>${escapeHtml(b.title)}</strong>？`)
  if (!ok) return
  const res = await api(`/player/squads/${b.id}`, { method: 'DELETE' })
  if (!res.ok) { flash(res.data.message || '刪除失敗', 'alert-warning'); return }
  boards.value = boards.value.filter(x => x.id !== b.id)
  flash('已刪除。')
}

// ══════════ 開啟的表 ══════════
const board = ref(null)
const saved = ref('')       // 最後一次存檔（或載入）時的內容，用來判斷有沒有改過
const saving = ref(false)
const conflict = ref(false)
const addText = reactive({})    // 各艘船／不在船上的「加入人員」輸入框文字
const shipText = reactive({})   // 各小隊的「加入艦船」輸入框文字
const dirty = computed(() => !!board.value?.can_edit && JSON.stringify(boardPayload(board.value)) !== saved.value)
const dupes = computed(() => (board.value ? duplicateScids(board.value) : new Set()))

function setBoard(data) {
  if (data) {
    data.title = data.title || ''
    data.event_at = data.event_at || ''
    data.note = data.note || ''
    data.squads = data.squads || []
  }
  board.value = data
  saved.value = data ? JSON.stringify(boardPayload(data)) : ''
  conflict.value = false
  syncBoardUrl()
}

async function openBoard(id, force = false) {
  if (!force && board.value && board.value.id !== id && dirty.value && !(await confirmLeave())) return
  const { ok, status, data } = await api(`/player/squads/${id}`)
  if (!ok) {
    flash(status === 404 ? '找不到這張分配表（可能已被刪除）' : (data.message || '讀取失敗'), 'alert-warning')
    if (status === 404) setBoard(null)
    return
  }
  setBoard(data.data)
}

async function confirmLeave() {
  return confirmRef.value.confirm('這張表有未儲存的變更，確定要離開？', { title: '尚未儲存', okText: '放棄變更' })
}

async function closeBoard() {
  if (dirty.value && !(await confirmLeave())) return
  setBoard(null)
  loadList()
}

async function save() {
  if (!board.value || saving.value) return
  if (!board.value.title.trim()) { flash('名稱不得為空', 'alert-warning'); return }
  saving.value = true
  const { ok, status, data } = await api(`/player/squads/${board.value.id}`, {
    method: 'PUT', body: JSON.stringify(boardPayload(board.value)),
  })
  saving.value = false
  if (status === 409) { conflict.value = true; return }
  if (!ok) { flash(data.message || '儲存失敗', 'alert-warning'); return }
  setBoard(data.data)
  flash('已儲存。')
}

// 關掉分頁或重新整理前提醒還沒存
function beforeUnload(e) {
  if (!dirty.value) return
  e.preventDefault()
  e.returnValue = ''
}
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))

// ── 網址 ?board=<id> ──
function syncBoardUrl() {
  if (!props.active) return
  const id = board.value?.id || ''
  if ((route.query.board || '') === id) return
  const query = { ...route.query }
  if (id) query.board = id
  else delete query.board
  router.replace({ query })
}
// ── 分享 ──
const sharing = ref(false)
const copied = ref(false)
const shareUrl = computed(() => (board.value?.share_token
  ? new URL(router.resolve(`/player/squad/${board.value.share_token}`).href, window.location.origin).toString() : ''))
async function callShare(enabled, regenerate = false) {
  sharing.value = true
  const { ok, data } = await api(`/player/squads/${board.value.id}/share`, {
    method: 'POST', body: JSON.stringify({ enabled, regenerate }),
  })
  sharing.value = false
  if (!ok) { flash(data.message || '設定失敗', 'alert-warning'); return }
  board.value.share_token = data.data.share_token
  flash(!enabled ? '已關閉分享連結，舊連結失效。' : regenerate ? '已重新產生，舊連結失效。' : '已開啟分享連結。')
}
const setShare = enabled => callShare(enabled)
async function regenerateShare() {
  const ok = await confirmRef.value.confirm('重新產生後，之前分享出去的連結就打不開了。', { title: '重新產生分享連結', okText: '重新產生' })
  if (ok) callShare(true, true)
}
async function copyShare() {
  try {
    await navigator.clipboard.writeText(shareUrl.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* 瀏覽器不給複製就算了，輸入框可以手動複製 */ }
}

// ── 小隊、艦船 ──
function addSquad() {
  if (board.value.squads.length >= MAX_SQUADS) return
  board.value.squads.push(emptySquad(board.value))
}
async function removeSquad(i) {
  const s = board.value.squads[i]
  const n = squadPeople(s).length
  if (s.ships.length || n) {
    const ok = await confirmRef.value.confirm(`確定要刪除 <strong>${escapeHtml(s.name)}</strong>（${s.ships.length} 艘船、${n} 人）？`)
    if (!ok) return
  }
  board.value.squads.splice(i, 1)
}
function addShip(s, c) {
  if (!c) return
  if (s.ships.length >= MAX_SHIPS_PER_SQUAD) { flash(`每個小隊最多 ${MAX_SHIPS_PER_SQUAD} 艘船`, 'alert-warning'); return }
  s.ships.push({ id: newId(board.value, 'v'), vehicle_id: c._id, vehicle_name: c.name, label: '', crew_max: c.crew_max, crew: [] })
  setTimeout(() => { shipText[s.id] = '' })
}
async function removeShip(s, i) {
  const v = s.ships[i]
  if (v.crew.length) {
    const ok = await confirmRef.value.confirm(`移除 <strong>${escapeHtml(shipTitle(v))}</strong>？船上的 ${v.crew.length} 人會移到「不在船上」。`,
      { title: '移除艦船', okText: '移除' })
    if (!ok) return
    s.members.push(...v.crew)
  }
  s.ships.splice(i, 1)
}

const fleetSet = computed(() => new Set(props.fleetUuids))
const shipMeta = c => [fleetSet.value.has(c._id) ? '我的機庫' : '', c.crew_max ? `乘員 ${c.crew_max}` : ''].filter(Boolean).join(' · ')
let fleetShips = null   // 自己機庫的船（沒打字時列出來；第一次用到才查 /player/fleet）
async function searchShips(q) {
  const t = (q || '').trim()
  if (!t) {
    // 沒打字：先列自己機庫的船
    if (!props.fleetUuids.length) return []
    if (!fleetShips) {
      const { ok, data } = await api('/player/fleet')
      const seen = new Set()
      fleetShips = ok ? (data.data || []).filter(r => r.vehicle_uuid && !seen.has(r.vehicle_uuid) && seen.add(r.vehicle_uuid))
        .map(r => ({ _id: r.vehicle_uuid, name: r.vehicle?.name || r.vehicle_name || r.vehicle_uuid, crew_max: r.vehicle?.crew_max }))
        .sort((a, b) => a.name.localeCompare(b.name)) : []
    }
    return fleetShips
  }
  const { ok, data } = await api(`/item/vehicles?${new URLSearchParams({ q: t, limit: '30' })}`)
  if (!ok) return []
  const rows = data.data || []
  return rows.sort((a, b) => fleetSet.value.has(b._id) - fleetSet.value.has(a._id))
}

// ── 人員 ──
const roster = ref([])   // 全部玩家（暱稱、遊戲ID），加入人員的候選
async function loadRoster() {
  const { ok, data } = await api('/player/search?q=')
  if (ok) roster.value = data.data || []
}
const norm = t => (t || '').toLowerCase()
async function searchPeople(q) {
  const t = norm(q.trim())
  if (!t) return []
  const rows = roster.value.filter(p => norm(p.nickname).includes(t) || norm(p.star_citizen_id).includes(t)
    || norm(p.player_name).includes(t)).slice(0, 12).map(p => ({ kind: 'player', ...p }))
  return [...rows, { kind: 'guest', name: q.trim().slice(0, 40) }]
}
const personLabel = c => (c.kind === 'guest' ? `「${c.name}」加為未註冊人員` : (c.nickname || c.star_citizen_id))
function personMeta(c) {
  if (c.kind === 'guest') return '只記名字'
  const where = board.value && personWhere(c.star_citizen_id)
  return [c.nickname ? c.star_citizen_id : '', where ? `已在 ${where}` : ''].filter(Boolean).join(' · ')
}
function personWhere(scid) {
  for (const s of board.value.squads) {
    for (const v of s.ships) if (v.crew.some(p => p.scid === scid)) return `${s.name} › ${shipTitle(v)}`
    if (s.members.some(p => p.scid === scid)) return `${s.name} › 不在船上`
  }
  return ''
}
function addPerson(list, c, inputKey) {
  if (!c) return
  if (countPeople(board.value) >= MAX_PEOPLE) { flash(`人員最多 ${MAX_PEOPLE} 人`, 'alert-warning'); return }
  const person = c.kind === 'guest'
    ? { id: newId(board.value, 'm'), scid: null, name: c.name, role: '', registered: false }
    : { id: newId(board.value, 'm'), scid: c.star_citizen_id, name: c.nickname || c.star_citizen_id, role: '', registered: true }
  if (!person.name) return
  list.push(person)
  // AutocompleteField 選定後會把文字寫回輸入框；下一輪清空，方便連續加人
  setTimeout(() => { addText[inputKey] = '' })
}

// 人員列：名字（未註冊／重複）、職位、移到、上下、移除
const PeopleRows = defineComponent({
  props: { list: { type: Array, required: true }, squad: { type: Object, required: true } },
  setup(p) {
    return () => {
      const targets = personTargets(board.value)
      return h('ul', { class: 'sqb-people' }, p.list.length ? p.list.map((m, i) => h('li', { key: m.id, class: 'sqb-person' }, [
        h('span', { class: 'sqb-person__name' }, [
          p.squad.leader === m.id ? h('i', { class: 'bi bi-star-fill sqb-star me-1', title: '隊長', 'aria-label': '隊長' }) : null,
          h('span', { class: 'fw-semibold' }, m.name),
          m.registered === false ? h('span', { class: 'sf-chip sf-chip--todo ms-1' }, '未註冊') : null,
          m.scid && dupes.value.has(m.scid) ? h('span', { class: 'sf-chip sf-chip--warn ms-1' }, '重複') : null,
        ]),
        h('input', {
          class: 'form-control form-control-sm sqb-role', list: 'sqb-roles', maxlength: 40, placeholder: '職位',
          value: m.role, 'aria-label': `${m.name} 職位`, onInput: e => { m.role = e.target.value },
        }),
        h('select', {
          class: 'form-select form-select-sm sqb-move', 'aria-label': `${m.name} 移到`,
          value: personLocation(board.value, m.id),
          onChange: e => movePerson(board.value, m.id, e.target.value),
        }, targets.map(t => h('option', { value: t.key }, t.label))),
        h('div', { class: 'btn-group btn-group-sm' }, [
          h('button', { type: 'button', class: 'btn btn-outline-secondary', disabled: i === 0, 'aria-label': `${m.name} 上移`,
            onClick: () => moveItem(p.list, i, -1) }, [h('i', { class: 'bi bi-arrow-up' })]),
          h('button', { type: 'button', class: 'btn btn-outline-secondary', disabled: i === p.list.length - 1,
            'aria-label': `${m.name} 下移`, onClick: () => moveItem(p.list, i, 1) }, [h('i', { class: 'bi bi-arrow-down' })]),
        ]),
        h('button', { type: 'button', class: 'btn btn-sm btn-outline-danger', 'aria-label': `移除${m.name}`,
          onClick: () => { p.list.splice(i, 1); if (p.squad.leader === m.id) p.squad.leader = null } },
        [h('i', { class: 'bi bi-x-lg' })]),
      ])) : [h('li', { class: 'text-muted small py-1' }, '（尚未分配人員）')])
    }
  },
})

// 放在最後：immediate 會馬上執行，要用到上面宣告的 roster 等變數
watch(() => props.active, on => {
  if (!on) return
  if (!listLoaded.value && !listLoading.value) loadList()
  if (!roster.value.length) loadRoster()
  const id = String(route.query.board || '')
  if (id && board.value?.id !== id) openBoard(id)
  else syncBoardUrl()
}, { immediate: true })
watch(() => route.query.board, id => {
  if (!props.active) return
  if (id && board.value?.id !== id) openBoard(String(id))
})
</script>

<style scoped>
.sqb-search { max-width: 16rem; }
.sqb-sticky { position: sticky; top: 0; z-index: 5; background: var(--sf-header-bg, var(--sf-panel)); padding-block: .4rem; }
.sqb-dirty { color: var(--sf-accent-2); font-weight: 600; }
.sqb-share { border-top: 1px solid var(--sf-border); padding-top: .75rem; }
.sqb-share__url { flex: 1 1 18rem; max-width: 34rem; }
.sqb-no {
  display: inline-flex; align-items: center; justify-content: center; width: 1.9rem; height: 1.9rem; flex: 0 0 auto;
  border-radius: 50%; background: var(--sf-accent-2); color: #0b1020; font-weight: 700;
}
.sqb-squad-name { flex: 1 1 10rem; max-width: 18rem; font-weight: 600; }
.sqb-ship { border: 1px solid var(--sf-border-hi); border-radius: .5rem; padding: .5rem .6rem; margin-top: .6rem; background: var(--sf-chip-bg); }
.sqb-ship--off { border-style: dashed; }
.sqb-ship__head { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; }
.sqb-label { flex: 1 1 9rem; max-width: 14rem; }
.sqb-star { color: var(--sf-accent); }
:deep(.sqb-people) { list-style: none; margin: .4rem 0 0; padding: 0; }
:deep(.sqb-person) { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; padding: .3rem 0; border-top: 1px solid var(--sf-border); }
:deep(.sqb-person__name) { flex: 1 1 8rem; min-width: 6rem; display: inline-flex; align-items: center; flex-wrap: wrap; }
:deep(.sqb-role) { flex: 0 1 7rem; width: 7rem; }
:deep(.sqb-move) { flex: 0 1 11rem; width: 11rem; }
</style>
