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

    <div class="card shadow-sm border-0 mb-4">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">帳號</th>
                <th>角色</th>
                <th>模板</th>
                <th>建立時間</th>
                <th style="width:180px" class="pe-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loadingUsers">
                <td colspan="5" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!users.length">
                <td colspan="5" class="text-center py-4 text-muted">尚無使用者</td>
              </tr>
              <template v-else>
                <tr v-for="u in users" :key="u._id">
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
      </h6>
      <button v-show="tmplOpen" class="btn btn-outline-secondary btn-sm"
        @click="templateModalRef.open()">
        <i class="bi bi-plus-lg me-1"></i>新增模板
      </button>
    </div>

    <template v-if="tmplOpen">
      <div class="alert alert-info py-2 small mb-3">
        <i class="bi bi-info-circle me-1"></i>
        模板決定使用者的角色。
        <span class="badge bg-warning text-dark">系統</span> 模板為系統預設，不可刪除。
        修改模板角色時，持有該模板的所有使用者角色將自動同步。
      </div>

      <Transition name="alert-slide">
        <div v-if="tmplMsg" :class="`alert alert-${tmplMsgType} py-2 mb-3`">{{ tmplMsg }}</div>
      </Transition>

      <div class="card shadow-sm border-0">
        <div class="card-body p-0">
          <div style="overflow-x:auto">
            <table class="table table-hover align-middle mb-0">
              <thead class="table-light">
                <tr>
                  <th class="ps-3">模板名稱</th>
                  <th>角色</th>
                  <th>說明</th>
                  <th>建立時間</th>
                  <th style="width:180px" class="pe-3">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="loadingTemplates">
                  <td colspan="5" class="text-center py-4 text-muted">
                    <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                  </td>
                </tr>
                <tr v-else-if="!templates.length">
                  <td colspan="5" class="text-center py-4 text-muted">尚無模板</td>
                </tr>
                <template v-else>
                  <tr v-for="t in templates" :key="t._id">
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
import UserModal     from '@/components/UserModal.vue'
import TemplateModal from '@/components/TemplateModal.vue'
import ConfirmModal  from '@/components/ConfirmModal.vue'

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

const templatesMap = computed(() =>
  Object.fromEntries(templates.value.map(t => [t._id, t]))
)
const templateName = (id) => id ? (templatesMap.value[id]?.name ?? '') : ''
const fmtDate = (d) => d ? new Date(d).toLocaleString('zh-TW') : '—'

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

.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
.alert-slide-leave-active { transition: all .15s ease; }
.alert-slide-leave-to     { opacity: 0; }
</style>
