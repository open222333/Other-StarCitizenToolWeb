<template>
  <div>

    <!-- ══ 使用者列表 ══ -->
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold">
        <i class="bi bi-people me-2 text-primary"></i>使用者管理
      </h5>
      <button class="btn btn-primary btn-sm" @click="userModalRef.open()">
        <i class="bi bi-plus-lg me-1"></i>新增使用者
      </button>
    </div>

    <Transition name="alert-slide">
      <div v-if="usersMsg" :class="`alert alert-${usersMsgType} py-2 mb-3`">{{ usersMsg }}</div>
    </Transition>

    <!-- ── 篩選 ────────────────────────────────────────────── -->
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="usernameQuery" type="text" class="form-control form-control-sm"
            style="max-width: 12rem" placeholder="搜尋帳號...">
          <MultiSelectFilter v-model="selectedRoles" label="角色" :options="roleOptions" />
          <MultiSelectFilter v-model="selectedTemplates" label="模板" :options="templateFilterOptions" />
          <button v-if="hasActiveUserFilters" type="button" class="btn btn-sm btn-link" @click="resetUserFilters">
            清除全部篩選
          </button>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0 mb-4">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3 sortable-th" role="button" tabindex="0"
                  @click="toggleUserSort('username')" @keydown.enter="toggleUserSort('username')">
                  帳號
                  <i v-if="userSortBy === 'username'" class="bi ms-1"
                    :class="userSortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleUserSort('role')" @keydown.enter="toggleUserSort('role')">
                  角色
                  <i v-if="userSortBy === 'role'" class="bi ms-1"
                    :class="userSortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleUserSort('template')" @keydown.enter="toggleUserSort('template')">
                  模板
                  <i v-if="userSortBy === 'template'" class="bi ms-1"
                    :class="userSortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleUserSort('created_at')" @keydown.enter="toggleUserSort('created_at')">
                  建立時間
                  <i v-if="userSortBy === 'created_at'" class="bi ms-1"
                    :class="userSortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th style="width:180px" class="pe-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loadingUsers">
                <td colspan="5" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!filteredUsers.length">
                <td colspan="5" class="text-center py-4 text-muted">
                  {{ hasActiveUserFilters ? '沒有符合篩選條件的使用者。' : '尚無使用者' }}
                </td>
              </tr>
              <template v-else>
                <tr v-for="u in filteredUsers" :key="u._id">
                  <td class="ps-3 fw-semibold">
                    {{ u.username }}
                    <span v-if="u.username === 'admin'"
                      class="badge bg-danger-subtle text-danger border border-danger-subtle ms-1"
                      title="系統保護帳號，不可刪除">
                      <i class="bi bi-shield-fill-check"></i>
                    </span>
                    <span v-if="u.username === auth.username"
                      class="badge bg-primary-subtle text-primary border border-primary-subtle ms-1">
                      自己
                    </span>
                  </td>
                  <td>
                    <span :class="`badge bg-${roleColor(u.role)}`">{{ roleLabel(u.role) }}</span>
                  </td>
                  <td class="small">{{ templateName(u.template_id) || '—' }}</td>
                  <td class="text-muted small">{{ fmtDate(u.created_at) }}</td>
                  <td class="pe-3">
                    <button class="btn btn-sm btn-outline-secondary me-1"
                      @click="userModalRef.open(u)">
                      <i class="bi bi-pencil"></i> 編輯
                    </button>
                    <button class="btn btn-sm btn-outline-danger"
                      :disabled="u.username === 'admin' || u.username === auth.username"
                      :title="u.username === 'admin' ? '系統保護帳號不可刪除'
                             : u.username === auth.username ? '不可刪除自己' : ''"
                      @click="handleDeleteUser(u)">
                      <i class="bi bi-trash"></i>
                    </button>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ══ 使用者模板（可收合）══ -->
    <hr class="my-0 mb-3">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h6 class="mb-0 fw-bold section-toggle" @click="tmplOpen = !tmplOpen">
        <i class="bi me-1 toggle-icon" :class="tmplOpen ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
        <i class="bi bi-person-badge me-1 text-secondary"></i>使用者模板
        <FieldHint text="模板決定使用者的角色。系統模板為系統預設，不可刪除。修改模板角色時，持有該模板的所有使用者角色將自動同步。" />
      </h6>
      <button v-show="tmplOpen" class="btn btn-outline-secondary btn-sm"
        @click="templateModalRef.open()">
        <i class="bi bi-plus-lg me-1"></i>新增模板
      </button>
    </div>

    <template v-if="tmplOpen">
      <Transition name="alert-slide">
        <div v-if="tmplMsg" :class="`alert alert-${tmplMsgType} py-2 mb-3`">{{ tmplMsg }}</div>
      </Transition>

      <!-- ── 篩選 ────────────────────────────────────────────── -->
      <div class="card shadow-sm border-0 mb-3">
        <div class="card-body py-2">
          <div class="d-flex flex-wrap align-items-center gap-2">
            <input v-model="tmplQuery" type="text" class="form-control form-control-sm"
              style="max-width: 14rem" placeholder="搜尋模板名稱／說明...">
            <MultiSelectFilter v-model="selectedTmplRoles" label="角色" :options="roleOptions" />
            <button v-if="hasActiveTmplFilters" type="button" class="btn btn-sm btn-link" @click="resetTmplFilters">
              清除全部篩選
            </button>
          </div>
        </div>
      </div>

      <div class="card shadow-sm border-0">
        <div class="card-body p-0">
          <div style="overflow-x:auto">
            <table class="table table-hover align-middle mb-0">
              <thead class="table-light">
                <tr>
                  <th class="ps-3 sortable-th" role="button" tabindex="0"
                    @click="toggleTmplSort('name')" @keydown.enter="toggleTmplSort('name')">
                    模板名稱
                    <i v-if="tmplSortBy === 'name'" class="bi ms-1"
                      :class="tmplSortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                  </th>
                  <th class="sortable-th" role="button" tabindex="0"
                    @click="toggleTmplSort('role')" @keydown.enter="toggleTmplSort('role')">
                    角色
                    <i v-if="tmplSortBy === 'role'" class="bi ms-1"
                      :class="tmplSortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                  </th>
                  <th class="sortable-th" role="button" tabindex="0"
                    @click="toggleTmplSort('description')" @keydown.enter="toggleTmplSort('description')">
                    說明
                    <i v-if="tmplSortBy === 'description'" class="bi ms-1"
                      :class="tmplSortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                  </th>
                  <th class="sortable-th" role="button" tabindex="0"
                    @click="toggleTmplSort('created_at')" @keydown.enter="toggleTmplSort('created_at')">
                    建立時間
                    <i v-if="tmplSortBy === 'created_at'" class="bi ms-1"
                      :class="tmplSortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                  </th>
                  <th style="width:180px" class="pe-3">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="loadingTemplates">
                  <td colspan="5" class="text-center py-4 text-muted">
                    <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                  </td>
                </tr>
                <tr v-else-if="!filteredTemplates.length">
                  <td colspan="5" class="text-center py-4 text-muted">
                    {{ hasActiveTmplFilters ? '沒有符合篩選條件的模板。' : '尚無模板' }}
                  </td>
                </tr>
                <template v-else>
                  <tr v-for="t in filteredTemplates" :key="t._id">
                    <td class="ps-3 fw-semibold">
                      {{ t.name }}
                      <span v-if="t.is_system" class="badge bg-warning text-dark ms-1">
                        <i class="bi bi-shield-fill me-1"></i>系統
                      </span>
                    </td>
                    <td>
                      <span :class="`badge bg-${roleColor(t.role)}`">{{ roleLabel(t.role) }}</span>
                    </td>
                    <td class="small text-muted">{{ t.description || '—' }}</td>
                    <td class="text-muted small">{{ fmtDate(t.created_at) }}</td>
                    <td class="pe-3">
                      <button class="btn btn-sm btn-outline-secondary me-1"
                        @click="templateModalRef.open(t)">
                        <i class="bi bi-pencil"></i> 編輯
                      </button>
                      <button class="btn btn-sm btn-outline-danger"
                        :disabled="t.is_system"
                        :title="t.is_system ? '系統預設模板不可刪除' : ''"
                        @click="handleDeleteTemplate(t)">
                        <i class="bi bi-trash"></i>
                      </button>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>

    <!-- Modals -->
    <UserModal     ref="userModalRef"     :templates="templates" @saved="onUserSaved" />
    <TemplateModal ref="templateModalRef"                        @saved="onTemplateSaved" />
    <ConfirmModal  ref="confirmModalRef" />

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { userApi } from '@/api'
import UserModal        from '@/components/UserModal.vue'
import TemplateModal    from '@/components/TemplateModal.vue'
import ConfirmModal     from '@/components/ConfirmModal.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import FieldHint         from '@/components/FieldHint.vue'

