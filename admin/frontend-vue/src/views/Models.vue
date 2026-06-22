<template>
  <div>
    <!-- 顶部操作栏 -->
    <div class="filter-bar">
      <input class="input" style="width:220px" v-model="filters.keyword" placeholder="搜索型号/名称..." @input="debounceLoad" />
      <select class="select" style="width:150px" v-model="filters.category_code" @change="reload">
        <option value="">全部大类</option>
        <option v-for="c in categories" :key="c.code" :value="c.code">{{ c.name_zh }}（{{ c.model_count }}）</option>
      </select>
      <input class="input" style="width:130px" v-model="filters.brand" placeholder="品牌..." @input="debounceLoad" />
      <button class="btn btn-primary" @click="openCreate">+ 新增型号</button>
      <span style="margin-left:auto;font-size:12px;color:var(--text3)">共 {{ total }} 个型号</span>
    </div>

    <!-- 型号列表 -->
    <div class="card" style="padding:0">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else class="table-wrap">
        <table>
          <thead><tr>
            <SortableHeader label="型号代码" field="code" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" :thStyle="{width:'160px'}" />
            <SortableHeader label="型号名称" field="name" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" :thStyle="{width:'200px'}" />
            <SortableHeader label="品牌" field="brand" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
            <SortableHeader label="产品大类" field="category_name" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
            <th>状态</th><th>操作</th>
          </tr></thead>
          <tbody>
            <tr v-if="!items.length"><td colspan="6" class="empty">暂无型号，点击「新增型号」添加</td></tr>
            <tr v-for="m in items" :key="m.id">
              <td style="font-family:var(--mono);font-size:12px;font-weight:600;color:var(--accent)">{{ m.code }}</td>
              <td>
                <div style="font-size:13px;font-weight:500">{{ m.name }}</div>
                <div v-if="m.name_en" style="font-size:11px;color:var(--text3)">{{ m.name_en }}</div>
              </td>
              <td><span v-if="m.brand" class="tag">{{ m.brand }}</span><span v-else style="color:var(--text3)">—</span></td>
              <td><span class="badge badge-regulation">{{ m.category_name }}</span></td>
              <td><span :style="{color: m.enabled ? 'var(--green)':'var(--text3)', fontSize:12}">{{ m.enabled ? '启用':'禁用' }}</span></td>
              <td>
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                  <button class="btn btn-sm btn-outline" @click="openCompliance(m)">合规要求</button>
                  <button class="btn btn-sm btn-outline" @click="openEdit(m)">编辑</button>
                  <button class="btn btn-sm btn-danger" @click="handleDelete(m)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination">
      <span class="page-info">{{ total }} 个 / 第 {{ page }}/{{ totalPages||1 }} 页</span>
      <button class="btn btn-sm btn-outline" :disabled="page<=1" @click="page--;load()">上一页</button>
      <button class="btn btn-sm btn-outline" :disabled="page>=totalPages" @click="page++;load()">下一页</button>
    </div>

    <!-- 新增/编辑弹窗 -->
    <div v-if="showForm" class="modal-overlay" @click.self="showForm=false">
      <div class="modal" style="width:600px">
        <div class="modal-header">
          <span>{{ editingId ? '编辑型号' : '新增型号' }}</span>
          <button class="close-btn" @click="showForm=false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">型号代码 *</label>
              <input class="input" v-model="form.code" placeholder="如 RG-NBS5100-24GT4SFP" :disabled="!!editingId" />
            </div>
            <div class="form-group">
              <label class="form-label">产品大类 *</label>
              <select class="select" v-model="form.category_code" :disabled="!!editingId">
                <option value="">请选择</option>
                <option v-for="c in categories" :key="c.code" :value="c.code">{{ c.name_zh }}</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">型号名称（中文）*</label>
              <input class="input" v-model="form.name" placeholder="如 锐捷NBS5100系列交换机" />
            </div>
            <div class="form-group">
              <label class="form-label">型号名称（英文）</label>
              <input class="input" v-model="form.name_en" placeholder="如 Ruijie NBS5100 Series Switch" />
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">品牌</label>
            <input class="input" v-model="form.brand" placeholder="如 锐捷/Ruijie" />
          </div>
          <div class="form-group">
            <label class="form-label">描述</label>
            <textarea class="textarea" v-model="form.description" rows="2" placeholder="产品简介..." />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="showForm=false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="handleSave">{{ saving?'保存中...':'保存' }}</button>
        </div>
      </div>
    </div>

    <!-- 合规要求弹窗 -->
    <div v-if="showCompliance && currentModel" class="modal-overlay" @click.self="showCompliance=false">
      <div class="modal" style="width:1000px;max-height:90vh">
        <div class="modal-header">
          <span>
            <span style="font-family:var(--mono);color:var(--accent)">{{ currentModel.code }}</span>
            &nbsp;·&nbsp;合规要求
            <span style="font-size:12px;color:var(--text3);margin-left:8px">{{ currentModel.category_name }}</span>
          </span>
          <div style="display:flex;gap:8px;align-items:center">
            <select class="select" style="width:140px;font-size:12px" v-model="complianceFilter.country" @change="loadCompliance">
              <option value="">全部国家</option>
              <option v-for="cc in availableCountries" :key="cc.code" :value="cc.code">{{ cc.name }} ({{ cc.code }})</option>
            </select>
            <label style="font-size:12px;color:var(--text2);display:flex;align-items:center;gap:4px;cursor:pointer">
              <input type="checkbox" v-model="complianceFilter.mandatoryOnly" @change="loadCompliance" />
              仅强制
            </label>
            <button class="btn btn-sm btn-outline" @click="handleExport">⬇ 导出清单</button>
            <button class="close-btn" @click="showCompliance=false">×</button>
          </div>
        </div>
        <div class="modal-body" style="padding:0;overflow-y:auto">
          <div v-if="complianceLoading" class="loading">加载中...</div>
          <div v-else-if="!complianceItems.length" class="empty">暂无合规要求（该产品大类尚未关联合规条目）</div>
          <div v-else>
            <!-- 按国家分组展示 -->
            <div v-for="(group, cc) in complianceByCountry" :key="cc"
              style="border-bottom:1px solid var(--border)">
              <div style="padding:10px 20px;background:var(--bg3);display:flex;justify-content:space-between;align-items:center;cursor:pointer"
                @click="toggleCountry(cc)">
                <div style="display:flex;align-items:center;gap:10px">
                  <span style="font-family:var(--mono);color:var(--accent);font-weight:600">{{ cc }}</span>
                  <span style="font-size:13px">{{ group.country_name }}</span>
                  <span class="tag">{{ group.priority }}</span>
                  <span style="font-size:11px;color:var(--text3)">{{ group.items.length }} 条</span>
                </div>
                <span style="color:var(--text3);font-size:12px">{{ expandedCountries.has(cc) ? '▲' : '▼' }}</span>
              </div>
              <div v-if="expandedCountries.has(cc)">
                <table style="width:100%">
                  <thead><tr style="background:var(--bg2)">
                    <th style="width:40%">认证/法规名称</th><th>类型</th><th>强制性</th><th>生效日期</th><th>来源</th><th>操作</th>
                  </tr></thead>
                  <tbody>
                    <tr v-for="item in group.items" :key="item.compliance_id"
                      :style="{opacity: item.source==='exclude' ? 0.4 : 1}">
                      <td>
                        <div style="font-size:12px;font-weight:500;max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="item.compliance_name">
                          {{ item.compliance_name }}
                        </div>
                        <div v-if="item.custom_notes" style="font-size:11px;color:var(--yellow);margin-top:2px">📝 {{ item.custom_notes }}</div>
                      </td>
                      <td><span :class="['badge',`badge-${item.entry_type}`]">{{ {regulation:'法规',standard:'标准',certification:'认证'}[item.entry_type] }}</span></td>
                      <td><span :class="['badge',`badge-${item.mandatory}`]">{{ {mandatory:'强制',voluntary:'自愿',recommended:'推荐'}[item.mandatory] }}</span></td>
                      <td style="font-family:var(--mono);font-size:11px">{{ item.effective_date || '—' }}</td>
                      <td>
                        <span :style="{fontSize:11, color: item.source==='inherited'?'var(--text3)':item.source==='exclude'?'var(--red)':'var(--yellow)'}">
                          {{ {inherited:'继承',include:'定制加入',exclude:'已排除',customize:'定制备注'}[item.source] || item.source }}
                        </span>
                      </td>
                      <td>
                        <div style="display:flex;gap:4px">
                          <button v-if="item.source!=='exclude'" class="btn btn-sm" style="font-size:10px;padding:2px 6px;background:rgba(255,77,106,.1);color:var(--red);border:1px solid rgba(255,77,106,.2)"
                            @click="excludeItem(item)">排除</button>
                          <button v-else class="btn btn-sm btn-outline" style="font-size:10px;padding:2px 6px"
                            @click="restoreItem(item)">恢复</button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <span style="font-size:12px;color:var(--text3)">共 {{ complianceItems.length }} 条合规要求</span>
          <button class="btn btn-outline" @click="showCompliance=false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue'
