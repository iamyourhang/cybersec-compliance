# LLM Channel Router Design

## 背景

当前项目的 AI 能力主要依赖固定写死的 Provider 组合：

- 火山引擎
- 阿里百炼
- DeepSeek

这套方案能工作，但扩展性有限：

- 无法方便接入任意 OpenAI 兼容中转站或私有代理地址
- 通道配置主要依赖 `.env`，运营调整需要重启服务
- 失败降级逻辑与厂商配置耦合，无法抽象成通用通道池
- 缺少“额度用完后自动摘除并切到下一个通道”的明确机制

目标是将当前固定 ProviderManager 重构为“通道池 + 路由器”的模型，同时保持现有业务能力兼容，包括：

- 文档原文 AI 解析
- 法规问答 RAG 总结
- 飞书机器人问答

## 目标

本次设计目标：

1. 支持任意 `base_url + api_key + model` 的 OpenAI 兼容接口
2. 保留火山引擎联网搜索特性
3. 仅在识别到“额度用完”时自动切换到下一个通道
4. 支持后台人工维护通道池，并允许人工标记“额度耗尽”或“暂停”
5. 保留 `.env` 作为兜底默认通道来源
6. 统一文档解析、RAG、飞书三条链路的 AI 调用入口

## 非目标

本次不处理以下内容：

- 不将 `429 限流`、`超时`、`5xx`、内容安全拦截作为自动切换条件
- 不做动态按成本、延迟、成功率的智能调度
- 不做每通道详细额度统计或自动读取账户余额
- 不做多租户隔离
- 不把 embedding 通道池与 chat 通道池在第一版统一

## 方案概览

推荐方案为“数据库通道池 + `.env` 兜底”的双模式：

1. 系统优先从数据库读取启用通道
2. 如果数据库没有可用通道，则回退到 `.env` 中定义的默认通道
3. 所有业务调用统一走 `ChannelRouter`
4. `ChannelRouter` 负责：
   - 按优先级选择通道
   - 跳过禁用、暂停、额度耗尽通道
   - 识别额度耗尽并自动摘除
   - 把通道事件写入事件表

## 核心概念

### 1. 通道

通道是一次可调用的 LLM 访问配置，不等同于厂商。

一个通道至少包含：

- 名称
- 协议适配类型
- `base_url`
- `api_key`
- `model`
- 优先级
- 是否启用
- 是否支持联网搜索

### 2. 协议适配器

第一版只支持两个适配器：

- `openai_compatible`
- `volcengine_search`

适配器的职责是把统一的 chat 请求转换成不同供应商需要的调用参数。

#### openai_compatible

适用于：

- OpenAI 官方兼容接口
- 中转站
- 私有代理服务
- DashScope 兼容模式
- DeepSeek OpenAI 兼容地址

#### volcengine_search

适用于：

- 需要火山引擎联网搜索能力的场景
- 通过 `extra_body.search_config` 传递联网搜索参数的接口

### 3. 通道状态

调度时只关心三类布尔状态：

- `enabled`
- `manual_pause`
- `quota_exhausted`

只有满足以下条件的通道才会进入候选列表：

- `enabled = true`
- `manual_pause = false`
- `quota_exhausted = false`

## 调度逻辑

### 请求流程

所有 AI 调用统一走：

`ChannelRouter.chat(messages, temperature, max_tokens, enable_web_search, ...)`

内部流程：

1. 读取当前可用通道列表
2. 按 `priority` 升序排序
3. 依次尝试每个通道
4. 任一成功则立即返回
5. 若失败且错误被识别为“额度用完”，则：
   - 标记当前通道 `quota_exhausted = true`
   - 写入事件日志
   - 尝试下一个通道
6. 若失败但不是“额度用完”，则：
   - 不切换通道
   - 维持当前适配器已有重试策略
   - 最终直接返回该错误

### 为什么只在额度用完时切换

这是用户明确要求。这样做的好处是：

- 避免因为短时波动导致通道频繁抖动
- 保持当前主通道的稳定优先级
- 降低跨通道行为差异导致的输出波动

代价是：

- 单通道超时或 5xx 时不会自动切到下一个
- 某些中转站故障仍需要人工介入

这是当前需求下可以接受的取舍。

## 额度用完识别

第一版采用“双来源”机制。

### 自动识别

当适配器抛出错误时，系统会检查错误码或错误文本，命中下列信号即视为“额度用完”：

- `insufficient_quota`
- `quota exceeded`
- `exceeded your current quota`
- `insufficient balance`
- `balance not enough`
- `余额不足`
- `额度已用完`

自动识别命中后：

- 通道写库为 `quota_exhausted = true`
- 记录 `last_error`
- 更新 `last_checked_at`
- 写入事件表

### 人工标记

后台可直接将通道置为：

- 暂停
- 额度耗尽

也可手工恢复：

- 清除暂停
- 清除额度耗尽

### 优先级规则

人工暂停优先级最高：

- `manual_pause = true` 一定跳过
- `quota_exhausted = true` 一定跳过

自动识别不会覆盖人工暂停状态。

## 配置来源

### 数据库通道池

数据库通道池是主配置来源，适用于：

- 日常运营维护
- 临时切换中转站
- 调整优先级
- 手工标记耗尽

### `.env` 兜底

当数据库没有任何可用通道时，系统读取 `.env` 中的默认通道配置。

兜底通道只用于：

- 首次部署
- 数据库未配置时的保底可用性
- 后台配置误删或全部停用时的恢复路径

`.env` 通道不参与后台编辑。

## 数据库设计

### 表一：`llm_channels`

建议字段：

