<template>
  <div>
    <div class="grid-2" style="margin-bottom:20px">
      <div class="card">
        <div class="card-title">⚡ 手动触发任务</div>
        <div v-if="runningTask" style="background:rgba(255,208,96,.08);border:1px solid rgba(255,208,96,.2);padding:10px 14px;border-radius:3px;margin-bottom:16px;font-size:12px;color:var(--yellow)">
          ⏳ 运行中: {{ runningTask }}
        </div>
        <div style="margin-bottom:16px">
          <div style="font-size:11px;color:var(--text3);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">官方源同步范围</div>
          <div style="display:flex;gap:8px;margin-bottom:8px">
            <button v-for="p in ['P1','P2','P3']" :key="p"
              :class="['btn','btn-sm', priority===p?'btn-primary':'btn-outline']"
              @click="priority = priority===p ? '' : p">优先级 {{ p }}</button>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <button v-for="c in ['EU','US','GB','CN','JP','KR']" :key="c"
              :class="['btn','btn-sm', selectedCountries.includes(c)?'btn-primary':'btn-outline']"
              @click="toggleCountry(c)">{{ c }}</button>
          </div>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button class="btn btn-primary" :disabled="!!runningTask" @click="trigger('weekly_compliance_update')">▶ 每两周完整更新</button>
          <button class="btn btn-outline" :disabled="!!runningTask" @click="trigger('source_registry_refresh')">🌐 刷新全球源矩阵</button>
          <button class="btn btn-outline" :disabled="!!runningTask" @click="trigger('full_update')">官方源同步</button>
          <button class="btn btn-outline" :disabled="!!runningTask" @click="trigger('artifact_fetch')">📥 抓取原文</button>
          <button class="btn btn-outline" :disabled="!!runningTask" @click="trigger('candidate_verification')">✅ 候选验真</button>
          <button class="btn btn-outline" :disabled="!!runningTask" @click="trigger('document_parse')">📄 解析原文</button>
          <button class="btn btn-outline" @click="trigger('weekly_report')">📊 生成周报</button>
          <button class="btn btn-outline" @click="trigger('alert_scan')">🔔 预警扫描</button>
        </div>
      </div>
      <div class="card">
        <div class="card-title">📁 最近报告</div>
        <div v-if="!reports.length" class="empty" style="padding:20px 0">暂无报告</div>
        <div v-for="r in reports.slice(0,5)" :key="r.id"
          style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">
          <div>
            <div style="font-size:12px">{{ r.file_name || r.report_type }}</div>
            <div style="font-size:11px;color:var(--text3)">{{ (r.generated_at||'').slice(0,16) }}</div>
          </div>
          <a v-if="r.cos_url" :href="r.cos_url" target="_blank" class="btn btn-sm btn-outline">下载</a>
        </div>
      </div>
    </div>
    <div class="card" style="padding:0">
      <div style="padding:16px 20px;border-bottom:1px solid var(--border);font-size:13px;font-weight:600;color:var(--text2)">任务执行历史</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>时间</th><th>任务类型</th><th>状态</th><th>新增</th><th>更新</th><th>失败</th><th>触发方</th></tr></thead>
          <tbody>
            <tr v-if="!history.length"><td colspan="7" class="empty">暂无记录</td></tr>
            <tr v-for="h in history" :key="h.id">
              <td style="font-family:var(--mono);font-size:11px;white-space:nowrap">{{ (h.started_at||'').slice(0,16) }}</td>
              <td style="font-size:12px">{{ taskTypeLabel[h.task_type] || h.task_type }}</td>
              <td>
                <span
                  :title="h.status"
                  :style="{color: h.status==='success'?'var(--green)':h.status==='failed'?'var(--red)':'var(--yellow)',fontSize:12,fontWeight:600}"
                >
                  {{ statusLabel(h.status) }}
                </span>
              </td>
              <td style="font-family:var(--mono);font-size:12px;color:var(--green)">{{ h.created_count ?? '—' }}</td>
              <td style="font-family:var(--mono);font-size:12px;color:var(--accent)">{{ h.updated_count ?? '—' }}</td>
              <td style="font-family:var(--mono);font-size:12px;color:var(--red)">{{ h.error_count ?? '—' }}</td>
              <td style="font-size:11px;color:var(--text3)">{{ h.triggered_by }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, inject } from 'vue'
import { tasksApi } from '@/api'
import { statusLabel } from '@/utils/labels'

const toast = inject('toast')
const history = ref([])
const reports = ref([])
const runningTask = ref(null)
const priority = ref('')
const selectedCountries = ref([])
const taskTypeLabel = {
  full_update:'兼容旧入口',
  official_source_sync:'官方源同步',
  official_artifact_fetch:'官方原文抓取',
  candidate_verification:'候选规则验真',
  document_parse:'官方原文解析',
  source_registry_refresh:'全球官方源覆盖矩阵',
  incremental_check:'旧增量检查(已停用)',
  weekly_report:'周报',
  weekly_compliance_update:'每两周完整更新',
  manual:'手动'
}

function toggleCountry(c) {
  selectedCountries.value = selectedCountries.value.includes(c)
    ? selectedCountries.value.filter(x=>x!==c)
    : [...selectedCountries.value, c]
}

async function loadData() {
  try {
    const [h, r, s] = await Promise.all([tasksApi.history(), tasksApi.reports(), tasksApi.status()])
    history.value = h.items; reports.value = r.items; runningTask.value = s.running_task
  } catch(e) {}
}

async function trigger(type) {
  try {
    if (type === 'full_update') {
      await tasksApi.triggerOfficialSourceSync({ countries: selectedCountries.value.length ? selectedCountries.value : null, priority: priority.value || null })
      toast('官方源同步已启动（后台运行）')
    } else if (type === 'weekly_compliance_update') {
      await tasksApi.triggerWeeklyComplianceUpdate(); toast('每两周完整更新已启动')
    } else if (type === 'source_registry_refresh') {
      await tasksApi.triggerSourceRegistryRefresh(); toast('全球官方源覆盖矩阵刷新已启动')
    } else if (type === 'artifact_fetch') {
      await tasksApi.triggerArtifactFetch(); toast('官方原文抓取已启动')
    } else if (type === 'candidate_verification') {
      await tasksApi.triggerCandidateVerification(); toast('候选规则验真已启动')
    } else if (type === 'document_parse') {
      await tasksApi.triggerDocumentParse(); toast('官方原文解析已启动')
    } else if (type === 'weekly_report') {
      await tasksApi.triggerReport(); toast('周报生成已启动')
    } else if (type === 'alert_scan') {
      await tasksApi.triggerAlert(); toast('预警扫描已启动')
    }
    setTimeout(loadData, 1500)
  } catch(e) { toast(String(e), 'error') }
}

let timer
onMounted(() => { loadData(); timer = setInterval(() => tasksApi.status().then(s => runningTask.value = s.running_task), 5000) })
onUnmounted(() => clearInterval(timer))
</script>