import SortableHeader from '@/components/SortableHeader.vue'
import { api } from '@/api'

const toast = inject('toast')
const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const saving = ref(false)
const PAGE_SIZE = 20
const totalPages = computed(() => Math.ceil(total.value / PAGE_SIZE))

const categories = ref([])
const filters = reactive({ keyword: '', category_code: '', brand: '' })
const sortField = ref('brand')
const sortOrder = ref('asc')
function handleSort(field) {
  if (sortField.value === field) { sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc' } else { sortField.value = field; sortOrder.value = 'asc' }
  reload()
}
const showForm = ref(false)
const editingId = ref(null)
const form = ref(defaultForm())

const showCompliance = ref(false)
const currentModel = ref(null)
const complianceItems = ref([])
const complianceByCountry = ref({})
const complianceLoading = ref(false)
const complianceFilter = reactive({ country: '', mandatoryOnly: false })
const expandedCountries = ref(new Set())

function defaultForm() {
  return { code:'', name:'', name_en:'', category_code:'', brand:'', description:'' }
}

const availableCountries = computed(() => {
  const map = {}
  complianceItems.value.forEach(i => {
    if (!map[i.country_code]) map[i.country_code] = { code: i.country_code, name: i.country_name }
  })
  return Object.values(map).sort((a,b) => a.code.localeCompare(b.code))
})

let debounceTimer
function debounceLoad() { clearTimeout(debounceTimer); debounceTimer = setTimeout(reload, 400) }
function reload() { page.value = 1; load() }

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: PAGE_SIZE, sort_by: sortField.value, sort_order: sortOrder.value }
    if (filters.keyword)       params.keyword = filters.keyword
    if (filters.category_code) params.category_code = filters.category_code
    if (filters.brand)         params.brand = filters.brand
    const data = await api.get('/models/', { params })
    items.value = data.items; total.value = data.total
  } catch(e) { toast(String(e), 'error') }
  loading.value = false
}

