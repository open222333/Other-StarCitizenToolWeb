<!--
  使用方式（父元件）：
    const confirmRef = ref(null)
    const ok = await confirmRef.value.confirm('確定要刪除 <strong>xxx</strong>？')
    if (ok) { ... }
-->
<template>
  <div class="modal fade" ref="modalEl" tabindex="-1">
    <div class="modal-dialog modal-sm">
      <div class="modal-content border-0 shadow">

        <div class="modal-header border-0 pb-0">
          <h5 class="modal-title text-danger">
            <i class="bi bi-exclamation-triangle me-1"></i>確認刪除
          </h5>
          <button type="button" class="btn-close" @click="resolve(false)"></button>
        </div>

        <!-- v-html 可渲染 <strong> 等標記；呼叫端應自行 escHtml 使用者輸入 -->
        <div class="modal-body" v-html="message"></div>

        <div class="modal-footer border-0">
          <button type="button" class="btn btn-secondary btn-sm" @click="resolve(false)">
            取消
          </button>
          <button type="button" class="btn btn-danger btn-sm" @click="resolve(true)">
            刪除
          </button>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Modal } from 'bootstrap'

const modalEl = ref(null)
const message = ref('')
let   bsModal = null
let   _res    = null   // Promise resolver

onMounted(() => {
  bsModal = new Modal(modalEl.value, { backdrop: 'static' })
  // 點空白或按 Esc 關閉時，視同「取消」
  modalEl.value.addEventListener('hidden.bs.modal', () => {
    if (_res) { _res(false); _res = null }
  })
})

/** 顯示確認視窗，回傳 Promise<boolean> */
function confirm(msg) {
  message.value = msg
  bsModal.show()
  return new Promise((res) => { _res = res })
}

function resolve(val) {
  if (_res) { _res(val); _res = null }
  bsModal.hide()
}

defineExpose({ confirm })
</script>