const auth = useAuthStore()

// ── Data ──────────────────────────────────────────────────────────
const users             = ref([])
const templates         = ref([])
const loadingUsers      = ref(false)
const loadingTemplates  = ref(false)
const tmplOpen          = ref(true)

// ── Modal refs ───────────────────────────────────────────────────
const userModalRef     = ref(null)
const templateModalRef = ref(null)
const confirmModalRef  = ref(null)

// ── Alert state ──────────────────────────────────────────────────
const usersMsg     = ref(''); const usersMsgType = ref('success')
const tmplMsg      = ref(''); const tmplMsgType  = ref('success')

function flash(msgRef, typeRef, msg, type = 'danger') {
  msgRef.value = msg; typeRef.value = type
  setTimeout(() => { msgRef.value = '' }, 3000)
}

// ── Helpers ──────────────────────────────────────────────────────
const ROLE_LABELS = { admin: '管理員', operator: '操作員', viewer: '檢視者' }
const ROLE_COLORS = { admin: 'danger',  operator: 'warning',  viewer: 'secondary' }
const roleLabel = (r) => ROLE_LABELS[r] || r
const roleColor = (r) => ROLE_COLORS[r] || 'secondary'
const roleOptions = Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))

const templatesMap = computed(() =>
  Object.fromEntries(templates.value.map(t => [t._id, t]))
)
const templateName = (id) => id ? (templatesMap.value[id]?.name ?? '') : ''
const fmtDate = (d) => d ? new Date(d).toLocaleString('zh-TW') : '—'

