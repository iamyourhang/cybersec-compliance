<template>
  <router-view />
  <Teleport to="body">
    <div class="toast-wrap">
      <div v-for="t in toasts" :key="t.id" :class="['toast', `toast-${t.type}`]">{{ t.msg }}</div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, provide } from 'vue'

const toasts = ref([])
function showToast(msg, type = 'success') {
  const id = Date.now()
  toasts.value.push({ id, msg, type })
  setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, 3000)
}
provide('toast', showToast)
</script>
