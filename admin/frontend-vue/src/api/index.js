import axios from 'axios'

const BASE = '/api'

export const api = axios.create({ baseURL: BASE })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r.data,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err.response?.data?.detail || err.message || '请求失败')
  }
)

// 合规知识库
export const complianceApi = {
  list:    (p) => api.get('/compliance/', { params: p }),
  get:     (id) => api.get(`/compliance/${id}`),
  create:  (d) => api.post('/compliance/', d),
  update:  (id, d) => api.put(`/compliance/${id}`, d),
  remove:  (id) => api.delete(`/compliance/${id}`),
  meta:    () => api.get('/compliance/meta/all'),
  review:  (id, d) => api.post(`/compliance/${id}/review`, d),
  manualSource: (id, d) => api.post(`/compliance/${id}/manual-source`, d),
  manualSourceUpload: (id, formData) => api.post(`/compliance/${id}/manual-source-upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  evidence: (id) => api.get(`/evidence/${id}`),
}

export const reviewCasesApi = {
  list: (params) => api.get('/review-cases/', { params }),
  decide: (id, d) => api.post(`/review-cases/${id}/decision`, d),
  aiAssist: (id) => api.post(`/review-cases/${id}/ai-assist`),
}

// 变更日志
export const changelogApi = {
  list:   (p) => api.get('/changelog/', { params: p }),
  review: (id) => api.post(`/changelog/${id}/review`),
}

// 任务管理
export const tasksApi = {
  status:        () => api.get('/tasks/status'),
  history:       () => api.get('/tasks/history'),
  reports:       () => api.get('/tasks/reports'),
  triggerOfficialSourceSync: (d) => api.post('/tasks/trigger/official-source-sync', d),
  triggerUpdate: (d) => api.post('/tasks/trigger/full-update', d),
  triggerArtifactFetch: () => api.post('/tasks/trigger/artifact-fetch'),
  triggerCandidateVerification: () => api.post('/tasks/trigger/candidate-verification'),
  triggerDocumentParse: () => api.post('/tasks/trigger/document-parse'),
  triggerSourceRegistryRefresh: () => api.post('/tasks/trigger/source-registry-refresh'),
  triggerWeeklyComplianceUpdate: () => api.post('/tasks/trigger/weekly-compliance-update'),
  triggerReport: () => api.post('/tasks/trigger/weekly-report'),
  triggerAlert:  () => api.post('/tasks/trigger/alert-scan'),
}

// 仪表盘
export const dashboardApi = {
  stats:    () => api.get('/dashboard/stats'),
  statsFull: () => api.get('/dashboard/stats-full'),
  workflow: () => api.get('/dashboard/workflow'),
  upcoming: (params) => api.get('/dashboard/upcoming', { params }),
  recent:   () => api.get('/dashboard/recent-changes'),
}

// 设置
export const settingsApi = {
  getApiKeys: () => api.get('/settings/api-keys'),
  saveApiKey: (d) => api.post('/settings/api-keys', d),
  deleteApiKey: (id) => api.delete(`/settings/api-keys/${id}`),
  getAlertRules: () => api.get('/settings/alert-rules'),
  updateAlertRule: (id, d) => api.put(`/settings/alert-rules/${id}`, d),
}

export const ragApi = {
  ask: (d) => api.post('/rag/ask', d),
}

export const agentApi = {
  ask: (d) => api.post('/agent/ask', d),
  cases: (params) => api.get('/agent/cases', { params }),
  decideCase: (id, d) => api.post(`/agent/cases/${id}/decision`, d),
}

export const llmChannelsApi = {
  list: () => api.get('/llm-channels/'),
  create: (d) => api.post('/llm-channels/', d),
  update: (id, d) => api.put(`/llm-channels/${id}`, d),
  testById: (id) => api.post(`/llm-channels/${id}/test`),
  pause: (id, d = {}) => api.post(`/llm-channels/${id}/pause`, d),
  resume: (id, d = {}) => api.post(`/llm-channels/${id}/resume`, d),
  markQuotaExhausted: (id, d = {}) => api.post(`/llm-channels/${id}/mark-quota-exhausted`, d),
  clearQuotaExhausted: (id, d = {}) => api.post(`/llm-channels/${id}/clear-quota-exhausted`, d),
  events: (id, params) => api.get(`/llm-channels/${id}/events`, { params }),
  test: (d) => api.post('/llm-channels/test', d),
}

export const officialSourcesApi = {
  list: (params) => api.get('/official-sources/', { params }),
  create: (d) => api.post('/official-sources/', d),
  update: (id, d) => api.put(`/official-sources/${id}`, d),
  sync: (id) => api.post(`/official-sources/${id}/sync`),
  history: (id, params) => api.get(`/official-sources/${id}/history`, { params }),
}

export const specRequirementsApi = {
  list: (params) => api.get('/spec-requirements/', { params }),
}
