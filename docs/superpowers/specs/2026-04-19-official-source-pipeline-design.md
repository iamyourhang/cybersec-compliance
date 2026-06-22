# 官方源白名单周更链路设计

## 背景

现有 `scheduler/main.py` 中的 `job_full_update` 与 `job_incremental_check` 直接调用 `CollectorEngine.full_update()` / `incremental_check()`，本质上依赖 AI 联网搜索与模型判断。这个设计在法律法规场景下风险过高，会把未经官方证据确认的候选直接写入正式知识库。

本次重构目标是彻底停用“AI 搜索驱动正式库更新”的链路，改成“官方源白名单驱动”的采集、抓取、候选入库和文件解析流程。

## 目标

1. 每周更新只从官方白名单来源拉取，不再使用 AI 搜索发现新法规。
2. 新发现内容先进入 `candidate`，只有满足证据门槛的记录才允许进入 `verified`。
3. 只要能拿到官方原文页面或 PDF，就保存到 COS，并以此作为后续 RAG / 规格解析的唯一输入。
4. 保留现有 AI 能力，但仅用于“基于已下载文件的解析”，不再用于“发现法规”或“判断真伪”。

## 方案选择

### 方案 A：RSS-only

只使用官方 RSS。

优点：实现简单。
缺点：政府/监管站大量没有 RSS，覆盖率不足。

### 方案 B：官方源注册表 + 多抓取器

建立一张官方源注册表，每个源按 `rss / html_list / pdf_index / official_api` 等类型配置对应抓取器。

优点：兼容性最好，适合长期扩展。
缺点：前期需要先整理一批高质量官方源。

### 方案 C：纯人工维护

不做自动发现，只允许人工补录。

优点：最保守。
缺点：后续维护成本高，无法形成周更能力。

采用方案 B。

## 架构

### 1. 官方源注册层

新增 `official_sources` 表，作为唯一的外部发现入口。每条记录描述一个被允许抓取的官方源。

核心字段：

- `id`
- `country_code`
- `name`
- `base_url`
- `list_url`
- `source_type`
- `allowed_domains`
- `entry_type_scope`
- `poll_interval_hours`
- `priority`
- `enabled`
- `parser_config`
- `last_checked_at`
- `last_success_at`
- `last_error`

其中：

- `source_type` 支持 `rss`、`html_list`、`pdf_index`、`official_api`
- `parser_config` 为 JSON，存放 CSS selector、正则模式、PDF 链接规则等抓取细节

### 2. 官方发现层

新增 `collector/official_sources/` 目录，包含：

- `models.py`
- `repository.py`
- `fetchers.py`
- `normalizers.py`
- `pipeline.py`

职责分工：

- `repository.py` 负责官方源配置和扫描历史持久化
- `fetchers.py` 负责按 `source_type` 拉列表页 / RSS / API
- `normalizers.py` 把源站结果统一成候选项结构
- `pipeline.py` 编排同步、去重、候选入库、原文抓取

### 3. 候选与证据门禁

官方源同步得到的内容不直接写正式记录，而是先生成候选更新。

门禁规则：

1. 命中 `allowed_domains`
2. 能抽到 `title`
3. 能抽到 `detail_url` 或 `artifact_url`
4. 至少拥有官方详情页快照或 PDF 文件之一

通过以上条件：

- 写入 `compliance_knowledge` 时 `authenticity_status='candidate'`
- `data_source` 标记为 `official_source:<source_name>`

如果同时满足：

1. 原文文件或官方 HTML 快照已存 COS
2. 标题、日期、机构、链接规则自洽
3. 官方域名与国家/机构白名单匹配

则允许提升到 `verified`。

### 4. 原文工件层

优先下载 PDF；没有 PDF 时保存 HTML 快照。

工件策略：

- PDF：沿用现有 `OfficialSourceIngestService`，下载并上传到 COS
- HTML：新增 HTML 快照上传能力，保存正文 HTML、抓取时间、SHA256

所有后续 RAG / 规格解析只从 COS 工件读取。

### 5. 调度替换

停用旧任务：

- `job_full_update`
- `job_incremental_check`

新增任务：

- `job_official_source_sync_daily`
  - 每天同步 `P1` 国家官方源
- `job_official_source_sync_weekly`
  - 每周同步 `P2` / `P3` 国家官方源
- `job_official_artifact_fetch`
  - 下载新增候选的官方原文
- `job_candidate_verification`
  - 对已有候选跑规则校验并提升状态
- `job_document_parse`
  - 对已抓到原文文件的候选创建/更新 `regulation_documents` 并进入解析链

周报保留，但统计口径调整为：

- 本周新增 `candidate`
- 本周新增 `verified`
- 本周新增工件数
- 本周新增隔离/可疑数

## 第一批官方源

首批接入：

- `EU`：`EUR-Lex`
- `GB`：`legislation.gov.uk`
- `US`：`NIST CSRC`、`FCC`
- `JP`：`METI`、`IPA`
- `SG`：`CSA`

第二批预留：

- `AU`
- `CA`
- `KR`
- `CN`

其他国家先暂停自动更新，等待补齐官方源。

## API 与后台

新增后台官方源管理接口：

- `GET /api/official-sources`
- `POST /api/official-sources`
- `PUT /api/official-sources/{id}`
- `POST /api/official-sources/{id}/sync`
- `GET /api/official-sources/{id}/history`

任务页文案调整：

- “全量更新” 改为 “官方源同步”
- 增加 “工件抓取” 与 “候选校验” 手动触发入口

## 错误处理

1. 源站列表页失败：记录 `last_error`，不影响其他源
2. PDF 下载失败：记录 `source_download_status='failed'`
3. 页面存在但抽取不到候选：记录为 `history`，不入库
4. 快照已存在且哈希未变：跳过重复下载

## 测试

1. 源注册表 CRUD
2. `rss/html_list/pdf_index` 抓取器最小回归
3. 官方源同步写入 `candidate`
4. 工件下载到 COS
5. 调度器新任务触发
6. 旧 `CollectorEngine` 不再被调度器和后台任务入口调用

## 非目标

1. 本轮不继续增强 AI 搜索能力
2. 本轮不一次性接入全部国家官方源
3. 本轮不自动把所有候选直接升级为 `verified`
