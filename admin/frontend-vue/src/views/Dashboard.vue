<template>
  <div class="board-shell">
    <section class="board-hero">
      <div>
        <div class="eyebrow">VERIFIED COMPLIANCE BOARD</div>
        <h2>全球网络安全法规认证看板</h2>
        <p>只展示官方证据闭环的已核验数据。生效预警按当前日期实时计算，可在 30 / 90 / 180 / 360 天窗口内筛选。</p>
      </div>
      <div class="hero-panel">
        <span class="pulse"></span>
        <div>
          <strong>{{ rangeDays }} 天窗口</strong>
          <small>{{ upcoming.length }} 条即将生效</small>
        </div>
      </div>
    </section>

    <section class="metric-grid">
      <div class="metric-card" v-for="card in statCards" :key="card.label">
        <span>{{ card.label }}</span>
        <strong :style="{ color: card.color }">{{ card.value }}</strong>
        <small>{{ card.sub }}</small>
      </div>
    </section>

    <section class="workflow-card card">
      <div class="workflow-head">
        <div>
          <div class="card-title">证据驱动主流程</div>
          <p>{{ workflow.principle || '只让官方证据闭环进入已核验状态。' }}</p>
        </div>
        <span class="feedback-pill">周报异常回流核验</span>
      </div>
      <div class="workflow-track">
        <div v-for="(stage, idx) in workflowStages" :key="stage.key" class="workflow-node">
          <div :class="['node-card', `health-${stage.health}`]">
            <span class="node-index">{{ String(idx + 1).padStart(2, '0') }}</span>
            <strong>{{ stage.title }}</strong>
            <small>{{ stage.subtitle }}</small>
            <div class="node-primary">
              <b>{{ stage.primary_value }}</b>
              <span>{{ stage.primary_label }}</span>
            </div>
            <div class="node-metrics">
              <span v-for="metric in stage.metrics" :key="metric.label">
                {{ metric.label }} <b>{{ metric.value }}</b>
              </span>
            </div>
          </div>
          <i v-if="idx < workflowStages.length - 1" class="flow-arrow">→</i>
        </div>
      </div>
      <div class="workflow-feedback">{{ workflow.feedback }}</div>
    </section>

    <section class="control-deck">
      <div class="range-tabs">
        <button
          v-for="d in rangeOptions"
          :key="d"
          :class="{ active: rangeDays === d }"
          @click="setRange(d)"
        >
          {{ d }}天
        </button>
      </div>

      <div class="filter-lane">
        <input class="input" v-model="filters.keyword" placeholder="搜索法规/认证名称..." @input="debouncedReload" />
        <select class="select" v-model="filters.country_code" @change="reloadUpcoming">
          <option value="">全部国家</option>
          <option v-for="c in meta.countries" :key="c.code" :value="c.code">{{ c.name_zh }} ({{ c.code }})</option>
        </select>
        <select class="select" v-model="filters.entry_type" @change="reloadUpcoming">
          <option value="">全部类型</option>
          <option value="regulation">法规</option>
          <option value="certification">认证</option>
          <option value="standard">标准</option>
        </select>
        <select class="select" v-model="filters.mandatory" @change="reloadUpcoming">
          <option value="">强制/自愿</option>
          <option value="mandatory">强制</option>
          <option value="voluntary">自愿</option>
          <option value="recommended">推荐</option>
        </select>
        <select class="select" v-model="filters.product_code" @change="reloadUpcoming">
          <option value="">全部产品</option>
          <option v-for="p in meta.products" :key="p.code" :value="p.code">{{ p.name_zh }}</option>
        </select>
        <button class="btn btn-outline" @click="resetFilters">重置</button>
      </div>
    </section>

    <section class="board-grid">
      <div class="card board-table">
        <div class="table-head">
          <div>
            <div class="card-title">生效预警 · {{ rangeDays }}天内</div>
            <p>所有倒计时均由服务端按 `CURRENT_DATE` 计算，避免前端时区造成误差。</p>
          </div>
          <button class="btn btn-primary" @click="downloadVerifiedExcel">导出已核验 Excel</button>
        </div>

        <div v-if="loading" class="loading">正在加载已核验看板数据...</div>
        <div v-else-if="!upcoming.length" class="empty-state">
          <strong>当前窗口暂无即将生效条目</strong>
          <span>可以切到更长窗口，或放宽国家/产品/类型筛选。</span>
        </div>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>法规/认证</th>
                <th>国家</th>
                <th>类型</th>
                <th>强制性</th>
                <th>生效日期</th>
                <th>倒计时</th>
                <th>产品</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in upcoming" :key="item.id">
                <td class="name-cell">
                  <strong :title="item.name">{{ item.name }}</strong>
                  <small>{{ item.summary || '已核验官方证据记录' }}</small>
                </td>
                <td>
                  <span class="tag">{{ item.country_name || item.country_code }}</span>
                  <em>{{ item.country_code }}</em>
                </td>
                <td><span :class="['badge', `badge-${item.entry_type}`]">{{ typeLabel[item.entry_type] || item.entry_type }}</span></td>
                <td><span :class="['badge', `badge-${item.mandatory}`]">{{ mandatoryLabel[item.mandatory] || item.mandatory }}</span></td>
                <td class="mono">{{ item.effective_date || '—' }}</td>
                <td>
                  <span :class="['countdown', countdownClass(item.days_until_effective)]">
                    {{ formatCountdown(item.days_until_effective) }}
                  </span>
                </td>
                <td class="products">
                  <span v-for="p in (item.applicable_products || []).slice(0, 3)" :key="p" class="tag">{{ p }}</span>
                  <span v-if="(item.applicable_products || []).length > 3" class="tag">+{{ item.applicable_products.length - 3 }}</span>
                </td>
                <td>
                  <a v-if="item.official_url" :href="item.official_url" target="_blank" class="source-link">官方源</a>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <aside class="insight-rail">
        <div class="card mini-chart">
          <div class="card-title">类型分布</div>
          <div v-for="row in typeRows" :key="row.label" class="bar-row">
            <span>{{ row.label }}</span>
            <div><i :style="{ width: row.width + '%', background: row.color }"></i></div>
            <b>{{ row.value }}</b>
          </div>
        </div>

        <div class="card mini-chart">
          <div class="card-title">强制性</div>
          <div v-for="row in mandatoryRows" :key="row.label" class="bar-row">
            <span>{{ row.label }}</span>
            <div><i :style="{ width: row.width + '%', background: row.color }"></i></div>
            <b>{{ row.value }}</b>
          </div>
        </div>

        <div class="card recent-card">
          <div class="card-title">最近已核验变更</div>
          <div v-if="!recentChanges.length" class="muted">暂无变更</div>
          <div v-for="c in recentChanges.slice(0, 6)" :key="c.id" class="recent-item">
            <span :class="['change-dot', c.change_type]"></span>
            <div>
              <strong :title="c.name">{{ c.name }}</strong>
              <small>{{ c.country_name }} · {{ (c.changed_at || '').slice(0, 16) }}</small>
            </div>
          </div>
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { complianceApi, dashboardApi } from '@/api'