- `id`
- `name`
- `provider_type`
- `base_url`
- `api_key_encrypted`
- `model`
- `priority`
- `enabled`
- `supports_web_search`
- `quota_exhausted`
- `manual_pause`
- `last_error`
- `last_checked_at`
- `created_at`
- `updated_at`

说明：

- `api_key` 必须加密存储，不以明文落库
- `priority` 数字越小优先级越高
- `supports_web_search` 由通道配置决定，不完全由适配器推导

### 表二：`llm_channel_events`

建议字段：

- `id`
- `channel_id`
- `event_type`
- `message`
- `raw_error`
- `created_at`

建议事件类型：

- `quota_exhausted_detected`
- `manual_paused`
- `manual_resumed`
- `quota_cleared`
- `request_failed`
- `request_succeeded`

第一版中 `request_succeeded` 可以不写，只在需要时再加，避免事件表膨胀过快。

## 后端模块设计

### 1. `ChannelRepository`

职责：

- 读写通道主表
- 读写事件表
- 查询可用通道列表
- 更新通道状态

### 2. `ChannelRouter`

职责：

- 拉取候选通道
- 按优先级调度
- 调用对应适配器
- 识别额度耗尽
- 自动摘除通道
- 记录事件

### 3. 适配器层

保留现有 Provider 类，但收敛为协议适配器：

- `OpenAICompatProvider`
- `VolcengineProvider`

原有固定写死的工厂逻辑将被削弱，更多由数据库通道实例驱动。

## API 设计

后台管理接口建议如下：

- `GET /api/llm-channels`
- `POST /api/llm-channels`
- `PUT /api/llm-channels/{id}`
- `POST /api/llm-channels/{id}/pause`
- `POST /api/llm-channels/{id}/resume`
- `POST /api/llm-channels/{id}/mark-quota-exhausted`
- `POST /api/llm-channels/{id}/clear-quota-exhausted`
- `GET /api/llm-channels/{id}/events`
- `POST /api/llm-channels/test`

### 测试接口用途

`/api/llm-channels/test` 用于：

- 验证 `base_url + api_key + model` 是否可连通
- 辅助排查是否为额度用完
- 校验模型名称是否正确

第一版只需要返回：

- success / failure
- 错误摘要
- 是否识别为额度用完

## 后台页面设计

新增独立页面：`AI 通道管理`

不建议塞进“系统设置”，避免配置过于隐藏。

### 列表页展示字段

- 名称
- 协议类型
- 模型
- `base_url`
- 优先级
- 启用状态
- 暂停状态
- 额度耗尽状态
- 最近错误
- 最近检查时间

### 列表页操作

- 新增
- 编辑
- 暂停
- 恢复
- 标记额度耗尽
- 清除额度耗尽
- 上移优先级
- 下移优先级
- 测试连通性
- 查看事件日志

### 编辑页字段

- 名称
- 协议类型
- `base_url`
- `api_key`
- `model`
- 优先级
- 是否启用
- 是否支持联网搜索

要求：

- `api_key` 默认不回显明文
- 允许覆盖更新
- `base_url` 和 `model` 必填

## 与现有业务的衔接

以下入口都改为依赖 `ChannelRouter.chat(...)`：

- 文档原文解析
- RAG 回答生成
- 飞书问答意图处理

Embedding 暂时保留独立配置，不纳入本次 chat 通道池重构范围。

## 错误处理策略

### 额度用完

- 标记当前通道为 `quota_exhausted`
- 记录事件
- 自动尝试下一个通道

### 非额度错误

- 不切通道
- 沿用当前适配器内置重试
- 若最终失败，则将错误返回业务调用方

### 无可用通道

统一返回清晰错误：

`当前无可用 AI 通道，请在后台检查额度或恢复被暂停通道。`

## 安全要求

- `api_key` 必须加密存储
- 日志中不打印完整 key
- 后台接口必须要求登录
- 事件表中的 `raw_error` 需要脱敏，避免回写敏感请求头或密钥

## 测试策略

### 单元测试

- 路由器按优先级选择第一个可用通道
- 命中额度耗尽错误后自动切换到下一个
- 普通错误不会自动切通道
- 人工暂停和额度耗尽状态会被正确跳过
- 数据库为空时会回退到 `.env` 通道

### 集成测试

- 后台新增通道后能立即参与调度
- 人工标记额度耗尽后，下一次请求跳过该通道
- 清除额度耗尽后，通道恢复可用

### 后台验收

- 页面可新增/编辑/暂停/恢复通道
- 可查看最近错误和事件日志
- 可手工清除“额度耗尽”状态

## 实施顺序

建议分三步：

1. 数据库与后端基础层
   - 新增数据表
   - 新增 `ChannelRepository`
   - 新增 `ChannelRouter`
   - 打通 `.env` 兜底

2. 业务接入
   - 文档解析接入 `ChannelRouter`
   - RAG 总结接入 `ChannelRouter`
   - 飞书问答接入 `ChannelRouter`

3. 后台管理
   - 通道管理 API
   - 通道管理前端页面
   - 连通性测试与事件查看

## 风险与取舍

### 风险

- 中转站错误格式不统一，自动识别“额度用完”可能不完全可靠
- 如果人工误标记通道耗尽，可能导致优先通道被长期跳过
- 加密存储实现如果处理不当，可能影响密钥迁移

### 对策

- 自动识别与人工控制并存
- 后台提供清除耗尽状态
- `.env` 保底通道保持系统可恢复

## 结论

本方案将当前“固定厂商 ProviderManager”升级为“可运营的通道池路由器”，并严格遵守以下关键约束：

- 兼容性优先
- 任意 OpenAI 兼容地址可接入
- 只在额度用完时自动切换
- 支持自动识别 + 人工标记
- 后台可维护，`.env` 可兜底

这是当前需求下兼容性、稳定性、可维护性最平衡的设计。
