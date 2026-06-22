<template>
  <th
    :style="{cursor: sortable ? 'pointer' : 'default', whiteSpace:'nowrap', userSelect:'none', ...thStyle}"
    @click="sortable && $emit('sort', field)"
  >
    {{ label }}
    <span v-if="sortable" style="margin-left:4px;font-size:10px;opacity:0.6">
      <span v-if="currentSort === field">{{ currentOrder === 'asc' ? '▲' : '▼' }}</span>
      <span v-else style="opacity:0.3">⇅</span>
    </span>
  </th>
</template>

<script setup>
defineProps({
  label:       { type: String, required: true },
  field:       { type: String, default: '' },
  sortable:    { type: Boolean, default: true },
  currentSort: { type: String, default: '' },
  currentOrder:{ type: String, default: 'asc' },
  thStyle:     { type: Object, default: () => ({}) },
})
defineEmits(['sort'])
</script>
