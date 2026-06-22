<template>
  <div class="agent-page">
    <section class="card agent-hero">
      <div>
        <div class="card-title">已核验本地语料</div>
        <div class="agent-title">法规问答工作台</div>
        <div class="agent-subtitle">
          后端只抓官方源、只下载官方正文页/PDF、只基于本地文档切片回答。
          当前工作台默认锁定为已核验语料，不混入候选或待复核条目。
        </div>
      </div>
      <div class="hero-badges">
        <span class="hero-badge">官方来源</span>
        <span class="hero-badge">原文工件</span>
        <span class="hero-badge">已核验检索</span>
      </div>
    </section>

    <section class="agent-grid">
      <aside class="card agent-panel left-panel">
        <div class="panel-header">
          <div class="card-title">问题编排</div>
          <div class="panel-caption">设定问题范围和证据边界</div>
        </div>

        <div class="policy-box">
          <div class="policy-label">当前约束</div>
          <div class="policy-items">
            <span class="policy-pill locked">仅已核验原文</span>
            <span class="policy-pill">禁用联网补证</span>
            <span class="policy-pill">仅本地切片回答</span>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">问题</label>
          <textarea
            class="textarea agent-textarea"
            v-model="form.question"
            placeholder="例如：CRA 对默认安全配置、漏洞处理和软件更新的要求，分别落在哪些条款？"
          />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">国家/地区</label>
            <select class="select" v-model="form.country_code">
              <option value="">不限</option>
              <option v-for="c in countries" :key="c.code" :value="c.code">{{ c.code }} - {{ c.name_zh }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">产品类型</label>
            <select class="select" v-model="form.product_code">
              <option value="">不限</option>
              <option v-for="p in products" :key="p.code" :value="p.code">{{ p.name_zh }}</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">限定文档</label>
          <select class="select" v-model="form.document_id">
            <option value="">全部已核验/可检索文档</option>
            <option v-for="doc in readyDocuments" :key="doc.id" :value="doc.id">{{ doc.name }}</option>
          </select>
          <div class="field-hint">
            只建议在你明确知道目标法规时限定单文档。其余情况保持全库检索更稳。
          </div>
        </div>

        <div class="action-row">
          <button class="btn btn-primary" :disabled="asking || !canAsk" @click="askQuestion()">
            {{ asking ? '检索中...' : '发起问答' }}
          </button>
          <button class="btn btn-outline" :disabled="asking" @click="resetConversation">清空会话</button>
        </div>

        <div class="starter-block">
          <div class="form-label">建议起手问题</div>
          <div class="starter-list">
            <button
              v-for="prompt in starterPrompts"
              :key="prompt"
              class="starter-chip"
              @click="fillPrompt(prompt)"
            >
              {{ prompt }}
            </button>
          </div>
        </div>
      </aside>

      <main class="card agent-panel center-panel">
        <div class="panel-header">
          <div class="card-title">问答会话</div>
          <div class="panel-caption">问题编排、回答和证据结论都会留在当前会话里</div>
        </div>

        <div v-if="!turns.length" class="empty-state">
          <div class="empty-kicker">证据问答</div>
          <div class="empty-title">还没有开始问答</div>
          <div class="empty-copy">
            这个工作台默认按“官方源 -> 本地文档 -> 验证条款 -> 引用回答”运作。
            你可以先问一个法规要求，也可以直接限定到某份原文文档。
          </div>
        </div>

        <div v-else class="timeline">
          <article
            v-for="turn in turns"
            :key="turn.id"
            class="turn-card"
            :class="turn.role === 'user' ? 'turn-user' : 'turn-assistant'"
          >
            <div class="turn-meta">
              <span>{{ turn.role === 'user' ? '你的问题' : '合规助手回答' }}</span>
              <span>{{ turn.createdAt }}</span>
            </div>
            <div class="turn-content">{{ turn.content }}</div>

            <template v-if="turn.role === 'assistant' && turn.result">
              <div class="turn-status-row">
                <span
                  class="answer-status"
                  :class="turn.result.status === 'answered' ? 'answered' : (turn.result.status === 'error' ? 'error' : 'insufficient')"
                >
                  {{ answerStatusText(turn.result.status) }}
                </span>
                <span class="trace-inline">
                  {{ renderTraceInline(turn.result.trace) }}
                </span>
              </div>

              <div v-if="turn.result.citations?.length" class="inline-section">
                <div class="inline-title">引用片段</div>
                <div class="citation-list">
                  <div v-for="(citation, index) in turn.result.citations" :key="index" class="citation-card">
                    <div class="citation-meta">
                      <span>{{ citation.document_name }}</span>
                      <span>{{ citationLocation(citation) }}</span>
                    </div>
                    <div class="citation-text">{{ citation.excerpt }}</div>
                  </div>
                </div>
              </div>

              <div v-if="turn.result.next_actions?.length" class="inline-section">
                <div class="inline-title">建议下一步</div>
                <div class="next-actions">
                  <span v-for="(item, index) in turn.result.next_actions" :key="index" class="next-pill">{{ item }}</span>
                </div>
              </div>
            </template>
          </article>
        </div>
      </main>

      <aside class="card agent-panel right-panel">
        <div class="panel-header">
          <div class="card-title">证据台</div>
          <div class="panel-caption">只展示最近一次回答使用的证据范围和检索轨迹</div>
        </div>

        <div class="desk-block">
          <div class="desk-title">语料边界</div>
          <div class="desk-copy">
            当前固定为 <strong>已核验本地语料</strong>。后端不会在回答阶段临时联网补法规，也不会从候选或待复核数据中找证据。
          </div>
        </div>

        <div class="desk-block">
          <div class="desk-title">最近检索轨迹</div>
          <div v-if="latestTrace" class="trace-grid">
            <div class="trace-cell">
              <span>条款结构</span>
              <strong>{{ latestTrace.retrieval_counts?.section_hits ?? 0 }}</strong>
            </div>
            <div class="trace-cell">
              <span>语义召回</span>
              <strong>{{ latestTrace.retrieval_counts?.vector_hits ?? 0 }}</strong>
            </div>
            <div class="trace-cell">
              <span>关键词召回</span>
              <strong>{{ latestTrace.retrieval_counts?.keyword_hits ?? 0 }}</strong>
            </div>
            <div class="trace-cell">
              <span>合并结果</span>
              <strong>{{ latestTrace.retrieval_counts?.merged_hits ?? 0 }}</strong>
            </div>
          </div>
          <div v-else class="desk-empty">等待第一次问答后展示。</div>
        </div>

        <div class="desk-block">
          <div class="desk-title">当前范围</div>
          <div class="scope-list">
            <div class="scope-row">
              <span>国家</span>
              <strong>{{ scopeLabel(form.country_code, countries, '全部') }}</strong>
            </div>
            <div class="scope-row">
              <span>产品</span>
              <strong>{{ scopeLabel(form.product_code, products, '全部') }}</strong>
            </div>
            <div class="scope-row">
              <span>文档</span>
              <strong>{{ selectedDocumentName }}</strong>
            </div>
          </div>
        </div>

        <div class="desk-block">
          <div class="desk-title">最近关联记录</div>
          <div v-if="latestResult?.related_records?.length" class="related-list">
            <span v-for="item in latestResult.related_records" :key="item.id" class="tag">
              {{ item.name }} · {{ item.country_code }}
            </span>
          </div>
          <div v-else class="desk-empty">暂无关联结构化记录。</div>
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, ragApi } from '@/api'
import { statusLabel } from '@/utils/labels'