async function loadCategories() {
  try { categories.value = await api.get('/models/categories') } catch(e) {}
}

function openCreate() { editingId.value = null; form.value = defaultForm(); showForm.value = true }
function openEdit(m) {
  editingId.value = m.id
  form.value = { code: m.code, name: m.name, name_en: m.name_en||'', category_code: m.category_code, brand: m.brand||'', description: m.description||'' }
  showForm.value = true
}

async function handleSave() {
  if (!form.value.code || !form.value.name || !form.value.category_code) {
    toast('型号代码、名称、大类为必填项', 'error'); return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/models/${editingId.value}`, form.value)
      toast('更新成功')
    } else {
      await api.post('/models/', form.value)
      toast('创建成功')
    }
    showForm.value = false; load(); loadCategories()
  } catch(e) { toast(String(e), 'error') }
  saving.value = false
}

async function handleDelete(m) {
  if (!confirm(`确认删除型号：${m.code}？`)) return
  try { await api.delete(`/models/${m.id}`); toast('已删除'); load(); loadCategories() }
  catch(e) { toast(String(e), 'error') }
}

async function openCompliance(m) {
  currentModel.value = m
  complianceFilter.country = ''
  complianceFilter.mandatoryOnly = false
  showCompliance.value = true
  await loadCompliance()
  // 默认展开P1国家
  const p1 = ['EU','US','GB','CN','JP','KR']
  expandedCountries.value = new Set(p1.filter(cc => complianceByCountry.value[cc]))
}

async function loadCompliance() {
  if (!currentModel.value) return
  complianceLoading.value = true
  try {
    const params = {}
    if (complianceFilter.country) params.country_code = complianceFilter.country
    if (complianceFilter.mandatoryOnly) params.mandatory_only = true
    const data = await api.get(`/models/${currentModel.value.id}/compliance`, { params })
    complianceItems.value = data.items || []
    complianceByCountry.value = data.by_country || {}
  } catch(e) { toast(String(e), 'error') }
  complianceLoading.value = false
}

function toggleCountry(cc) {
  if (expandedCountries.value.has(cc)) expandedCountries.value.delete(cc)
  else expandedCountries.value.add(cc)
  expandedCountries.value = new Set(expandedCountries.value)
}

async function excludeItem(item) {
  try {
    await api.post(`/models/${currentModel.value.id}/compliance/override`, {
      compliance_id: item.compliance_id, override_type: 'exclude'
    })
    toast('已排除该条目')
    loadCompliance()
  } catch(e) { toast(String(e), 'error') }
}

async function restoreItem(item) {
  try {
    await api.delete(`/models/${currentModel.value.id}/compliance/override/${item.compliance_id}`)
    toast('已恢复继承')
    loadCompliance()
  } catch(e) { toast(String(e), 'error') }
}

async function handleExport() {
  const token = localStorage.getItem('token')
  const params = new URLSearchParams()
  if (complianceFilter.country) params.set('country_code', complianceFilter.country)
  if (complianceFilter.mandatoryOnly) params.set('mandatory_only', 'true')
  const resp = await fetch(`/api/models/${currentModel.value.id}/export?${params}`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!resp.ok) { toast('导出失败', 'error'); return }
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${currentModel.value.code}_合规清单.xlsx`
  a.click()
  toast('导出成功')
}

onMounted(() => { loadCategories(); load() })
</script>
