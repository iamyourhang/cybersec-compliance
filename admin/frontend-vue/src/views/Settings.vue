<template>
  <div>
    <div class="card">
      <div class="card-title">🔑 API Key 管理</div>
      <div style="margin-bottom:16px;display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
        <div class="form-group" style="margin:0;flex:1;min-width:150px">
          <label class="form-label">Provider</label>
          <select class="select" v-model="newKey.provider">
            <option value="volcengine">火山引擎</option>
            <option value="dashscope">阿里百炼</option>
            <option value="deepseek">DeepSeek</option>
          </select>
        </div>
        <div class="form-group" style="margin:0;flex:1;min-width:150px">
          <label class="form-label">模型名称</label>
          <input class="input" v-model="newKey.model" placeholder="如 doubao-seed-2-0-pro-260215" />
        </div>
        <div class="form-group" style="margin:0;flex:2;min-width:200px">
          <label class="form-label">API Key</label>
          <input class="input" v-model="newKey.api_key" placeholder="sk-..." type="password" />
        </div>
        <div class="form-group" style="margin:0;flex:2;min-width:200px">
          <label class="form-label">Base URL</label>
          <input class="input" v-model="newKey.base_url" />
        </div>
        <button class="btn btn-primary" @click="addKey">添加</button>
      </div>

      <div class="table-wrap">
        <table>
          <thead><tr><th>Provider</th><th>模型</th><th>优先级</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-if="!apiKeys.length"><td colspan="5" class="empty">暂无配置</td></tr>
            <tr v-for="k in apiKeys" :key="k.id">
              <td><span class="tag">{{ k.provider }}</span></td>
              <td style="font-family:var(--mono);font-size:12px">{{ k.model }}</td>
              <td style="font-family:var(--mono);font-size:12px">{{ k.priority }}</td>
              <td><span :style="{color: k.enabled?'var(--green)':'var(--text3)',fontSize:12}">{{ k.enabled?'启用':'禁用' }}</span></td>
              <td>
                <button class="btn btn-sm btn-danger" @click="deleteKey(k.id)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p style="font-size:11px;color:var(--text3);margin-top:12px">注：当前 .env 中配置的 Key 优先级高于此处，此处配置用于动态切换。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'
import { settingsApi } from '@/api'

const toast = inject('toast')
const apiKeys = ref([])
const newKey = ref({ provider:'volcengine', model:'', api_key:'', base_url:'https://ark.cn-beijing.volces.com/api/coding/v3', priority:1 })

async function load() {
  try { apiKeys.value = (await settingsApi.getApiKeys()).items || [] } catch(e) {}
}

async function addKey() {
  if (!newKey.value.model || !newKey.value.api_key) { toast('请填写模型名和Key', 'error'); return }
  try { await settingsApi.saveApiKey(newKey.value); toast('添加成功'); load() }
  catch(e) { toast(String(e), 'error') }
}

async function deleteKey(id) {
  if (!confirm('确认删除？')) return
  try { await settingsApi.deleteApiKey(id); toast('已删除'); load() }
  catch(e) { toast(String(e), 'error') }
}

onMounted(load)
</script>