const toast = inject('toast')
const route = useRoute()

const asking = ref(false)
const countries = ref([])
const products = ref([])
const readyDocuments = ref([])
const turns = ref([])
const latestResult = ref(null)
const latestTrace = ref(null)

const starterPrompts = [
  'CRA 对默认安全配置、漏洞处理和安全更新的要求分别落在哪些条款？',
  'NIS2 对关键实体网络与信息系统安全管理要求有哪些证据条款？',
  'JC-STAR 里和家用网络设备最相关的核心要求有哪些？',
  '请只基于原文说明该法规的适用范围，不要做延伸解释。',
]

const form = reactive({
  question: '',
  country_code: '',
  product_code: '',
  document_id: '',
})

const canAsk = computed(() => form.question.trim().length >= 5)

const selectedDocumentName = computed(() => {
  if (!form.document_id) return '全部可检索文档'
  return readyDocuments.value.find((doc) => doc.id === form.document_id)?.name || '指定文档'
})

function buildTurn(role, content, result = null) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    role,
    content,
    result,
    createdAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
  }
}

function scopeLabel(value, options, fallback) {
  if (!value) return fallback
  const item = options.find((row) => row.code === value)
  return item ? (item.name_zh || item.code) : value
}

function renderTraceInline(trace) {
  if (!trace?.retrieval_counts) return '本次未返回检索轨迹'
  const counts = trace.retrieval_counts
  return `条款结构 ${counts.section_hits ?? 0} / 语义召回 ${counts.vector_hits ?? 0} / 关键词召回 ${counts.keyword_hits ?? 0}`
}

