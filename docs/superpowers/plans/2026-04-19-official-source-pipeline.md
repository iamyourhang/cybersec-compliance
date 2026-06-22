# 官方源白名单周更链路 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用官方源白名单驱动周更链路，停用 AI 搜索直写正式库，并把新内容统一导入候选与原文工件流程。

**Architecture:** 新增 `official_sources` 注册表与抓取管线，调度器改为同步官方源、抓取工件、候选校验和文件解析四段式流程。旧 `CollectorEngine` 保留但退出调度链和后台触发入口。

**Tech Stack:** FastAPI, APScheduler, PostgreSQL, COS, requests/HTML parsing, pytest

---

### Task 1: 数据库与源注册表

**Files:**
- Create: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/database/migrations/V7__official_sources.sql`
- Test: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/tests/test_official_sources_repository.py`

- [ ] 定义 `official_sources`、`official_source_history` 表与索引
- [ ] 补首批种子源：EU/GB/US/JP/SG
- [ ] 为 repository 写最小 CRUD 测试

### Task 2: 官方源抓取管线

**Files:**
- Create: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/collector/official_sources/models.py`
- Create: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/collector/official_sources/repository.py`
- Create: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/collector/official_sources/fetchers.py`
- Create: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/collector/official_sources/normalizers.py`
- Create: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/collector/official_sources/pipeline.py`
- Test: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/tests/test_official_source_pipeline.py`

- [ ] 实现 `rss/html_list/pdf_index` 三类抓取器
- [ ] 统一归一化结果结构
- [ ] 写入同步历史
- [ ] 对命中条目生成 `candidate`

### Task 3: 原文工件抓取与 HTML 快照

**Files:**
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/collector/document/source_ingest.py`
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/database/repository.py`
- Test: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/tests/test_source_ingest.py`

- [ ] 扩展工件抓取支持 HTML 快照
- [ ] 记录工件类型、SHA256、COS URL
- [ ] 确保后续解析只读取工件

### Task 4: 调度器与后台任务入口替换

**Files:**
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/scheduler/main.py`
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/admin/api/routes/tasks.py`
- Test: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/tests/test_scheduler_jobs.py`

- [ ] 删除旧 `full_update/incremental_check` 调度入口
- [ ] 新增 `official_source_sync_daily/weekly`、`artifact_fetch`、`candidate_verification`、`document_parse`
- [ ] 手动任务入口同步改名和改行为

### Task 5: 后台官方源 API 与页面

**Files:**
- Create: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/admin/api/routes/official_sources.py`
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/admin/api/main.py`
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/admin/frontend-vue/src/api/index.js`
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/admin/frontend-vue/src/router/index.js`
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/admin/frontend-vue/src/views/Layout.vue`
- Create: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/admin/frontend-vue/src/views/OfficialSources.vue`
- Test: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/tests/test_official_sources_route.py`

- [ ] 提供源列表、编辑、启停、单源同步、历史查看
- [ ] 页面增加“官方源”入口

### Task 6: 周报统计与回归

**Files:**
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/scheduler/main.py`
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/reporter/excel_reporter.py`
- Modify: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/notifier/feishu.py`
- Test: `/Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/tests/test_weekly_report_metrics.py`

- [ ] 周报统计改为 candidate / verified / 工件 / 隔离
- [ ] 验证后台任务页、周报、健康检查都正常
