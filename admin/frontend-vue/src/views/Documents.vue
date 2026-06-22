<template>
  <div>
    <!-- 上传区域 -->
    <div v-if="auth.isAdmin" class="card" style="margin-bottom:20px">
      <div class="card-title">📤 上传法规原文</div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end">
        <div class="form-group" style="margin:0;flex:2;min-width:200px">
          <label class="form-label">文档名称</label>
          <input class="input" v-model="upload.name" placeholder="如：EU Cyber Resilience Act 2024" />
        </div>
        <div class="form-group" style="margin:0;width:130px">
          <label class="form-label">国家/地区</label>
          <select class="select" v-model="upload.country_code">
            <option v-for="c in countries" :key="c.code" :value="c.code">{{ c.code }} - {{ c.name_zh }}</option>
          </select>
        </div>
        <div class="form-group" style="margin:0;flex:2;min-width:200px">
          <label class="form-label">选择PDF文件</label>
          <input type="file" accept=".pdf" @change="onFileChange" style="color:var(--text2);font-size:13px" />
        </div>
        <div class="form-group" style="margin:0">
          <label class="form-label">上传后</label>
          <div style="display:flex;align-items:center;gap:8px;height:36px">
            <input type="checkbox" v-model="upload.auto_parse" id="auto_parse" />
            <label for="auto_parse" style="font-size:13px;color:var(--text2);cursor:pointer">自动解析</label>
          </div>
        </div>
        <button class="btn btn-primary" :disabled="uploading || !upload.file || !upload.name" @click="handleUpload">
          {{ uploading ? '上传中...' : '上传并解析' }}
        </button>
      </div>
      <div v-if="uploadProgress" style="margin-top:12px;font-size:12px;color:var(--accent)">{{ uploadProgress }}</div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <select class="select" style="width:130px" v-model="filters.country_code" @change="load">
        <option value="">全部国家</option>
        <option v-for="c in countries" :key="c.code" :value="c.code">{{ c.code }} - {{ c.name_zh }}</option>
      </select>
      <select class="select" style="width:130px" v-model="filters.parse_status" @change="load">
        <option value="">全部状态</option>
        <option value="pending">待解析</option>
        <option value="parsing">解析中</option>
        <option value="done">已完成</option>
        <option value="failed">失败</option>
      </select>
      <select class="select" style="width:140px" v-model="filters.index_status" @change="load">
        <option value="">全部索引</option>
        <option value="pending">待索引</option>
        <option value="indexing">索引中</option>
        <option value="ready">可问答</option>
        <option value="failed">索引失败</option>
      </select>
      <button class="btn btn-outline" @click="load">刷新</button>
      <span style="margin-left:auto;font-size:12px;color:var(--text3)">共 {{ items.length }} 个文档</span>
    </div>

    <!-- 文档列表 -->
    <div class="card" style="padding:0">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:300px">文档名称</th>
              <SortableHeader label="国家" field="country_code" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
              <th>文件名</th>
              <SortableHeader label="大小" field="file_size" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
              <SortableHeader label="解析状态" field="parse_status" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
              <th>索引状态</th>
              <SortableHeader label="上传时间" field="created_at" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!items.length"><td colspan="8" class="empty">暂无文档</td></tr>
            <tr v-for="doc in items" :key="doc.id">
              <td>
                <div style="font-size:13px;font-weight:500;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="doc.name">
                  {{ doc.name }}
                </div>
                <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px">
                  <span :class="['badge', authenticityClass(doc.authenticity_status)]">
                    {{ authenticityLabel(doc.authenticity_status) }}
                  </span>
                  <span v-if="doc.source_artifact_count" class="tag">证据 {{ doc.source_artifact_count }}</span>
                  <span v-if="doc.canonical_requirement_name" class="tag" :title="doc.canonical_requirement_name">
                    规范实体
                  </span>
                </div>
                <div v-if="doc.compliance_id" style="font-size:11px;color:var(--green);margin-top:2px">✅ 已关联知识库</div>
                <div v-if="doc.canonical_requirement_name" style="font-size:11px;color:var(--text3);margin-top:2px;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="doc.canonical_requirement_name">
                  📚 {{ doc.canonical_requirement_name }}
                </div>
                <div v-if="doc.spec_cos_url" style="font-size:11px;color:var(--yellow);margin-top:2px">
                  📊 <a :href="doc.spec_cos_url" target="_blank" style="color:var(--yellow)">下载规格Excel</a>
                </div>
                <div v-if="doc.spec_requirement_count" style="font-size:11px;color:var(--green);margin-top:2px">
                  🧩 已入库 {{ doc.spec_requirement_count }} 条规格
                </div>
                <div v-if="doc.spec_progress > 0 && doc.spec_progress < 100" style="margin-top:6px;min-width:160px">
                  <div style="display:flex;justify-content:space-between;margin-bottom:3px">
                    <span style="font-size:10px;color:var(--yellow)">📊 规格生成中</span>
                    <span style="font-size:10px;color:var(--yellow)">{{ doc.spec_progress }}%</span>
                  </div>
                  <div style="background:var(--bg3);border-radius:3px;height:4px;overflow:hidden">
                    <div :style="{width: doc.spec_progress+'%', background:'var(--yellow)', height:'100%', transition:'width .5s'}" />
                  </div>
                  <div style="font-size:10px;color:var(--text3);margin-top:3px">{{ doc.spec_progress_msg }}</div>
                </div>
              </td>
              <td><span class="tag">{{ doc.country_code }}</span></td>
              <td style="font-size:12px;color:var(--text3);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="doc.file_name">
                {{ doc.file_name }}
              </td>
              <td style="font-family:var(--mono);font-size:12px;white-space:nowrap">{{ formatSize(doc.file_size) }}</td>
              <td>
                <div>
                <span :class="['badge', statusClass[doc.parse_status]]">
                  {{ statusLabel[doc.parse_status] }}
                </span>
                <div v-if="doc.parse_status==='parsing' || (doc.progress > 0 && doc.progress < 100)"
                  style="margin-top:6px;min-width:120px">
                  <div style="background:var(--bg3);border-radius:3px;height:4px;overflow:hidden">
                    <div :style="{width: doc.progress+'%', background:'var(--accent)', height:'100%', transition:'width .5s'}" />
                  </div>
                  <div style="font-size:10px;color:var(--text3);margin-top:3px">
                    {{ doc.progress }}% · {{ doc.progress_msg || '处理中...' }}
                  </div>
                </div>
              </div>
              </td>
              <td>
                <div style="display:grid;gap:6px">
                  <span :class="['badge', indexClass[doc.index_status || 'pending']]">
                    {{ indexLabel[doc.index_status || 'pending'] }}
                  </span>
                  <div style="font-size:11px;color:var(--text3)">
                    {{ doc.chunk_count || 0 }} 个切片
                  </div>
                  <div style="font-size:11px;color:var(--text3)">
                    证据风险 {{ doc.authenticity_risk_score ?? '—' }}
                  </div>
                </div>
              </td>
              <td style="font-family:var(--mono);font-size:11px;color:var(--text3);white-space:nowrap">
                {{ (doc.created_at||'').slice(0,16) }}
              </td>
              <td>
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                  <a v-if="doc.cos_url" :href="doc.cos_url" target="_blank" class="btn btn-sm btn-outline">下载</a>
                  <button v-if="auth.isAdmin && doc.parse_status!=='parsing'" class="btn btn-sm btn-green" @click="triggerParse(doc.id)">
                    {{ doc.parse_status==='done' ? '重新解析' : '解析' }}
                  </button>
                  <button v-if="doc.parse_status==='done'" class="btn btn-sm btn-outline" @click="showResult(doc)">结果</button>
                  <button v-if="doc.index_status==='ready'" class="btn btn-sm btn-outline" @click="showChunks(doc)">切片</button>
                  <button v-if="doc.index_status==='ready'" class="btn btn-sm btn-outline" @click="showSections(doc)">条款</button>
                  <button v-if="auth.isAdmin && doc.index_status!=='indexing'" class="btn btn-sm btn-outline" @click="triggerIndex(doc.id)">重建索引</button>
                  <button v-if="doc.index_status==='ready'" class="btn btn-sm btn-primary" @click="askWithDoc(doc)">问答</button>
                  <button v-if="auth.isAdmin" class="btn btn-sm btn-outline" style="color:var(--yellow);border-color:rgba(255,208,96,.4)" :disabled="!doc.is_verified_document" @click="handleGenerateSpec(doc)">
                    {{ doc.is_verified_document ? '生成规格' : '待复核' }}
                  </button>
                  <button v-if="auth.isAdmin" class="btn btn-sm btn-danger" @click="handleDelete(doc)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 解析结果弹窗 -->
    <div v-if="resultDoc" class="modal-overlay" @click.self="resultDoc=null">
      <div class="modal" style="width:760px">
        <div class="modal-header">
          <span>解析结果 · {{ resultDoc.name }}</span>
          <button class="close-btn" @click="resultDoc=null">×</button>
        </div>
        <div class="modal-body">
          <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px">
            <div class="chunk-card" style="padding:10px">
              <div class="form-label">真实性</div>
              <div style="margin-top:6px"><span :class="['badge', authenticityClass(resultDoc.authenticity_status)]">{{ authenticityLabel(resultDoc.authenticity_status) }}</span></div>
            </div>
            <div class="chunk-card" style="padding:10px">
              <div class="form-label">证据工件</div>
              <div style="margin-top:6px;font-size:20px;font-family:var(--mono);color:var(--accent)">{{ resultDoc.source_artifact_count || 0 }}</div>
            </div>
            <div class="chunk-card" style="padding:10px">
              <div class="form-label">切片数量</div>
              <div style="margin-top:6px;font-size:20px;font-family:var(--mono);color:var(--accent)">{{ resultDoc.chunk_count || 0 }}</div>
            </div>
            <div class="chunk-card" style="padding:10px">
              <div class="form-label">规格入库</div>
              <div style="margin-top:6px;font-size:20px;font-family:var(--mono);color:var(--accent)">{{ resultDoc.spec_requirement_count || 0 }}</div>
            </div>
          </div>
          <div v-if="resultDoc.canonical_requirement_name" style="margin-bottom:12px;padding:12px 14px;border:1px solid var(--border);border-radius:4px;background:rgba(255,255,255,.02)">
            <div class="form-label">规范实体</div>
            <div style="margin-top:6px;font-size:13px;font-weight:600">{{ resultDoc.canonical_requirement_name }}</div>
            <div style="margin-top:4px;font-size:11px;color:var(--text3)">
              状态：{{ authenticityLabel(resultDoc.canonical_verification_status) }}
            </div>
          </div>
          <div v-if="resultDoc.source_artifacts?.length" style="margin-bottom:12px;padding:12px 14px;border:1px solid var(--border);border-radius:4px;background:rgba(255,255,255,.02)">
            <div class="form-label">证据工件</div>
            <div style="display:grid;gap:10px;margin-top:8px">
              <div v-for="artifact in resultDoc.source_artifacts" :key="artifact.id" class="chunk-card" style="padding:10px">
                <div class="chunk-meta">
                  <span :title="artifact.artifact_type">{{ artifactTypeLabel(artifact.artifact_type) }}</span>
                  <span :title="artifact.download_status">{{ downloadStatusLabel(artifact.download_status) }}</span>
                  <span v-if="artifact.downloaded_at">{{ artifact.downloaded_at.slice(0, 16) }}</span>
                </div>
                <div style="display:grid;gap:6px;font-size:12px">
                  <div v-if="artifact.official_url">
                    官方页：
                    <a :href="artifact.official_url" target="_blank" style="color:var(--accent)">{{ artifact.official_url }}</a>
                  </div>
                  <div v-if="artifact.artifact_url">
                    工件：
                    <a :href="artifact.artifact_url" target="_blank" style="color:var(--yellow)">{{ artifact.artifact_url }}</a>
                  </div>
                  <div v-if="artifact.download_error" style="color:var(--red)">
                    错误：{{ artifact.download_error }}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-if="resultDoc.parse_result" style="display:grid;gap:12px">
            <div class="form-row">
              <div><span class="form-label">法规名称</span><div style="font-size:13px">{{ resultDoc.parse_result.name }}</div></div>
              <div><span class="form-label">生效日期</span><div style="font-family:var(--mono);font-size:13px;color:var(--accent)">{{ resultDoc.parse_result.effective_date || '—' }}</div></div>
            </div>
            <div class="form-row">
              <div><span class="form-label">认证机构</span><div style="font-size:13px">{{ resultDoc.parse_result.issuing_body || '—' }}</div></div>
              <div><span class="form-label">强制性</span><div style="font-size:13px">{{ resultDoc.parse_result.mandatory }}</div></div>
            </div>
            <div>
              <span class="form-label">适用产品</span>
              <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">
                <span v-for="p in (resultDoc.parse_result.applicable_products||[])" :key="p" class="tag">{{ p }}</span>
              </div>
            </div>
            <div v-if="resultDoc.parse_result.requirements">
              <span class="form-label">核心要求</span>
              <ul style="margin-top:6px;padding-left:16px;font-size:13px;color:var(--text2)">
                <li v-for="(r,i) in (resultDoc.parse_result.requirements.key_requirements||[])" :key="i" style="margin-bottom:4px">{{ r }}</li>
              </ul>
            </div>
            <div>
              <span class="form-label">备注</span>
              <div style="font-size:12px;color:var(--text3)">{{ resultDoc.parse_result.remarks || '—' }}</div>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;padding-top:8px;border-top:1px solid var(--border)">
              <span style="font-size:11px;color:var(--text3)">置信度: {{ resultDoc.parse_result.confidence_score }}</span>
              <span v-if="resultDoc.compliance_id" style="font-size:12px;color:var(--green)">✅ 已写入知识库</span>
            </div>
          </div>
          <div v-else-if="resultDoc.parse_error" style="color:var(--red);font-size:13px;padding:20px 0">
            ❌ 解析失败：{{ resultDoc.parse_error }}
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="resultDoc=null">关闭</button>
          <button v-if="auth.isAdmin && !resultDoc.compliance_id && resultDoc.parse_result" class="btn btn-primary" @click="writeToKnowledge(resultDoc.id)">
            写入知识库
          </button>
        </div>
      </div>
    </div>

    <div v-if="chunkDoc" class="modal-overlay" @click.self="chunkDoc=null">
      <div class="modal" style="width:920px">
        <div class="modal-header">
          <span>切片预览 · {{ chunkDoc.name }}</span>
          <button class="close-btn" @click="chunkDoc=null">×</button>
        </div>
        <div class="modal-body">
          <div v-if="!chunkItems.length" class="empty" style="padding:40px 0">暂无切片</div>
          <div v-else style="display:grid;gap:10px">
            <div v-for="chunk in chunkItems" :key="chunk.id" class="chunk-card">
              <div class="chunk-meta">
                <span>#{{ chunk.chunk_index }}</span>
                <span>{{ chunk.clause_ref || '未识别条款' }}</span>
                <span>第 {{ chunk.page_from }}<template v-if="chunk.page_from !== chunk.page_to">-{{ chunk.page_to }}</template> 页</span>
              </div>
              <div style="font-size:12px;color:var(--text3);margin-bottom:6px">{{ chunk.section_path || '未识别层级' }}</div>
              <div class="chunk-text">{{ chunk.content }}</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="chunkDoc=null">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="sectionDoc" class="modal-overlay" @click.self="sectionDoc=null">
      <div class="modal" style="width:920px">
        <div class="modal-header">
          <span>条款结构 · {{ sectionDoc.name }}</span>
          <button class="close-btn" @click="sectionDoc=null">×</button>
        </div>
        <div class="modal-body">
          <div v-if="sectionDiagnostics.parsed_count || sectionDiagnostics.filtered_count"
            style="margin-bottom:12px;padding:12px 14px;border:1px solid var(--border);border-radius:4px;background:rgba(255,255,255,.02)">
            <div style="font-size:12px;color:var(--text2);margin-bottom:6px">
              共识别 {{ sectionDiagnostics.parsed_count || sectionItems.length }} 个结构节点，
              过滤 {{ sectionDiagnostics.filtered_count || 0 }} 个疑似目录/低置信度节点
            </div>
            <div v-if="Object.keys(sectionDiagnostics.filtered_reason_summary || {}).length"
              style="display:flex;gap:6px;flex-wrap:wrap">
              <span v-for="(count, reason) in sectionDiagnostics.filtered_reason_summary" :key="reason" class="tag">
                {{ reason }} · {{ count }}
              </span>
            </div>
          </div>
          <div v-if="!sectionItems.length" class="empty" style="padding:40px 0">暂无条款结构</div>
          <div v-else style="display:grid;gap:10px">
            <div v-for="section in sectionItems" :key="section.id" class="chunk-card">
              <div class="chunk-meta">
                <span>#{{ section.section_index }}</span>
                <span>{{ section.section_type }}</span>
                <span>{{ section.section_ref }}</span>
                <span>第 {{ section.page_from }}<template v-if="section.page_from !== section.page_to">-{{ section.page_to }}</template> 页</span>
              </div>
              <div v-if="section.title" style="font-size:13px;font-weight:600;margin-bottom:6px">{{ section.title }}</div>
              <div style="font-size:12px;color:var(--text3);margin-bottom:6px">{{ section.section_path || '未识别层级' }}</div>
              <div class="chunk-text">{{ section.content || '该结构节点暂无正文' }}</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="sectionDoc=null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, watch, inject } from 'vue'
