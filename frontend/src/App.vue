<template>
  <RouterView />
  <!-- 全站共用的提示（utils/toast.js 的 toast()） -->
  <SfToaster />
</template>

<script setup>
import SfToaster from '@/components/SfToaster.vue'
import { useThemeStore } from '@/stores/theme'
useThemeStore() // 初始化並套用已儲存的主題
</script>