// ── 使用者：篩選／排序（帳號跟模板都是後台一次性載入的小清單，不像操作紀錄
// 那樣會一路長大，所以這裡直接在前端 computed 裡篩跟排，不用另外改後端
// 加分頁 —— 沒有資料量會撐爆這頁的問題，加了反而是白工。） ─────────────
const usernameQuery    = ref('')
const selectedRoles    = ref([])
const selectedTemplates = ref([])   // '' 代表「未指定模板」
const userSortBy  = ref('username')
const userSortDir = ref('asc')

// 模板下拉多一個「未指定模板」的假選項，讓「模板」欄也符合「每個顯示欄位都能篩」。
const templateFilterOptions = computed(() => [
  { value: '', label: '（未指定模板）' },
  ...templates.value.map(t => ({ value: t._id, label: t.name })),
])

const hasActiveUserFilters = computed(() =>
  usernameQuery.value.trim() || selectedRoles.value.length || selectedTemplates.value.length)

function resetUserFilters() {
  usernameQuery.value = ''
  selectedRoles.value = []
  selectedTemplates.value = []
}

function toggleUserSort(field) {
  if (userSortBy.value === field) {
    userSortDir.value = userSortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    userSortBy.value = field
    userSortDir.value = 'asc'
  }
}

function _cmp(av, bv, dir) {
  if (av < bv) return dir === 'asc' ? -1 : 1
  if (av > bv) return dir === 'asc' ? 1 : -1
  return 0
}

const filteredUsers = computed(() => {
  let rows = users.value

  const q = usernameQuery.value.trim().toLowerCase()
  if (q) rows = rows.filter(u => (u.username || '').toLowerCase().includes(q))

  if (selectedRoles.value.length)
    rows = rows.filter(u => selectedRoles.value.includes(u.role))

  if (selectedTemplates.value.length)
    rows = rows.filter(u => selectedTemplates.value.includes(u.template_id || ''))

  rows = [...rows].sort((a, b) => {
    if (userSortBy.value === 'created_at') {
      return _cmp(new Date(a.created_at || 0).getTime(),
                  new Date(b.created_at || 0).getTime(), userSortDir.value)
    }
    if (userSortBy.value === 'template') {
      return _cmp(templateName(a.template_id).toLowerCase(),
                  templateName(b.template_id).toLowerCase(), userSortDir.value)
    }
    const av = (a[userSortBy.value] ?? '').toString().toLowerCase()
    const bv = (b[userSortBy.value] ?? '').toString().toLowerCase()
    return _cmp(av, bv, userSortDir.value)
  })
  return rows
})

