<template>
  <div style="display:grid;gap:20px">
    <div class="card">
      <div class="card-title">🛰 官方源白名单</div>
      <div style="font-size:13px;color:var(--text2);line-height:1.7">
        周更链路现在只从官方源白名单同步，AI 不再直接搜索并写入正式法规库。
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">
        <select class="select" style="width:120px" v-model="priority" @change="load">
          <option value="">全部优先级</option>
          <option value="P1">P1</option>
          <option value="P2">P2</option>
          <option value="P3">P3</option>
        </select>
        <button class="btn btn-outline" :disabled="loading" @click="load">刷新</button>
      </div>
    </div>

    <div class="card" style="padding:0">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>国家</th>
              <th>类型</th>
              <th>列表入口</th>
              <th>上次成功</th>
              <th>最近错误</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!items.length">
              <td colspan="7" class="empty">暂无官方源</td>
            </tr>
            <tr v-for="item in items" :key="item.id">
              <td>
                <div style="font-weight:600">{{ item.name }}</div>
                <div style="font-size:11px;color:var(--text3);margin-top:4px">
                  {{ item.country_priority }} · 优先级 {{ item.priority }}
                </div>
              </td>
              <td><span class="tag">{{ item.country_code }}</span></td>
              <td><span class="tag" :title="item.source_type">{{ sourceTypeLabel(item.source_type) }}</span></td>
              <td class="mono-cell" :title="item.list_url">{{ item.list_url }}</td>
              <td style="font-size:12px;color:var(--text2)">{{ item.last_success_at ? item.last_success_at.slice(0,19).replace('T',' ') : '—' }}</td>
              <td class="error-cell" :title="item.last_error || '—'">{{ item.last_error || '—' }}</td>
              <td>
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                  <button class="btn btn-sm btn-outline" :disabled="syncingId===item.id" @click="syncSource(item)">
                    {{ syncingId===item.id ? '同步中...' : '同步' }}
                  </button>
                  <button class="btn btn-sm btn-outline" @click="openHistory(item)">历史</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="historyModal" class="modal-overlay" @click.self="historyModal = null">
      <div class="modal" style="width:760px">
        <div class="modal-header">
          <span>同步历史 · {{ historyModal.name }}</span>
          <button class="close-btn" @click="historyModal = null">×</button>
        </div>
        <div class="modal-body">
          <div v-if="historyLoading" class="loading">加载中...</div>
          <div v-else-if="!historyItems.length" class="empty">暂无历史</div>
          <div v-else style="display:grid;gap:10px">
            <div v-for="item in historyItems" :key="item.id" class="event-card">
              <div class="event-meta">
                <span :title="item.status">{{ statusLabel(item.status) }}</span>
                <span>{{ (item.started_at || '').replace('T', ' ').slice(0, 19) }}</span>
              </div>
              <div style="font-size:13px;color:var(--text2)">
                发现 {{ item.discovered_count }} 条 · 候选 {{ item.candidate_count }} 条 · 工件 {{ item.artifact_count }} 条
              </div>
              <pre v-if="item.error" class="event-error">{{ item.error }}</pre>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="historyModal = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'
import { officialSourcesApi } from '@/api'
import { sourceTypeLabel, statusLabel } from '@/utils/labels'

const toast = inject('toast')
const loading = ref(false)
const syncingId = ref('')
const priority = ref('')
const items = ref([])
const historyModal = ref(null)
const historyLoading = ref(false)
const historyItems = ref([])

async function load() {
  loading.value = true
  try {
    const res = await officialSourcesApi.list(priority.value ? { country_priority: priority.value } : {})
    items.value = res.items || []
  } catch (e) {
    toast(String(e), 'error')
  }
  loading.value = false
}

async function syncSource(item) {
  syncingId.value = item.id
  try {
    const res = await officialSourcesApi.sync(item.id)
    toast(`同步完成：发现 ${res.discovered_count} 条，候选 ${res.candidate_count} 条`)
    await load()
  } catch (e) {
    toast(String(e), 'error')
    await load()
  }
  syncingId.value = ''
}

async function openHistory(item) {
  historyModal.value = item
  historyLoading.value = true
  historyItems.value = []
  try {
    const res = await officialSourcesApi.history(item.id, { limit: 30 })
    historyItems.value = res.items || []
  } catch (e) {
    toast(String(e), 'error')
  }
  historyLoading.value = false
}

onMounted(load)
</script>

<style scoped>
.mono-cell {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--mono);
  font-size: 12px;
}
.error-cell {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text3);
}
.event-card {
  border: 1px solid var(--border);
  background: var(--bg2);
  padding: 12px;
  border-radius: 4px;
}
.event-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 11px;
  color: var(--text3);
}
.event-error {
  margin-top: 8px;
  background: rgba(255, 64, 64, .08);
  border: 1px solid rgba(255, 64, 64, .18);
  color: var(--red);
  padding: 10px;
  border-radius: 4px;
  white-space: pre-wrap;
  font-size: 12px;
}
</style>
