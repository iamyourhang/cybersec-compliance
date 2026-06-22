<template>
  <div style="display:grid;gap:20px">
    <div class="card channel-hero">
      <div>
        <div class="card-title">Adaptive Routing</div>
        <div class="channel-title">AI 通道池管理</div>
        <div class="channel-subtitle">
          只在识别到额度用完时自动切换到下一个通道。数据库为空时，系统会回退到环境变量兜底通道。
        </div>
      </div>
      <div class="channel-summary">
        <div class="summary-box">
          <div class="summary-label">可路由通道</div>
          <div class="summary-value">{{ stats.available }}</div>
        </div>
        <div class="summary-box warning">
          <div class="summary-label">额度耗尽</div>
          <div class="summary-value">{{ stats.exhausted }}</div>
        </div>
      </div>
    </div>

    <div class="filter-bar">
      <button class="btn btn-primary" @click="openCreate">新增通道</button>
      <button class="btn btn-outline" :disabled="loading" @click="loadChannels">刷新</button>
      <span class="mode-tag" :class="usingFallback ? 'mode-fallback' : 'mode-db'">
        {{ usingFallback ? '当前显示 .env 兜底通道（只读）' : '当前使用数据库通道池' }}
      </span>
    </div>

    <div class="card" style="padding:0">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>协议</th>
              <th>模型</th>
              <th>Base URL</th>
              <th>优先级</th>
              <th>状态</th>
              <th>最近错误</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!items.length">
              <td colspan="8" class="empty">暂无可展示通道</td>
            </tr>
            <tr v-for="item in items" :key="item.id">
              <td>
                <div style="display:grid;gap:4px">
                  <div style="font-weight:600">{{ item.name }}</div>
                  <div style="display:flex;flex-wrap:wrap;gap:6px">
                    <span class="tag">{{ item.source === 'env_fallback' ? 'ENV' : 'DB' }}</span>
                    <span v-if="item.supports_web_search" class="tag search-tag">Web Search</span>
                  </div>
                  <div v-if="probeResults[item.id]" class="probe-line">
                    最近测试: {{ probeResults[item.id].content }} · {{ Math.round(probeResults[item.id].latency_ms || 0) }} ms
                  </div>
                </div>
              </td>
              <td><span class="tag">{{ item.provider_type }}</span></td>
              <td style="font-family:var(--mono);font-size:12px">{{ item.model }}</td>
              <td class="mono-cell" :title="item.base_url">{{ item.base_url }}</td>
              <td style="font-family:var(--mono)">{{ item.priority }}</td>
              <td>
                <div class="status-stack">
                  <span :class="['status-pill', item.enabled ? 'online' : 'offline']">{{ item.enabled ? '启用' : '禁用' }}</span>
                  <span v-if="item.manual_pause" class="status-pill paused">已暂停</span>
                  <span v-if="item.quota_exhausted" class="status-pill exhausted">额度耗尽</span>
                </div>
              </td>
              <td class="error-cell" :title="item.last_error || '—'">{{ item.last_error || '—' }}</td>
              <td>
                <div class="action-wrap">
                  <button
                    class="btn btn-sm btn-outline"
                    :disabled="testingChannelId === item.id"
                    @click="testExistingChannel(item)"
                  >
                    {{ testingChannelId === item.id ? '测试中...' : '测试' }}
                  </button>
                  <button class="btn btn-sm btn-outline" @click="viewEvents(item)">事件</button>
                  <button
                    v-if="!item.readonly"
                    class="btn btn-sm btn-outline"
                    @click="openEdit(item)"
                  >
                    编辑
                  </button>
                  <button
                    v-if="!item.readonly && !item.manual_pause"
                    class="btn btn-sm btn-outline"
                    @click="pauseChannel(item)"
                  >
                    暂停
                  </button>
                  <button
                    v-if="!item.readonly && item.manual_pause"
                    class="btn btn-sm btn-green"
                    @click="resumeChannel(item)"
                  >
                    恢复
                  </button>
                  <button
                    v-if="!item.readonly && !item.quota_exhausted"
                    class="btn btn-sm btn-danger"
                    @click="markQuota(item)"
                  >
                    标记耗尽
                  </button>
                  <button
                    v-if="!item.readonly && item.quota_exhausted"
                    class="btn btn-sm btn-green"
                    @click="clearQuota(item)"
                  >
                    清除耗尽
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showForm" class="modal-overlay" @click.self="closeForm">
      <div class="modal" style="width:760px">
        <div class="modal-header">
          <span>{{ editingId ? '编辑 AI 通道' : '新增 AI 通道' }}</span>
          <button class="close-btn" @click="closeForm">×</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">名称</label>
              <input v-model="form.name" class="input" placeholder="如：midtransit-primary" />
            </div>
            <div class="form-group">
              <label class="form-label">协议类型</label>
              <select v-model="form.provider_type" class="select">
                <option value="openai_compatible">openai_compatible</option>
                <option value="volcengine_search">volcengine_search</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Model</label>
              <input v-model="form.model" class="input" placeholder="如：gpt-4.1-mini" />
            </div>
            <div class="form-group">
              <label class="form-label">Priority</label>
              <input v-model.number="form.priority" type="number" min="1" class="input" />
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Base URL</label>
            <input v-model="form.base_url" class="input" placeholder="https://example.com/v1" />
          </div>

          <div class="form-group">
            <label class="form-label">API Key</label>
            <input
              v-model="form.api_key"
              class="input"
              type="password"
              :placeholder="editingId ? '留空则保持当前密钥不变' : 'sk-...'"
            />
          </div>

          <div class="form-row">
            <label class="toggle-line">
              <input v-model="form.enabled" type="checkbox" />
              <span>启用此通道</span>
            </label>
            <label class="toggle-line">
              <input v-model="form.supports_web_search" type="checkbox" />
              <span>支持联网搜索</span>
            </label>
          </div>

          <div v-if="testResult" class="test-result">
            <div class="form-label">连通性测试</div>
            <div class="test-box">
              <div><span class="tag">{{ testResult.model }}</span> <span style="color:var(--text2)">延迟 {{ Math.round(testResult.latency_ms || 0) }} ms</span></div>
              <div style="margin-top:8px;color:var(--text2)">{{ testResult.content }}</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="closeForm">取消</button>
          <button class="btn btn-outline" :disabled="testing" @click="testChannel">
            {{ testing ? '测试中...' : '测试通道' }}
          </button>
          <button class="btn btn-primary" :disabled="saving" @click="saveChannel">
            {{ saving ? '保存中...' : '保存通道' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="eventModal" class="modal-overlay" @click.self="eventModal = null">
      <div class="modal" style="width:820px">
        <div class="modal-header">
          <span>通道事件 · {{ eventModal.name }}</span>
          <button class="close-btn" @click="eventModal = null">×</button>
        </div>
        <div class="modal-body">
          <div v-if="eventLoading" class="loading">加载中...</div>
          <div v-else-if="!events.length" class="empty">暂无事件</div>
          <div v-else style="display:grid;gap:10px">
            <div v-for="evt in events" :key="evt.id" class="event-card">
              <div class="event-meta">
                <span>{{ evt.event_type }}</span>
                <span>{{ (evt.created_at || '').replace('T', ' ').slice(0, 19) }}</span>
              </div>
              <div style="color:var(--text2)">{{ evt.message || '—' }}</div>
              <pre v-if="evt.raw_error" class="event-error">{{ evt.raw_error }}</pre>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="eventModal = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { llmChannelsApi } from '@/api'

const toast = inject('toast')
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const testingChannelId = ref('')
const showForm = ref(false)
const editingId = ref('')
const eventModal = ref(null)
const eventLoading = ref(false)
const testResult = ref(null)
const items = ref([])
const events = ref([])
const probeResults = ref({})

const form = reactive({
  name: '',
  provider_type: 'openai_compatible',
  base_url: '',
  api_key: '',
  model: '',
  priority: 100,
  enabled: true,
  supports_web_search: false,
})

const stats = computed(() => ({
  available: items.value.filter(item => item.enabled && !item.manual_pause && !item.quota_exhausted).length,
  exhausted: items.value.filter(item => item.quota_exhausted).length,
}))

const usingFallback = computed(() => items.value.length > 0 && items.value.every(item => item.source === 'env_fallback'))

function resetForm() {
  form.name = ''
  form.provider_type = 'openai_compatible'
  form.base_url = ''
  form.api_key = ''
  form.model = ''
  form.priority = 100
  form.enabled = true
  form.supports_web_search = false
  editingId.value = ''
  testResult.value = null
}

function openCreate() {
  resetForm()
  showForm.value = true
}

function openEdit(item) {
  resetForm()
  editingId.value = item.id
  form.name = item.name
  form.provider_type = item.provider_type
  form.base_url = item.base_url
  form.model = item.model
  form.priority = item.priority
  form.enabled = item.enabled
  form.supports_web_search = item.supports_web_search
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  resetForm()
}

async function loadChannels() {
  loading.value = true
  try {
    const data = await llmChannelsApi.list()
    items.value = data.items || []
  } catch (e) {
    toast(String(e), 'error')
  }
  loading.value = false
}

function validateForm(requireKey = false) {
  if (!form.name || !form.base_url || !form.model) {
    toast('请完整填写名称、Base URL 和模型', 'error')
    return false
  }
  if (requireKey && !form.api_key) {
    toast('请填写 API Key', 'error')
    return false
  }
  return true
}

function buildPayload(requireKey = false) {
  if (!validateForm(requireKey)) return null
  return {
    name: form.name.trim(),
    provider_type: form.provider_type,
    base_url: form.base_url.trim(),
    api_key: form.api_key,
    model: form.model.trim(),
    priority: Number(form.priority || 100),
    enabled: !!form.enabled,
    supports_web_search: !!form.supports_web_search,
  }
}

async function saveChannel() {
  const payload = buildPayload(!editingId.value)
  if (!payload) return
  saving.value = true
  try {
    if (editingId.value) {
      await llmChannelsApi.update(editingId.value, payload)
      toast('通道已更新')
    } else {
      await llmChannelsApi.create(payload)
      toast('通道已创建')
    }
    closeForm()
    await loadChannels()
  } catch (e) {
    toast(String(e), 'error')
  }
  saving.value = false
}

async function testChannel() {
  const payload = buildPayload(!editingId.value)
  if (!payload) return
  testing.value = true
  try {
    testResult.value = await llmChannelsApi.test(payload)
    toast('连通性测试成功')
  } catch (e) {
    toast(String(e), 'error')
  }
  testing.value = false
}

async function testExistingChannel(item) {
  testingChannelId.value = item.id
  try {
    const result = await llmChannelsApi.testById(item.id)
    probeResults.value = {
      ...probeResults.value,
      [item.id]: result,
    }
    toast(`测试成功：${result.content} · ${Math.round(result.latency_ms || 0)}ms`)
  } catch (e) {
    toast(String(e), 'error')
  }
  testingChannelId.value = ''
}

async function pauseChannel(item) {
  try {
    await llmChannelsApi.pause(item.id)
    toast('已暂停通道')
    await loadChannels()
  } catch (e) {
    toast(String(e), 'error')
  }
}

async function resumeChannel(item) {
  try {
    await llmChannelsApi.resume(item.id)
    toast('已恢复通道')
    await loadChannels()
  } catch (e) {
    toast(String(e), 'error')
  }
}

async function markQuota(item) {
  try {
    await llmChannelsApi.markQuotaExhausted(item.id)
    toast('已标记为额度耗尽')
    await loadChannels()
  } catch (e) {
    toast(String(e), 'error')
  }
}

async function clearQuota(item) {
  try {
    await llmChannelsApi.clearQuotaExhausted(item.id)
    toast('已清除额度耗尽状态')
    await loadChannels()
  } catch (e) {
    toast(String(e), 'error')
  }
}

async function viewEvents(item) {
  eventModal.value = item
  eventLoading.value = true
  try {
    const data = await llmChannelsApi.events(item.id, { limit: 50 })
    events.value = data.items || []
  } catch (e) {
    toast(String(e), 'error')
    events.value = []
  }
  eventLoading.value = false
}

onMounted(loadChannels)
</script>

<style scoped>
.channel-hero {
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(255,208,96,.16), transparent 22%),
    radial-gradient(circle at right center, rgba(0,204,255,.16), transparent 30%),
    linear-gradient(135deg, rgba(255,255,255,.03), rgba(255,255,255,.01)),
    var(--bg2);
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: stretch;
}
.channel-title { font-size: 30px; font-weight: 600; letter-spacing: .5px; }
.channel-subtitle { margin-top: 10px; max-width: 680px; color: var(--text2); }
.channel-summary { display: flex; gap: 12px; align-items: center; }
.summary-box {
  min-width: 118px;
  padding: 16px 18px;
  border-radius: 4px;
  background: rgba(255,255,255,.04);
  border: 1px solid rgba(255,255,255,.08);
}
.summary-box.warning {
  background: rgba(255,77,106,.08);
  border-color: rgba(255,77,106,.18);
}
.summary-label {
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--text3);
}
.summary-value {
  margin-top: 8px;
  font-size: 28px;
  font-family: var(--mono);
  color: var(--text);
}
.mode-tag {
  margin-left: auto;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid var(--border2);
}
.mode-db { color: var(--green); background: rgba(0,229,160,.08); }
.mode-fallback { color: var(--yellow); background: rgba(255,208,96,.08); }
.mono-cell,
.error-cell {
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--mono);
  font-size: 12px;
}
.error-cell { color: var(--text3); }
.status-stack { display: flex; flex-wrap: wrap; gap: 6px; }
.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid transparent;
}
.status-pill.online { color: var(--green); background: rgba(0,229,160,.12); }
.status-pill.offline { color: var(--text3); background: rgba(255,255,255,.04); }
.status-pill.paused { color: var(--yellow); background: rgba(255,208,96,.12); }
.status-pill.exhausted { color: var(--red); background: rgba(255,77,106,.12); }
.action-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.toggle-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  color: var(--text2);
}
.test-result { margin-top: 4px; }
.test-box {
  border: 1px solid var(--border);
  border-radius: 4px;
  background: rgba(255,255,255,.02);
  padding: 14px;
}
.event-card {
  border: 1px solid var(--border);
  border-radius: 4px;
  background: rgba(255,255,255,.02);
  padding: 14px;
}
.event-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: var(--accent);
  font-family: var(--mono);
  font-size: 11px;
}
.event-error {
  margin-top: 10px;
  white-space: pre-wrap;
  font-size: 12px;
  color: var(--text3);
  background: var(--bg3);
  border-radius: 3px;
  padding: 10px;
}
.search-tag {
  color: var(--accent);
  border-color: rgba(0,204,255,.25);
}
.probe-line {
  font-size: 11px;
  color: var(--green);
}
@media (max-width: 1100px) {
  .channel-hero {
    flex-direction: column;
  }
}
</style>
