<template>
  <div class="review-page">
    <section class="card review-hero">
      <div>
        <div class="card-title">Review Cases</div>
        <div class="review-title">真实性审核工作台</div>
        <div class="review-subtitle">
          这里直接围绕 `review_cases + evidence + decision` 工作。候选、可疑、隔离状态都在这里收口，不再混在知识库 CRUD 里。
        </div>
      </div>
      <div class="hero-stats">
        <div class="hero-chip">
          <span>总案例</span>
          <strong>{{ total }}</strong>
        </div>
        <div class="hero-chip">
          <span>suspicious</span>
          <strong>{{ summary.suspicious }}</strong>
        </div>
        <div class="hero-chip">
          <span>quarantined</span>
          <strong>{{ summary.quarantined }}</strong>
        </div>
      </div>
    </section>

    <section class="filter-bar">
      <select class="select" style="width:160px" v-model="filters.current_status" @change="load">
        <option value="">全部状态</option>
        <option value="candidate">candidate</option>
        <option value="suspicious">suspicious</option>
        <option value="quarantined">quarantined</option>
        <option value="verified">verified</option>
      </select>
      <select class="select" style="width:160px" v-model="filters.country_code" @change="load">
        <option value="">全部国家</option>
        <option v-for="c in countries" :key="c.code" :value="c.code">{{ c.name_zh }} ({{ c.code }})</option>
      </select>
      <button class="btn btn-outline" @click="load">刷新</button>
      <span style="margin-left:auto;font-size:12px;color:var(--text3)">最近按更新时间排序</span>
    </section>

    <section class="review-grid">
      <div class="card cases-card">
        <div class="panel-head">
          <div class="card-title">待处理案例</div>
          <div class="panel-caption">优先看高风险和证据不足的项</div>
        </div>
        <div v-if="loading" class="loading">加载中...</div>
        <div v-else-if="!items.length" class="empty">暂无审核案例</div>
        <div v-else class="case-list">
          <button
            v-for="item in items"
            :key="item.id"
            class="case-row"
            :class="{ active: selectedCase?.id === item.id }"
            @click="selectCase(item)"
          >
            <div class="case-row-head">
              <span class="case-title">{{ item.title || item.compliance_id }}</span>
              <span class="case-status" :class="item.current_status">{{ item.current_status }}</span>
            </div>
            <div class="case-row-meta">
              <span>{{ item.country_code || '—' }}</span>
              <span>{{ item.entry_type || '—' }}</span>
              <span>风险 {{ item.risk_score ?? 0 }}</span>
            </div>
            <div class="case-row-note">{{ item.evidence_note || '暂无人工证据备注' }}</div>
          </button>
        </div>
      </div>

      <div class="card detail-card">
        <div class="panel-head">
          <div class="card-title">案例详情</div>
          <div class="panel-caption">证据、事件、处理动作</div>
        </div>

        <div v-if="!selectedCase" class="empty detail-empty">
          选择左侧一条 review case 开始处理。
        </div>

        <template v-else>
          <div class="detail-header">
            <div>
              <div class="detail-title">{{ detailRecord?.name || selectedCase.title || selectedCase.compliance_id }}</div>
              <div class="detail-subtitle">{{ detailRecord?.issuing_body || '未记录发布机构' }}</div>
            </div>
            <span class="case-status large" :class="selectedCase.current_status">{{ selectedCase.current_status }}</span>
          </div>

          <div class="summary-grid">
            <div class="summary-card">
              <div class="summary-label">风险分</div>
              <div class="summary-value" :class="riskClass(selectedCase.risk_score)">{{ selectedCase.risk_score ?? 0 }}</div>
            </div>
            <div class="summary-card">
              <div class="summary-label">证据工件</div>
              <div class="summary-value">{{ evidence.artifacts.length }}</div>
            </div>
            <div class="summary-card">
              <div class="summary-label">审核事件</div>
              <div class="summary-value">{{ evidence.events.length }}</div>
            </div>
            <div class="summary-card">
              <div class="summary-label">原文抓取</div>
              <div class="summary-value small">{{ selectedCase.source_download_status || '—' }}</div>
            </div>
          </div>

          <div class="detail-section">
            <div class="section-title">人工证据备注</div>
            <div class="section-copy">{{ selectedCase.evidence_note || '暂无人工证据备注。' }}</div>
            <div v-if="selectedCase.reasons?.length" class="reason-list">
              <span v-for="reason in selectedCase.reasons" :key="reason" class="tag">{{ reason }}</span>
            </div>
          </div>

          <div class="detail-section">
            <div class="section-title">证据工件</div>
            <div v-if="!evidence.artifacts.length" class="desk-empty">暂无挂载工件。</div>
            <div v-else class="artifact-list">
              <div v-for="artifact in evidence.artifacts" :key="artifact.id" class="artifact-card">
                <div class="artifact-meta">
                  <span>{{ artifact.artifact_type || 'artifact' }}</span>
                  <span>{{ artifact.download_status || 'pending' }}</span>
                </div>
                <a v-if="artifact.official_url" :href="artifact.official_url" target="_blank" class="artifact-link">{{ artifact.official_url }}</a>
                <a v-if="artifact.artifact_url" :href="artifact.artifact_url" target="_blank" class="artifact-link artifact-link-secondary">{{ artifact.artifact_url }}</a>
                <div v-if="artifact.download_error" class="artifact-error">{{ artifact.download_error }}</div>
              </div>
            </div>
          </div>

          <div class="detail-section">
            <div class="section-title">最近审核事件</div>
            <div v-if="!evidence.events.length" class="desk-empty">暂无审核事件。</div>
            <div v-else class="event-list">
              <div v-for="event in evidence.events.slice(0, 8)" :key="event.id" class="event-card">
                <div class="event-head">
                  <span>{{ event.event_type }}</span>
                  <span>{{ event.created_at }}</span>
                </div>
                <div class="event-flow">{{ event.from_status || '—' }} → {{ event.to_status || '—' }}</div>
              </div>
            </div>
          </div>

          <div class="action-bar">
            <button class="btn btn-outline" @click="openResearch">去问答</button>
            <button class="btn btn-outline" @click="openKnowledge">查看知识详情</button>
            <button class="btn btn-outline" style="color:var(--yellow);border-color:rgba(255,208,96,.4)" @click="openManualSource">
              人工补源
            </button>
            <button class="btn btn-outline" @click="runAiAssist" :disabled="aiAssistLoading">
              {{ aiAssistLoading ? 'AI 分析中...' : 'AI 辅助分析' }}
            </button>
            <button class="btn btn-outline" @click="prefillDecision('suspicious')">标可疑</button>
            <button class="btn btn-danger" @click="prefillDecision('quarantined')">隔离</button>
          </div>

          <div class="detail-section" v-if="aiAssist">
            <div class="section-title">AI 辅助分析</div>
            <div class="artifact-card">
              <div class="artifact-meta">
                <span>{{ aiAssist.evidence_status || 'analysis' }}</span>
                <span>AI 仅辅助，不拍板</span>
              </div>
              <div class="section-copy">{{ aiAssist.summary }}</div>
              <div v-if="aiAssist.confirmed_facts?.length" class="assist-block">
                <div class="assist-title">已确认事实</div>
                <ul class="assist-list">
                  <li v-for="fact in aiAssist.confirmed_facts" :key="fact">{{ fact }}</li>
                </ul>
              </div>
              <div v-if="aiAssist.gaps?.length" class="assist-block">
                <div class="assist-title">证据缺口</div>
                <ul class="assist-list">
                  <li v-for="gap in aiAssist.gaps" :key="gap">{{ gap }}</li>
                </ul>
              </div>
              <div v-if="aiAssist.recommended_actions?.length" class="assist-block">
                <div class="assist-title">建议动作</div>
                <ul class="assist-list">
                  <li v-for="action in aiAssist.recommended_actions" :key="action">{{ action }}</li>
                </ul>
              </div>
              <div v-if="aiAssist.warning" class="artifact-error">{{ aiAssist.warning }}</div>
            </div>
          </div>

          <div class="decision-box">
            <div class="section-title">写回审核结论</div>
            <div class="decision-grid">
              <div class="form-group">
                <label class="form-label">结论</label>
                <select class="select" v-model="decision.authenticity_status">
                  <option value="suspicious">suspicious</option>
                  <option value="quarantined">quarantined</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">风险分</label>
                <input class="input" type="number" min="0" max="100" v-model.number="decision.risk_score" />
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">原因列表（每行一个）</label>
              <textarea class="textarea" rows="4" v-model="decision.reasonsText" />
            </div>
            <div class="form-group">
              <label class="form-label">证据备注</label>
              <textarea class="textarea" rows="4" v-model="decision.evidence_note" />
            </div>
            <div class="decision-grid">
              <div class="form-group">
                <label class="form-label">原文抓取状态</label>
                <select class="select" v-model="decision.source_download_status">
                  <option value="">不改</option>
                  <option value="pending">pending</option>
                  <option value="downloaded">downloaded</option>
                  <option value="failed">failed</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">抓取错误</label>
                <input class="input" v-model="decision.source_download_error" />
              </div>
            </div>
            <div class="action-bar" style="margin-top:12px">
              <button class="btn btn-primary" :disabled="saving" @click="submitDecision">
                {{ saving ? '写回中...' : '确认写回' }}
              </button>
            </div>
          </div>
        </template>
      </div>
    </section>

    <div v-if="showManualSource && detailRecord" class="modal-overlay" @click.self="showManualSource=false">
      <div class="modal" style="width:640px">
        <div class="modal-header">
          <span>🔗 人工补源 · {{ detailRecord.name || selectedCase?.title || selectedCase?.compliance_id }}</span>
          <button class="close-btn" @click="showManualSource=false">×</button>
        </div>
        <div class="modal-body" style="display:grid;gap:12px">
          <div class="form-group">
            <label class="form-label">官方正文页 *</label>
            <input class="input" v-model="manualSourceForm.official_url" placeholder="https://官方域名/..." />
          </div>
          <div class="form-group">
            <label class="form-label">官方 PDF / 工件链接</label>
            <input class="input" v-model="manualSourceForm.artifact_url" placeholder="可选，优先填官方 PDF" />
          </div>
          <div class="form-group">
            <label class="form-label">证据备注 *</label>
            <textarea
              class="textarea"
              rows="4"
              v-model="manualSourceForm.evidence_note"
              placeholder="如：2026-04-22 人工联网确认该链接为官方正文页，并与条目名称、主管机构和正文内容逐项比对一致。"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="showManualSource=false">取消</button>
          <button class="btn btn-primary" :disabled="manualSourceSaving" @click="submitManualSource">
            {{ manualSourceSaving ? '提交中...' : '确认补源并核实' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { complianceApi, reviewCasesApi } from '@/api'

const toast = inject('toast')
const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const total = ref(0)
const countries = ref([])
const selectedCase = ref(null)
const detailRecord = ref(null)
const evidence = reactive({ artifacts: [], events: [] })
const filters = reactive({ current_status: 'suspicious', country_code: '' })
const decision = reactive(defaultDecision())
const showManualSource = ref(false)
const manualSourceSaving = ref(false)
const aiAssist = ref(null)
const aiAssistLoading = ref(false)
const manualSourceForm = reactive({
  official_url: '',
  artifact_url: '',
  evidence_note: '',
})

function defaultDecision() {
  return {
    authenticity_status: 'suspicious',
    risk_score: 70,
    reasonsText: '',
    evidence_note: '',
    source_download_status: 'failed',
    source_download_error: '',
  }
}

const summary = computed(() => {
  return items.value.reduce((acc, item) => {
    acc[item.current_status] = (acc[item.current_status] || 0) + 1
    return acc
  }, { suspicious: 0, quarantined: 0, verified: 0, candidate: 0 })
})

function riskClass(score = 0) {
  if (score >= 80) return 'risk-high'
  if (score >= 40) return 'risk-mid'
  return 'risk-low'
}

async function loadMeta() {
  try {
    const meta = await complianceApi.meta()
    countries.value = meta.countries || []
  } catch (e) {
    toast(String(e), 'error')
  }
}

async function load() {
  loading.value = true
  try {
    const data = await reviewCasesApi.list({
      current_status: filters.current_status || null,
      country_code: filters.country_code || null,
      limit: 200,
    })
    items.value = data.items || []
    total.value = data.total || items.value.length
    if (items.value.length && !selectedCase.value) {
      await selectCase(items.value[0])
    } else if (!items.value.length) {
      selectedCase.value = null
      detailRecord.value = null
      evidence.artifacts = []
      evidence.events = []
    }
  } catch (e) {
    toast(String(e), 'error')
  } finally {
    loading.value = false
  }
}

async function selectCase(item) {
  selectedCase.value = item
  aiAssist.value = null
  decision.authenticity_status = item.current_status === 'quarantined' ? 'quarantined' : 'suspicious'
  decision.risk_score = item.risk_score ?? 70
  decision.reasonsText = Array.isArray(item.reasons) ? item.reasons.join('\n') : ''
  decision.evidence_note = item.evidence_note || ''
  decision.source_download_status = item.source_download_status || 'failed'
  decision.source_download_error = item.source_download_error || ''
  try {
    const [detail, evidencePayload] = await Promise.all([
      complianceApi.get(item.compliance_id),
      complianceApi.evidence(item.compliance_id),
    ])
    detailRecord.value = detail
    evidence.artifacts = evidencePayload.artifacts || []
    evidence.events = evidencePayload.events || []
  } catch (e) {
    toast(String(e), 'error')
  }
}

function prefillDecision(status) {
  decision.authenticity_status = status
  decision.risk_score = status === 'quarantined' ? 95 : 70
}

function openManualSource() {
  if (!detailRecord.value || !selectedCase.value) return
  showManualSource.value = true
  manualSourceForm.official_url = detailRecord.value.official_url || ''
  manualSourceForm.artifact_url = detailRecord.value.source_artifact_url || ''
  manualSourceForm.evidence_note = detailRecord.value.review_case?.evidence_note || ''
}

async function runAiAssist() {
  if (!selectedCase.value) return
  aiAssistLoading.value = true
  try {
    aiAssist.value = await reviewCasesApi.aiAssist(selectedCase.value.id)
  } catch (e) {
    toast(String(e), 'error')
  } finally {
    aiAssistLoading.value = false
  }
}

async function submitManualSource() {
  if (!selectedCase.value) return
  if (!manualSourceForm.official_url.trim() || !manualSourceForm.evidence_note.trim()) {
    toast('请填写官方正文页和证据备注', 'error')
    return
  }
  manualSourceSaving.value = true
  try {
    await complianceApi.manualSource(selectedCase.value.compliance_id, {
      official_url: manualSourceForm.official_url.trim(),
      artifact_url: manualSourceForm.artifact_url.trim() || null,
      evidence_note: manualSourceForm.evidence_note.trim(),
    })
    toast('人工补源成功，条目已通过正式证据链核实')
    showManualSource.value = false
    selectedCase.value = null
    detailRecord.value = null
    evidence.artifacts = []
    evidence.events = []
    await load()
  } catch (e) {
    toast(String(e), 'error')
  } finally {
    manualSourceSaving.value = false
  }
}

async function submitDecision() {
  if (!selectedCase.value) return
  const reasons = decision.reasonsText.split('\n').map((x) => x.trim()).filter(Boolean)
  if (!reasons.length || !decision.evidence_note.trim()) {
    toast('请填写原因列表和证据备注', 'error')
    return
  }
  saving.value = true
  try {
    await reviewCasesApi.decide(selectedCase.value.id, {
      authenticity_status: decision.authenticity_status,
      risk_score: decision.risk_score,
      reasons,
      evidence_note: decision.evidence_note,
      source_download_status: decision.source_download_status || null,
      source_download_error: decision.source_download_error || null,
    })
    toast('审核结论已写回')
    selectedCase.value = null
    await load()
  } catch (e) {
    toast(String(e), 'error')
  } finally {
    saving.value = false
  }
}

function openResearch() {
  if (!detailRecord.value) return
  router.push({
    path: '/research',
    query: {
      country: detailRecord.value.country_code || '',
      question: `${detailRecord.value.name} 的真实性证据和核心要求是什么？`,
      document: detailRecord.value.source_document_id || detailRecord.value.document_id || '',
    },
  })
}

function openKnowledge() {
  router.push('/knowledge')
}

onMounted(async () => {
  await loadMeta()
  await load()
})
</script>

<style scoped>
.review-page { display:grid; gap:20px; }
.review-hero {
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:16px;
  background:
    radial-gradient(circle at top right, rgba(255,77,106,.12), transparent 24%),
    radial-gradient(circle at bottom left, rgba(255,208,96,.12), transparent 28%),
    linear-gradient(135deg, rgba(255,255,255,.03), rgba(255,255,255,0)),
    var(--bg2);
}
.review-title { font-size:30px; font-weight:600; letter-spacing:.4px; }
.review-subtitle { margin-top:8px; max-width:760px; color:var(--text2); line-height:1.8; }
.hero-stats { display:flex; gap:10px; flex-wrap:wrap; justify-content:flex-end; }
.hero-chip {
  min-width:100px;
  padding:10px 12px;
  border:1px solid var(--border);
  border-radius:4px;
  background:rgba(255,255,255,.03);
  display:grid;
  gap:4px;
}
.hero-chip span { color:var(--text3); font-size:11px; text-transform:uppercase; letter-spacing:1px; }
.hero-chip strong { font-size:22px; font-family:var(--mono); }
.review-grid { display:grid; grid-template-columns: 360px minmax(0,1fr); gap:16px; align-items:start; }
.panel-head { display:grid; gap:6px; margin-bottom:14px; }
.panel-caption { color:var(--text3); font-size:12px; }
.cases-card, .detail-card { min-height:760px; }
.case-list { display:grid; gap:10px; }
.case-row {
  width:100%;
  text-align:left;
  border:1px solid var(--border);
  background:rgba(255,255,255,.02);
  border-radius:4px;
  padding:14px;
  display:grid;
  gap:8px;
  cursor:pointer;
  transition:all .15s;
}
.case-row:hover, .case-row.active { border-color:var(--accent); background:rgba(0,204,255,.05); }
.case-row-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
.case-title { font-size:13px; font-weight:600; line-height:1.6; }
.case-status {
  padding:4px 8px;
  border-radius:999px;
  font-size:11px;
  text-transform:uppercase;
  font-family:var(--mono);
}
.case-status.suspicious { background:rgba(255,208,96,.12); color:var(--yellow); }
.case-status.quarantined { background:rgba(255,77,106,.12); color:var(--red); }
.case-status.verified { background:rgba(0,229,160,.12); color:var(--green); }
.case-status.candidate { background:rgba(255,255,255,.06); color:var(--text2); }
.case-status.large { width:fit-content; }
.case-row-meta { display:flex; flex-wrap:wrap; gap:10px; color:var(--text3); font-size:11px; }
.case-row-note { color:var(--text2); font-size:12px; line-height:1.7; }
.detail-empty { min-height:620px; display:flex; align-items:center; justify-content:center; }
.detail-header { display:flex; justify-content:space-between; gap:16px; margin-bottom:14px; }
.detail-title { font-size:20px; font-weight:600; line-height:1.5; }
.detail-subtitle { color:var(--text3); margin-top:4px; }
.summary-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:16px; }
.summary-card {
  padding:12px;
  border:1px solid var(--border);
  border-radius:4px;
  background:rgba(255,255,255,.02);
  display:grid;
  gap:6px;
}
.summary-label { color:var(--text3); font-size:11px; text-transform:uppercase; letter-spacing:1px; }
.summary-value { font-size:22px; font-family:var(--mono); color:var(--accent); }
.summary-value.small { font-size:14px; font-family:inherit; color:var(--text2); }
.risk-high { color:var(--red); }
.risk-mid { color:var(--yellow); }
.risk-low { color:var(--green); }
.detail-section { margin-bottom:16px; }
.section-title { color:var(--text3); font-size:11px; text-transform:uppercase; letter-spacing:1px; margin-bottom:8px; }
.section-copy { color:var(--text2); line-height:1.8; }
.reason-list { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
.artifact-list, .event-list { display:grid; gap:10px; }
.artifact-card, .event-card {
  padding:12px;
  border:1px solid var(--border);
  border-radius:4px;
  background:rgba(255,255,255,.02);
  display:grid;
  gap:6px;
}
.artifact-meta, .event-head { display:flex; justify-content:space-between; gap:12px; font-size:12px; }
.artifact-meta { color:var(--accent); }
.event-head { color:var(--yellow); }
.artifact-link { color:var(--text2); word-break:break-all; font-size:12px; }
.artifact-link-secondary { color:var(--accent); }
.artifact-error { color:var(--red); font-size:12px; }
.event-flow { color:var(--text3); font-size:12px; }
.action-bar { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:16px; }
.assist-block { margin-top:10px; display:grid; gap:6px; }
.assist-title { font-size:12px; color:var(--text3); }
.assist-list { margin:0; padding-left:18px; color:var(--text2); line-height:1.7; }
.decision-box {
  margin-top:12px;
  padding:14px;
  border:1px solid var(--border);
  border-radius:4px;
  background:rgba(255,255,255,.02);
}
.decision-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
</style>