const toast = inject('toast')
const loading = ref(true)
const rangeOptions = [30, 90, 180, 360]
const rangeDays = ref(90)
const stats = ref({})
const statsFull = ref({})
const workflow = ref({ stages: [] })
const upcoming = ref([])
const recentChanges = ref([])
const meta = reactive({ countries: [], products: [] })
const filters = reactive({
  keyword: '',
  country_code: '',
  entry_type: '',
  mandatory: '',
  product_code: '',
})

let debounceTimer
const typeLabel = { regulation: '法规', certification: '认证', standard: '标准' }
const mandatoryLabel = { mandatory: '强制', voluntary: '自愿', recommended: '推荐' }

const statCards = computed(() => [
  { label: '已确认条目', value: stats.value.total_records ?? '—', sub: '仅已核验', color: 'var(--accent)' },
  { label: '覆盖国家', value: stats.value.country_count ?? '—', sub: '可筛选地区', color: 'var(--green)' },
  { label: `${rangeDays.value}天预警`, value: upcoming.value.length, sub: '生效日窗口', color: upcoming.value.length ? 'var(--yellow)' : 'var(--accent)' },
  { label: '待审核变更', value: stats.value.pending_review ?? '—', sub: '不进入导出', color: stats.value.pending_review > 0 ? 'var(--orange)' : 'var(--green)' },
])