function answerStatusText(status) {
  return statusLabel(status)
}

function citationLocation(citation) {
  const rawClause = String(citation?.clause_ref || '').trim()
  const clause = rawClause && rawClause !== 'verified read model' ? rawClause : '结构化记录'
  if (citation?.page_from === null || citation?.page_from === undefined || citation?.page_from === '') {
    return clause
  }
  const pageTo = citation.page_to
  const range = pageTo && pageTo !== citation.page_from ? `${citation.page_from}-${pageTo}` : citation.page_from
  return `${clause} · 第 ${range} 页`
}

function buildHistoryPayload() {
  return turns.value
    .slice(-8)
    .map((turn) => ({ role: turn.role, content: turn.content }))
    .filter((item) => item.content?.trim())
}

function fillPrompt(prompt) {
  form.question = prompt
}

function resetConversation() {
  turns.value = []
  latestResult.value = null
  latestTrace.value = null
  form.question = ''
}

async function loadMeta() {
  try {
    const meta = await api.get('/compliance/meta/all')
    countries.value = meta.countries || []
    products.value = meta.products || []
    const docs = await api.get('/documents/', { params: { limit: 200, index_status: 'ready' } })
    readyDocuments.value = (docs.items || []).sort((a, b) => String(a.name).localeCompare(String(b.name), 'zh-CN'))
  } catch (e) {
    toast(String(e), 'error')
  }
}

async function askQuestion() {
  const question = form.question.trim()
  if (!question || asking.value) return

  const history = buildHistoryPayload()
  turns.value.push(buildTurn('user', question))
  asking.value = true

  try {
    const response = await ragApi.ask({
      question,
      country_code: form.country_code || null,
      product_code: form.product_code || null,
      document_id: form.document_id || null,
      top_k: 6,
      verified_only: true,
      history,
    })
    latestResult.value = response
    latestTrace.value = response.trace || null
    turns.value.push(buildTurn('assistant', response.answer, response))
    form.question = ''
  } catch (e) {
    const detail = String(e)
    const errorResult = {
      status: 'error',
      trace: latestTrace.value,
      citations: [],
      related_records: [],
      next_actions: [
        '先保持“全部已核验/可检索文档”，不要限定单文档后重试',
        '到“法规原文”确认目标文档是否处于“可问答/ready”状态',
        '如果连续失败，说明后端链路异常，需要查看服务器日志',
      ],
    }
    latestResult.value = errorResult
    turns.value.push(
      buildTurn(
        'assistant',
        `本次问答没有完成，问题没有进入有效回答阶段。\n\n错误摘要：${detail}`,
        errorResult,
      ),
    )
    toast(detail, 'error')
  } finally {
    asking.value = false
  }
}

onMounted(async () => {
  await loadMeta()
  if (route.query.document) form.document_id = String(route.query.document)
  if (route.query.country) form.country_code = String(route.query.country)
  if (route.query.question) form.question = String(route.query.question)
})
</script>

<style scoped>
.agent-page {
  display: grid;
  gap: 20px;
}

.agent-hero {
  position: relative;
  overflow: hidden;
  min-height: 154px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background:
    radial-gradient(circle at top right, rgba(255,208,96,.18), transparent 26%),
    radial-gradient(circle at bottom left, rgba(0,204,255,.16), transparent 28%),
    linear-gradient(135deg, rgba(0,204,255,.08), rgba(255,255,255,.01)),
    var(--bg2);
}

.agent-title {
  font-size: 32px;
  font-weight: 600;
  letter-spacing: .6px;
}

.agent-subtitle {
  max-width: 760px;
  margin-top: 10px;
  color: var(--text2);
  line-height: 1.8;
}

.hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
  max-width: 280px;
}

