<template>
  <div>
    <div class="card" style="margin-bottom:20px">
      <div class="card-title">🔔 预警规则配置</div>
      <div v-if="loading" class="loading">加载中...</div>
      <table v-else>
        <thead><tr><th>规则名称</th><th>类型</th><th>提前天数</th><th>通知渠道</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="rule in rules" :key="rule.id">
            <td style="font-size:13px">{{ rule.name }}</td>
            <td><span class="tag">{{ rule.rule_type }}</span></td>
            <td style="font-family:var(--mono);font-size:13px">{{ rule.days_before ?? '—' }}</td>
            <td><span class="tag">{{ rule.notification_channel }}</span></td>
            <td>
              <span :style="{color: rule.enabled ? 'var(--green)':'var(--text3)', fontSize:12}">
                {{ rule.enabled ? '✅ 启用' : '○ 禁用' }}
              </span>
            </td>
            <td>
              <button class="btn btn-sm btn-outline" @click="toggleRule(rule)">
                {{ rule.enabled ? '禁用' : '启用' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import { settingsApi } from '@/api'

const toast = inject('toast')
const rules = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try { rules.value = (await settingsApi.getAlertRules()).items || [] }
  catch(e) { toast(String(e), 'error') }
  loading.value = false
}

async function toggleRule(rule) {
  try {
    await settingsApi.updateAlertRule(rule.id, { enabled: !rule.enabled })
    toast(rule.enabled ? '已禁用' : '已启用')
    load()
  } catch(e) { toast(String(e), 'error') }
}

onMounted(load)
</script>