const typeRows = computed(() => makeRows(statsFull.value.by_type || {}, {
  regulation: ['法规', 'var(--accent)'],
  certification: ['认证', 'var(--yellow)'],
  standard: ['标准', 'var(--orange)'],
}))

const mandatoryRows = computed(() => makeRows(statsFull.value.by_mandatory || {}, {
  mandatory: ['强制', 'var(--red)'],
  voluntary: ['自愿', 'var(--green)'],
  recommended: ['推荐', 'var(--yellow)'],
}))

const workflowStages = computed(() => workflow.value.stages || [])

function makeRows(source, labels) {
  const values = Object.entries(labels).map(([key, [label, color]]) => ({
    key,
    label,
    color,
    value: source[key] || 0,
  }))
  const max = Math.max(1, ...values.map(v => v.value))
  return values.map(v => ({ ...v, width: Math.max(6, Math.round((v.value / max) * 100)) }))
}

function buildUpcomingParams() {
  const params = { days: rangeDays.value, limit: 500 }
  Object.entries(filters).forEach(([key, value]) => {
    if (String(value || '').trim()) params[key] = value
  })
  return params
}

async function reloadUpcoming() {
  loading.value = true
  try {
    const data = await dashboardApi.upcoming(buildUpcomingParams())
    upcoming.value = data.items || []
  } catch (e) {
    toast(String(e), 'error')
  } finally {
    loading.value = false
  }
}

function debouncedReload() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(reloadUpcoming, 250)
}

function setRange(days) {
  rangeDays.value = days
  reloadUpcoming()
}

function resetFilters() {
  Object.keys(filters).forEach(key => { filters[key] = '' })
  reloadUpcoming()
}

function countdownClass(days) {
  if (days <= 30) return 'urgent'
  if (days <= 90) return 'watch'
  return 'calm'
}

function formatCountdown(days) {
  if (days === 0) return '今日生效'
  return `${days} 天`
}