.hero-badge {
  padding: 8px 12px;
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 999px;
  background: rgba(255,255,255,.04);
  color: var(--text);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.agent-grid {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
}

.agent-panel {
  min-height: 720px;
}

.panel-header {
  display: grid;
  gap: 6px;
  margin-bottom: 16px;
}

.panel-caption {
  color: var(--text3);
  font-size: 12px;
}

.left-panel,
.right-panel {
  position: sticky;
  top: 0;
}

.policy-box {
  border: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,0));
  padding: 14px;
  border-radius: 4px;
  margin-bottom: 18px;
}

.policy-label,
.desk-title,
.inline-title {
  font-size: 11px;
  color: var(--text3);
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.policy-items,
.next-actions,
.starter-list,
.related-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.policy-pill,
.next-pill,
.starter-chip {
  border-radius: 999px;
  border: 1px solid var(--border2);
  background: var(--bg3);
  color: var(--text2);
  padding: 6px 10px;
  font-size: 12px;
}

.policy-pill.locked {
  color: var(--yellow);
  border-color: rgba(255,208,96,.25);
  background: rgba(255,208,96,.08);
}

.starter-chip {
  cursor: pointer;
  transition: all .15s;
}

.starter-chip:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.agent-textarea {
  min-height: 180px;
}

.field-hint {
  margin-top: 8px;
  color: var(--text3);
  font-size: 12px;
  line-height: 1.6;
}

.action-row {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
}

.starter-block {
  display: grid;
  gap: 10px;
}

.center-panel {
  display: grid;
  gap: 16px;
}

.empty-state {
  min-height: 620px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 10px;
  padding: 32px;
  border: 1px dashed var(--border2);
  border-radius: 4px;
  background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,0));
}

.empty-kicker {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--accent);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.empty-title {
  font-size: 24px;
  font-weight: 600;
}

.empty-copy {
  max-width: 520px;
  color: var(--text2);
  line-height: 1.9;
}

.timeline {
  display: grid;
  gap: 14px;
}

.turn-card {
  padding: 16px 18px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,.02);
}

.turn-user {
  background:
    linear-gradient(135deg, rgba(0,204,255,.08), rgba(0,204,255,.02)),
    var(--bg2);
}

.turn-assistant {
  background:
    linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,0)),
    var(--bg2);
}

.turn-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--text3);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 8px;
}

.turn-content {
  white-space: pre-wrap;
  line-height: 1.9;
}

.turn-status-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}

.trace-inline {
  color: var(--text3);
  font-size: 12px;
}

.answer-status {
  display: inline-flex;
  width: fit-content;
  padding: 4px 10px;
  border-radius: 999px;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
}

.answer-status.answered { background: rgba(0,229,160,.12); color: var(--green); }
.answer-status.error { background: rgba(255,138,138,.12); color: #ff8a8a; }
.answer-status.insufficient { background: rgba(255,77,106,.12); color: var(--red); }

.inline-section {
  margin-top: 14px;
}

.citation-list {
  display: grid;
  gap: 10px;
}

.citation-card {
  border: 1px solid var(--border);
  background: rgba(255,255,255,.02);
  border-radius: 4px;
  padding: 12px;
}

.citation-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
  color: var(--accent);
  font-size: 11px;
  letter-spacing: .5px;
  text-transform: uppercase;
}

.citation-text {
  color: var(--text2);
  font-size: 13px;
  line-height: 1.8;
}

.desk-block {
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: rgba(255,255,255,.02);
  margin-bottom: 14px;
}

.desk-copy,
.desk-empty {
  color: var(--text2);
  line-height: 1.8;
  font-size: 13px;
}

.trace-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.trace-cell {
  padding: 12px;
  border-radius: 4px;
  background: var(--bg3);
  border: 1px solid var(--border2);
  display: grid;
  gap: 4px;
}

.trace-cell span {
  color: var(--text3);
  font-family: var(--mono);
  font-size: 11px;
  text-transform: uppercase;
}

.trace-cell strong {
  font-size: 22px;
  color: var(--accent);
}

.scope-list {
  display: grid;
  gap: 10px;
}

.scope-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--text2);
  font-size: 13px;
}

.scope-row strong {
  color: var(--text);
  text-align: right;
}

@media (max-width: 1380px) {
  .agent-grid {
    grid-template-columns: 1fr;
  }

  .left-panel,
  .right-panel {
    position: static;
    min-height: auto;
  }

  .agent-panel {
    min-height: auto;
  }
}
</style>