// ── 使用者模板：同一套邏輯 ─────────────────────────────────────────
const tmplQuery         = ref('')
const selectedTmplRoles = ref([])
const tmplSortBy  = ref('name')
const tmplSortDir = ref('asc')

const hasActiveTmplFilters = computed(() =>
  tmplQuery.value.trim() || selectedTmplRoles.value.length)

function resetTmplFilters() {
  tmplQuery.value = ''
  selectedTmplRoles.value = []
}

function toggleTmplSort(field) {
  if (tmplSortBy.value === field) {
    tmplSortDir.value = tmplSortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    tmplSortBy.value = field
    tmplSortDir.value = 'asc'
  }
}

const filteredTemplates = computed(() => {
  let rows = templates.value

  const q = tmplQuery.value.trim().toLowerCase()
  if (q) rows = rows.filter(t =>
    (t.name || '').toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q))

  if (selectedTmplRoles.value.length)
    rows = rows.filter(t => selectedTmplRoles.value.includes(t.role))

  rows = [...rows].sort((a, b) => {
    if (tmplSortBy.value === 'created_at') {
      return _cmp(new Date(a.created_at || 0).getTime(),
                  new Date(b.created_at || 0).getTime(), tmplSortDir.value)
    }
    const av = (a[tmplSortBy.value] ?? '').toString().toLowerCase()
    const bv = (b[tmplSortBy.value] ?? '').toString().toLowerCase()
    return _cmp(av, bv, tmplSortDir.value)
  })
  return rows
})

// ── API calls ────────────────────────────────────────────────────
async function loadUsers() {
  loadingUsers.value = true
  const res = await userApi.list()
  if (res) { const d = await res.json(); users.value = d.data || [] }
  loadingUsers.value = false
}

async function loadTemplates() {
  loadingTemplates.value = true
  const res = await userApi.listTemplates()
  if (res) { const d = await res.json(); templates.value = d.data || [] }
  loadingTemplates.value = false
}

async function loadAll() {
  await Promise.all([loadUsers(), loadTemplates()])
}

// ── Event handlers ───────────────────────────────────────────────
async function onUserSaved() { await loadAll() }

async function onTemplateSaved(syncedUsers) {
  await loadAll()
  if (syncedUsers !== undefined)
    flash(tmplMsg, tmplMsgType, `已同步 ${syncedUsers} 位使用者的角色`, 'success')
}

async function handleDeleteUser(u) {
  const ok = await confirmModalRef.value.confirm(
    `確定要刪除使用者 <strong>${escHtml(u.username)}</strong>？`
  )
  if (!ok) return
  const res  = await userApi.remove(u._id)
  if (!res) return
  const data = await res.json()
  if (data.success) loadUsers()
  else flash(usersMsg, usersMsgType, data.message || '刪除失敗')
}

async function handleDeleteTemplate(t) {
  const ok = await confirmModalRef.value.confirm(
    `確定要刪除模板 <strong>${escHtml(t.name)}</strong>？`
  )
  if (!ok) return
  const res  = await userApi.removeTemplate(t._id)
  if (!res) return
  const data = await res.json()
  if (data.success) loadTemplates()
  else flash(tmplMsg, tmplMsgType, data.message || '刪除失敗')
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

onMounted(loadAll)
</script>

<style scoped>
.section-toggle { cursor: pointer; user-select: none; }
.toggle-icon    { transition: transform .2s; display: inline-block; }

.sortable-th { cursor: pointer; user-select: none; }
.sortable-th:hover { color: var(--bs-primary); }

.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
.alert-slide-leave-active { transition: all .15s ease; }
.alert-slide-leave-to     { opacity: 0; }
</style>