function downloadVerifiedExcel() {
  const params = new URLSearchParams()
  if (filters.keyword) params.set('keyword', filters.keyword)
  if (filters.country_code) params.set('country_code', filters.country_code)
  if (filters.entry_type) params.set('entry_type', filters.entry_type)
  if (filters.mandatory) params.set('mandatory', filters.mandatory)
  if (filters.product_code) params.set('product_code', filters.product_code)
  params.set('status', 'active')
  const token = localStorage.getItem('token')
  fetch(`/api/compliance/export/excel?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
    .then(async (resp) => {
      if (!resp.ok) throw new Error('导出失败')
      const blob = await resp.blob()
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `verified_compliance_${new Date().toISOString().slice(0, 10)}.xlsx`
      link.click()
      URL.revokeObjectURL(link.href)
      toast('导出成功')
    })
    .catch((e) => toast(String(e.message || e), 'error'))
}

onMounted(async () => {
  try {
    const [simple, full, flowData, recent, metaData] = await Promise.all([
      dashboardApi.stats(),
      dashboardApi.statsFull(),
      dashboardApi.workflow(),
      dashboardApi.recent(),
      complianceApi.meta(),
    ])
    stats.value = simple
    statsFull.value = full
    workflow.value = flowData
    recentChanges.value = recent.items || []
    meta.countries = metaData.countries || []
    meta.products = metaData.products || []
    await reloadUpcoming()
  } catch (e) {
    toast(String(e), 'error')
    loading.value = false
  }
})
</script>

<style scoped>
.board-shell { display: grid; gap: 20px; }
.board-hero {
  position: relative; overflow: hidden;
  display: flex; justify-content: space-between; gap: 24px; align-items: stretch;
  border: 1px solid rgba(0,204,255,.18);
  border-radius: 12px; padding: 28px;
  background:
    radial-gradient(circle at 8% 20%, rgba(0,204,255,.18), transparent 28%),
    radial-gradient(circle at 84% 8%, rgba(255,208,96,.14), transparent 24%),
    linear-gradient(135deg, rgba(9,16,31,.94), rgba(16,32,49,.92));
  box-shadow: 0 20px 60px rgba(0,0,0,.24);
}
.board-hero::after {
  content: ""; position: absolute; inset: 0;
  background-image: linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px);
  background-size: 28px 28px; pointer-events: none;
}
.board-hero > * { position: relative; z-index: 1; }
.eyebrow { font-family: var(--mono); color: var(--accent); font-size: 11px; letter-spacing: 3px; margin-bottom: 10px; }
.board-hero h2 { font-size: 30px; line-height: 1.2; margin-bottom: 10px; letter-spacing: .5px; }
.board-hero p { color: var(--text2); max-width: 780px; font-size: 14px; }
.hero-panel {
  min-width: 210px; display: flex; align-items: center; gap: 12px;
  padding: 18px; border: 1px solid rgba(255,255,255,.1); border-radius: 10px;
  background: rgba(9,16,31,.52); backdrop-filter: blur(8px);
}
.hero-panel strong { display: block; font-family: var(--mono); font-size: 18px; color: var(--yellow); }
.hero-panel small { color: var(--text2); }
.pulse { width: 12px; height: 12px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 8px rgba(0,229,160,.12); }

.metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.metric-card {
  padding: 18px; border: 1px solid var(--border); border-radius: 10px;
  background: linear-gradient(180deg, rgba(22,32,53,.9), rgba(15,24,41,.96));
}
.metric-card span { display:block; color: var(--text3); font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; }
.metric-card strong { display:block; font-size: 30px; line-height: 1.1; font-family: var(--mono); margin: 8px 0 2px; }
.metric-card small { color: var(--text3); }

.workflow-card {
  position: relative;
  overflow: hidden;
  padding: 18px;
  border-radius: 12px;
  background:
    linear-gradient(90deg, rgba(0,204,255,.08), transparent 42%),
    linear-gradient(180deg, rgba(22,32,53,.92), rgba(10,18,32,.98));
}
.workflow-card::before {
  content: ""; position: absolute; inset: 16px;
  border: 1px solid rgba(255,255,255,.04); border-radius: 10px;
  pointer-events: none;
}
.workflow-head {
  position: relative; z-index: 1;
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
  margin-bottom: 16px;
}
.workflow-head p { color: var(--text3); font-size: 12px; margin-top: 4px; max-width: 820px; }
.feedback-pill {
  border: 1px solid rgba(255,208,96,.28); color: var(--yellow);
  border-radius: 999px; padding: 8px 12px; font-size: 12px;
  background: rgba(255,208,96,.08); white-space: nowrap;
}
.workflow-track {
  position: relative; z-index: 1;
  display: grid; grid-template-columns: repeat(6, minmax(130px, 1fr)); gap: 10px;
  align-items: stretch;
}
.workflow-node { position: relative; display: flex; min-width: 0; }
.node-card {
  width: 100%; min-height: 182px;
  display: flex; flex-direction: column; gap: 8px;
  border: 1px solid var(--border); border-radius: 12px; padding: 14px;
  background: rgba(8,15,28,.7);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04);
}
.node-card.health-ready { border-color: rgba(0,229,160,.24); }
.node-card.health-attention { border-color: rgba(255,208,96,.32); box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 0 30px rgba(255,208,96,.06); }
.node-card.health-empty { opacity: .74; }
.node-index { font-family: var(--mono); color: var(--accent); font-size: 11px; letter-spacing: 1px; }
.node-card strong { font-size: 15px; letter-spacing: .5px; }
.node-card small { min-height: 32px; color: var(--text3); line-height: 1.45; }
.node-primary { margin-top: auto; display: flex; align-items: baseline; gap: 8px; }
.node-primary b { font-family: var(--mono); color: var(--text); font-size: 26px; line-height: 1; }
.node-primary span { color: var(--text3); font-size: 11px; }
.node-metrics { display: grid; gap: 4px; padding-top: 8px; border-top: 1px solid var(--border); }
.node-metrics span { display: flex; justify-content: space-between; color: var(--text3); font-size: 11px; gap: 8px; }
.node-metrics b { color: var(--text2); font-family: var(--mono); }
.flow-arrow {
  position: absolute; right: -12px; top: 50%; transform: translateY(-50%);
  z-index: 2; color: var(--accent); font-style: normal; font-family: var(--mono);
  text-shadow: 0 0 12px rgba(0,204,255,.5);
}
.workflow-feedback {
  position: relative; z-index: 1;
  margin-top: 14px; color: var(--text3); font-size: 12px;
  border-top: 1px dashed rgba(255,255,255,.12); padding-top: 12px;
}

.control-deck {
  display: grid; gap: 12px; border: 1px solid var(--border);
  border-radius: 10px; padding: 14px; background: rgba(15,24,41,.72);
}
.range-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.range-tabs button {
  border: 1px solid var(--border2); background: rgba(255,255,255,.02);
  color: var(--text2); border-radius: 999px; padding: 8px 16px;
  font-family: var(--mono); cursor: pointer; transition: all .18s;
}
.range-tabs button:hover { color: var(--text); border-color: var(--accent); }
.range-tabs button.active { color: #001018; background: var(--accent); border-color: var(--accent); box-shadow: 0 0 24px rgba(0,204,255,.22); }
.filter-lane { display: grid; grid-template-columns: minmax(220px, 1.4fr) repeat(4, minmax(130px, 1fr)) auto; gap: 10px; }

.board-grid { display: grid; grid-template-columns: minmax(0, 1fr) 330px; gap: 20px; align-items: start; }
.board-table { padding: 0; overflow: hidden; border-radius: 10px; }
.table-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 20px; border-bottom: 1px solid var(--border); }
.table-head p { color: var(--text3); font-size: 12px; margin-top: 4px; }
.name-cell strong { display:block; max-width: 420px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size: 13px; }
.name-cell small { display:block; max-width: 520px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color: var(--text3); font-size: 11px; margin-top: 2px; }
td em { display:block; color: var(--text3); font-style: normal; font-size: 11px; margin-top: 2px; }
.mono { font-family: var(--mono); white-space: nowrap; }
.products { min-width: 170px; }
.source-link { color: var(--accent); text-decoration: none; font-size: 12px; }
.source-link:hover { text-decoration: underline; }
.muted { color: var(--text3); font-size: 12px; }
.countdown { font-family: var(--mono); font-weight: 700; white-space: nowrap; }
.countdown.urgent { color: var(--red); }
.countdown.watch { color: var(--yellow); }
.countdown.calm { color: var(--green); }
.empty-state { padding: 58px 20px; display: grid; justify-items: center; gap: 8px; color: var(--text3); }
.empty-state strong { color: var(--text); font-size: 16px; }

.insight-rail { display: grid; gap: 16px; }
.mini-chart, .recent-card { border-radius: 10px; }
.bar-row { display: grid; grid-template-columns: 52px 1fr 38px; align-items: center; gap: 10px; margin: 12px 0; font-size: 12px; color: var(--text2); }
.bar-row div { height: 8px; border-radius: 999px; background: var(--bg3); overflow: hidden; }
.bar-row i { display:block; height: 100%; border-radius: inherit; }
.bar-row b { font-family: var(--mono); color: var(--text); text-align: right; }
.recent-item { display:flex; gap:10px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.recent-item:last-child { border-bottom: 0; }
.recent-item strong { display:block; max-width: 240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size: 12px; }
.recent-item small { color: var(--text3); font-size: 11px; }
.change-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; background: var(--accent); flex-shrink: 0; }
.change-dot.created { background: var(--green); }
.change-dot.updated { background: var(--accent); }
.change-dot.deprecated { background: var(--red); }

@media (max-width: 1180px) {
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .workflow-track { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .flow-arrow { display: none; }
  .board-grid { grid-template-columns: 1fr; }
  .filter-lane { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .board-hero { flex-direction: column; padding: 20px; }
  .board-hero h2 { font-size: 24px; }
  .metric-grid, .workflow-track, .filter-lane { grid-template-columns: 1fr; }
  .workflow-head { flex-direction: column; }
  .table-head { align-items: flex-start; flex-direction: column; }
}
</style>
