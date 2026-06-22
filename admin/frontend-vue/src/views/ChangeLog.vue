<template>
  <div>
    <div class="filter-bar">
      <select class="select" style="width:130px" v-model="filters.change_type" @change="reload">
        <option value="">全部类型</option>
        <option value="created">新增</option>
        <option value="updated">更新</option>
        <option value="deprecated">废止</option>
      </select>
      <select class="select" style="width:130px" v-model="filters.reviewed" @change="reload">
        <option value="">全部状态</option>
        <option value="false">待审核</option>
        <option value="true">已审核</option>
      </select>
      <span style="margin-left:auto;font-size:12px;color:var(--text3)">共 {{ total }} 条</span>
    </div>

    <div class="card" style="padding:0">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else class="table-wrap">
        <table>
          <thead><tr>
                <SortableHeader label="变更时间" field="changed_at" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
                <SortableHeader label="类型" field="change_type" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
                <th>条目名称</th>
                <SortableHeader label="国家" field="country_code" :currentSort="sortField" :currentOrder="sortOrder" @sort="handleSort" />
                <th>变更摘要</th><th>审核</th><th>操作</th>
              </tr></thead>
          <tbody>
            <tr v-if="!items.length"><td colspan="7" class="empty">暂无变更记录</td></tr>
            <tr v-for="item in items" :key="item.id">
              <td style="font-family:var(--mono);font-size:11px;color:var(--text3);white-space:nowrap">{{ (item.changed_at||'').slice(0,16) }}</td>
              <td><span :style="{color:typeColor[item.change_type],fontWeight:600,fontSize:12}">{{ typeLabel[item.change_type] }}</span></td>
              <td style="max-width:280px">
                <div style="font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="item.name">{{ item.name }}</div>
              </td>
              <td><span class="tag">{{ item.country_code }}</span></td>
              <td style="font-size:12px;color:var(--text3);max-width:220px">
                <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="item.diff_summary">{{ item.diff_summary || '—' }}</div>
              </td>
              <td>
                <span v-if="item.reviewed" style="color:var(--green);font-size:12px">✅ {{ item.reviewed_by }}</span>
                <span v-else style="color:var(--yellow);font-size:12px">⏳ 待审核</span>
              </td>
              <td>
                <button v-if="!item.reviewed" class="btn btn-sm btn-green" @click="handleReview(item.id)">确认</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="pagination">
      <span class="page-info">{{ total }} 条 / 第 {{ page }}/{{ totalPages||1 }} 页</span>
      <button class="btn btn-sm btn-outline" :disabled="page<=1" @click="page--;load()">上一页</button>
      <button class="btn btn-sm btn-outline" :disabled="page>=totalPages" @click="page++;load()">下一页</button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue'
import SortableHeader from '@/components/SortableHeader.vue'
import { changelogApi } from '@/api'

const toast = inject('toast')
const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const PAGE_SIZE = 20
const filters = reactive({ change_type: '', reviewed: '' })
const sortField = ref('changed_at')
const sortOrder = ref('desc')
function handleSort(field) {
  if (sortField.value === field) { sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc' } else { sortField.value = field; sortOrder.value = 'asc' }
  reload()
}

const typeColor = { created:'var(--green)', updated:'var(--accent)', deprecated:'var(--red)' }
const typeLabel = { created:'新增', updated:'更新', deprecated:'废止' }
const totalPages = computed(() => Math.ceil(total.value / PAGE_SIZE))

function reload() { page.value = 1; load() }

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: PAGE_SIZE, sort_by: sortField.value, sort_order: sortOrder.value }
    if (filters.change_type) params.change_type = filters.change_type
    if (filters.reviewed !== '') params.reviewed = filters.reviewed
    const data = await changelogApi.list(params)
    items.value = data.items; total.value = data.total
  } catch(e) { toast(String(e), 'error') }
  loading.value = false
}

async function handleReview(id) {
  try { await changelogApi.review(id); toast('已标记审核'); load() }
  catch(e) { toast(String(e), 'error') }
}

onMounted(load)
</script>
