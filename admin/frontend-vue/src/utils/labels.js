const ROLE_LABELS = {
  admin: '管理员',
  viewer: '普通用户',
}

const AUTHENTICITY_LABELS = {
  verified: '已核验',
  suspicious: '待复核',
  quarantined: '已隔离',
  candidate: '候选',
}

const SOURCE_TYPE_LABELS = {
  html_list: '官方网页列表',
  html: '官方正文页',
  pdf: '官方 PDF',
  rss: '官方 RSS',
  api: '官方接口',
  gazette: '官方公报',
  registry: '官方登记库',
}

const ARTIFACT_TYPE_LABELS = {
  artifact: '原文工件',
  html_list: '官方网页列表',
  html: '官方正文页',
  pdf: '官方 PDF',
  rss: '官方 RSS',
  api: '官方接口',
  gazette: '官方公报',
  registry: '官方登记库',
}

const DOWNLOAD_STATUS_LABELS = {
  pending: '待抓取',
  downloading: '抓取中',
  downloaded: '已抓取',
  ready: '可用',
  failed: '抓取失败',
  success: '成功',
  skipped: '已跳过',
}

const AGENT_TOOL_LABELS = {
  ComplianceInventoryTool: '合规清单检索',
  SpecRequirementTool: '规格要求检索',
  VerifiedRagTool: '原文证据检索',
  EffectiveDateTool: '生效日期检索',
  EvidenceLookupTool: '证据链检索',
  CaseCreationTool: '待办工单创建',
}

const STATUS_LABELS = {
  answered: '已基于证据回答',
  case_created: '已创建待处理任务',
  needs_clarification: '需要补充条件',
  insufficient_evidence: '证据不足',
  out_of_scope: '已过滤无关问题',
  blocked: '已拦截越权指令',
  error: '调用异常',
  analysis: '辅助分析',
  ok: '成功',
  success: '成功',
  failed: '失败',
  pending: '待处理',
  indexing: '索引中',
  ready: '可问答',
}

const RETRIEVAL_LABELS = {
  section: '条款结构',
  vector: '语义召回',
  keyword: '关键词召回',
  merged: '合并结果',
}

export function labelFrom(map, value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback
  return map[value] || String(value)
}

export function roleLabel(value) {
  return labelFrom(ROLE_LABELS, value, '普通用户')
}

export function authenticityLabel(value) {
  return labelFrom(AUTHENTICITY_LABELS, value || 'candidate')
}

export function sourceTypeLabel(value) {
  return labelFrom(SOURCE_TYPE_LABELS, value)
}

export function artifactTypeLabel(value) {
  return labelFrom(ARTIFACT_TYPE_LABELS, value || 'artifact')
}

export function downloadStatusLabel(value) {
  return labelFrom(DOWNLOAD_STATUS_LABELS, value)
}

export function agentToolLabel(value) {
  return labelFrom(AGENT_TOOL_LABELS, value)
}

export function statusLabel(value) {
  return labelFrom(STATUS_LABELS, value)
}

export function retrievalLabel(value) {
  return labelFrom(RETRIEVAL_LABELS, value)
}

export function bilingualLabel(label, code) {
  if (!code || label === code) return label
  return `${label}（${code}）`
}