import { useRouter } from 'vue-router'
import SortableHeader from '@/components/SortableHeader.vue'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { artifactTypeLabel, downloadStatusLabel } from '@/utils/labels'

const router = useRouter()
const auth = useAuthStore()
const toast = inject('toast')
const items = ref([])
const loading = ref(false)
const uploading = ref(false)
const uploadProgress = ref('')
const resultDoc = ref(null)
const chunkDoc = ref(null)
const chunkItems = ref([])
const sectionDoc = ref(null)
const sectionItems = ref([])
const sectionDiagnostics = ref({ parsed_count: 0, filtered_count: 0, filtered_reason_summary: {} })
const countries = ref([])
const filters = reactive({ country_code: '', parse_status: '', index_status: '' })
const sortField = ref('created_at')
const sortOrder = ref('desc')
function handleSort(field) {
  if (sortField.value === field) { sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc' } else { sortField.value = field; sortOrder.value = 'asc' }
  load()
}
const upload = reactive({ name: '', country_code: 'EU', file: null, auto_parse: true })

const statusLabel = { pending:'待解析', parsing:'解析中', done:'已完成', failed:'失败' }
const statusClass = { pending:'badge-standard', parsing:'badge-certification', done:'badge-active', failed:'badge-deprecated' }
const indexLabel = { pending:'待索引', indexing:'索引中', ready:'可问答', failed:'索引失败' }
const indexClass = { pending:'badge-standard', indexing:'badge-certification', ready:'badge-active', failed:'badge-deprecated' }
const authenticityStatusLabel = { verified: '已核验', suspicious: '待复核', quarantined: '已隔离', candidate: '候选' }
const authenticityStatusClass = { verified: 'badge-active', suspicious: 'badge-certification', quarantined: 'badge-deprecated', candidate: 'badge-standard' }

function authenticityLabel(status) {
  return authenticityStatusLabel[status] || '候选'
}

function authenticityClass(status) {
  return authenticityStatusClass[status] || 'badge-standard'
}

function formatSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + 'KB'
  return (bytes/1024/1024).toFixed(1) + 'MB'
}

