import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const screenPath = resolve(here, '../src/views/Screen.vue')
const source = readFileSync(screenPath, 'utf8')

const checks = [
  ['shows built-in compliance agent corpus label', /合规 Agent · 已验证本地语料/.test(source)],
  ['imports authenticated api and agentApi client', /import\s+\{\s*api,\s*agentApi\s*\}\s+from\s+['"]@\/api['"]/.test(source)],
  ['tracks login state for gated asking', /const\s+isLoggedIn\s*=\s*computed/.test(source)],
  ['has a screen ask function', /async\s+function\s+askScreenQuestion\s*\(/.test(source)],
  ['forces verified-only Agent request', /verified_only:\s*true/.test(source)],
  ['uses 90-day alert window for screen Agent', /alert_window_days:\s*90/.test(source)],
  ['passes selected country scope to Agent', /country_code:\s*qaScopeCountry(?:\.value)?/.test(source)],
  ['passes selected document scope to Agent', /document_id:\s*qaScopeDocument(?:\.value)?/.test(source)],
  ['supports asking from item detail', /function\s+askFromItemDetail\s*\(/.test(source)],
  ['renders citation evidence cards', /qa-citation-card/.test(source)],
  ['opens cited source details', /openCitationSource\s*\(/.test(source)],
  ['shows login prompt instead of anonymous RAG', /登录后使用内置 AI 问答/.test(source)],
  ['renders agent case-created status', /case_created/.test(source)],
  ['renders chat-style agent panel', /chatgpt-panel/.test(source) && /chat-composer/.test(source)],
  ['submits on plain Enter with Shift+Enter preserved', /@keydown\.enter\.exact\.prevent="askScreenQuestion"/.test(source)],
  ['renders out-of-scope filter status', /out_of_scope/.test(source) && /已过滤无关问题/.test(source)],
  ['renders assistant answers as sanitized markdown', /v-html="renderAgentMarkdown\(turn\.content\)"/.test(source) && /function\s+escapeHtml\s*\(/.test(source)],
  ['styles markdown answer blocks', /markdown-body/.test(source) && /:deep\(ul\)/.test(source)],
  ['surfaces priority inherited product regulations in country overview', /priority-regimes/.test(source) && /priorityComplianceItems/.test(source)],
  ['orders compliance items by product regulatory importance', /orderedComplianceItems/.test(source) && /complianceImportanceRank/.test(source)],
  ['avoids nested tiny compliance-list scroller', /\.compliance-list\s*\{\s*flex:0 0 auto;\s*overflow:visible;/.test(source)],
  ['renders lifecycle milestones in item detail', /法规生命周期节点/.test(source) && /lifecycle_milestones/.test(source) && /milestone-item/.test(source)],
  ['labels upcoming as applicability milestones', /近90天适用节点/.test(source) && /milestone_label_zh/.test(source)],
]

const failures = checks.filter(([, ok]) => !ok)
if (failures.length) {
  console.error('Screen agent verification failed:')
  for (const [name] of failures) console.error(`- ${name}`)
  process.exit(1)
}

console.log(`Screen agent verification passed: ${checks.length} checks`)
