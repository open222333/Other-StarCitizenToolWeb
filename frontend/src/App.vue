<template>
  <RouterView />
</template>

<script setup>
import { useThemeStore } from '@/stores/theme'
useThemeStore() // 初始化並套用已儲存的主題
</script>