function onFileChange(e) { upload.file = e.target.files[0] }

async function load() {
  loading.value = true
  try {
    const params = { limit: 100, sort_by: sortField.value, sort_order: sortOrder.value }
    if (filters.country_code) params.country_code = filters.country_code
    if (filters.parse_status) params.parse_status = filters.parse_status
    if (filters.index_status) params.index_status = filters.index_status
    const data = await api.get('/documents/', { params })
    items.value = data.items || []
  } catch(e) { toast(String(e), 'error') }
  loading.value = false
}

async function loadCountries() {
  try { countries.value = (await api.get('/compliance/meta/all')).countries || [] } catch(e) {}
}

async function handleUpload() {
  if (!upload.file || !upload.name) { toast('请填写名称并选择文件', 'error'); return }
  uploading.value = true
  uploadProgress.value = '正在上传...'
  try {
    const form = new FormData()
    form.append('file', upload.file)
    form.append('name', upload.name)
    form.append('country_code', upload.country_code)
    form.append('auto_parse', upload.auto_parse)
    const data = await api.post('/documents/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    toast(data.message || '上传成功')
    uploadProgress.value = upload.auto_parse ? '✅ 上传成功，后台解析中，约1-2分钟后刷新查看结果' : '✅ 上传成功'
    upload.name = ''; upload.file = null
    setTimeout(load, 3000)
  } catch(e) { toast(String(e), 'error'); uploadProgress.value = '' }
  uploading.value = false
}

async function triggerParse(id) {
  try {
    await api.post(`/documents/${id}/parse`, null, { params: { write_to_knowledge: true } })
    toast('解析任务已启动，约1-2分钟后刷新查看')
    setTimeout(load, 5000)
  } catch(e) { toast(String(e), 'error') }
}

async function triggerIndex(id) {
  try {
    await api.post(`/documents/${id}/index`)
    toast('索引任务已启动，约1-2分钟后刷新查看')
    setTimeout(load, 5000)
  } catch(e) { toast(String(e), 'error') }
}

async function showResult(doc) {
  try {
    const data = await api.get(`/documents/${doc.id}`)
    resultDoc.value = data
  } catch(e) { toast(String(e), 'error') }
}

async function writeToKnowledge(id) {
  try {
    await api.post(`/documents/${id}/parse`, null, { params: { write_to_knowledge: true } })
    toast('已触发写入知识库')
    resultDoc.value = null; load()
  } catch(e) { toast(String(e), 'error') }
}

async function showChunks(doc) {
  try {
    const data = await api.get(`/documents/${doc.id}/chunks`)
    chunkDoc.value = doc
    chunkItems.value = data.items || []
  } catch (e) { toast(String(e), 'error') }
}

async function showSections(doc) {
  try {
    const data = await api.get(`/documents/${doc.id}/sections`)
    sectionDoc.value = doc
    sectionItems.value = data.items || []
    sectionDiagnostics.value = {
      parsed_count: data.parsed_count || 0,
      filtered_count: data.filtered_count || 0,
      filtered_reason_summary: data.filtered_reason_summary || {},
    }
  } catch (e) { toast(String(e), 'error') }
}

function askWithDoc(doc) {
  router.push({
    path: '/research',
    query: {
      document: doc.id,
      country: doc.country_code,
      question: `${doc.name} 的核心合规要求是什么？`,
    },
  })
}

async function handleDelete(doc) {
  if (!confirm(`确认删除文档：${doc.name}？`)) return
  try { await api.delete(`/documents/${doc.id}`); toast('已删除'); load() }
  catch(e) { toast(String(e), 'error') }
}

async function handleGenerateSpec(doc) {
  if (!doc.is_verified_document) {
    toast('只有已核验文档才能生成规格', 'error')
    return
  }
  if (!confirm('从「' + doc.name + '」生成产品规格要求Excel？约需1-3分钟。')) return
  try {
    const result = await api.post('/documents/' + doc.id + '/generate-spec', { applicable_products: null })
    const idx = items.value.findIndex(d => d.id === doc.id)
    if (idx !== -1) {
      items.value[idx].spec_progress = result.spec_progress || 3
      items.value[idx].spec_progress_msg = result.spec_progress_msg || '规格生成任务已启动'
    }
    startPolling()
    toast(result.message || '规格生成任务已启动，后台处理中', 'info')
  } catch(e) { toast(String(e), 'error') }
}

let pollTimer = null

// 只轮询进度，不重新渲染整个列表
async function pollProgress() {
  const active = items.value.filter(d =>
    d.parse_status === 'parsing' ||
    (d.progress > 0 && d.progress < 100) ||
    (d.spec_progress > 0 && d.spec_progress < 100)
  )
  if (!active.length) { stopPolling(); return }

  for (const doc of active) {
    try {
      const fresh = await api.get(`/documents/${doc.id}`)
      const idx = items.value.findIndex(d => d.id === doc.id)
      if (idx !== -1) {
        // 只更新进度相关字段，不替换整个对象避免闪烁
        items.value[idx].progress = fresh.progress
        items.value[idx].progress_msg = fresh.progress_msg
        items.value[idx].parse_status = fresh.parse_status
        items.value[idx].index_status = fresh.index_status
        items.value[idx].index_error = fresh.index_error
        items.value[idx].chunk_count = fresh.chunk_count
        items.value[idx].spec_cos_url = fresh.spec_cos_url
        items.value[idx].spec_requirement_count = fresh.spec_requirement_count
        items.value[idx].spec_progress = fresh.spec_progress
        items.value[idx].spec_progress_msg = fresh.spec_progress_msg
        items.value[idx].compliance_id = fresh.compliance_id
        // 完成时停止轮询该条
        if (fresh.parse_status === 'done' || fresh.parse_status === 'failed') {
          if (fresh.progress >= 100 || fresh.parse_status === 'failed') {
            const stillActive = items.value.some(d =>
              d.parse_status === 'parsing' || (d.progress > 0 && d.progress < 100)
            )
            if (!stillActive) stopPolling()
          }
        }
      }
    } catch(e) {}
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(pollProgress, 3000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

watch(() => items.value.map(d => d.parse_status + ':' + d.spec_progress), () => {
  const hasActive = items.value.some(d =>
    d.parse_status === 'parsing' ||
    d.index_status === 'indexing' ||
    (d.spec_progress > 0 && d.spec_progress < 100)
  )
  if (hasActive) startPolling()
}, { deep: false })

onUnmounted(() => stopPolling())

onMounted(() => { loadCountries(); load() })
</script>

<style scoped>
.chunk-card {
  border: 1px solid var(--border);
  border-radius: 4px;
  background: rgba(255,255,255,.02);
  padding: 14px;
}
.chunk-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--accent);
  font-family: var(--mono);
  font-size: 11px;
  margin-bottom: 8px;
}
.chunk-text {
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: 13px;
  color: var(--text2);
}
</style>
