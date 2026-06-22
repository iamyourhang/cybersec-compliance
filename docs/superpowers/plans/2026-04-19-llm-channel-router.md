# LLM Channel Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前固定 ProviderManager 重构为“数据库通道池 + `.env` 兜底 + 额度耗尽自动切换”的统一路由层，并接入文档解析、RAG 和飞书链路。

**Architecture:** 新增 `llm_channels` / `llm_channel_events` 作为通道配置与事件来源，后端以 `ChannelRepository + ChannelRouter` 为核心，适配层仅保留 `openai_compatible` 与 `volcengine_search` 两类协议实现。业务调用统一走 `ChannelRouter.chat(...)`，当数据库无可用通道时回退到 `.env` 默认通道。

**Tech Stack:** FastAPI, PostgreSQL, psycopg2, Pydantic Settings, Vue 3, OpenAI-compatible SDK

---

## File Map

### New Files

- `database/migrations/V4__llm_channels.sql`
  - 新增 `llm_channels`、`llm_channel_events`
- `app/security/crypto.py`
  - `api_key` 加解密工具
- `collector/providers/router_models.py`
  - 通道实体、路由层错误类型
- `collector/providers/channel_repository.py`
  - 通道主表与事件表读写
- `collector/providers/channel_router.py`
  - 统一通道路由器
- `admin/api/routes/llm_channels.py`
  - 后台通道管理接口
- `admin/frontend-vue/src/views/LlmChannels.vue`
  - 通道管理页
- `tests/test_channel_router.py`
  - 路由器单测
- `tests/test_llm_channels_route.py`
  - 后台 API 测试

### Modified Files

- `config/settings.py`
  - 新增 `.env` 兜底通道配置与加密密钥配置
- `config/.env.example`
  - 补充默认通道池示例
- `collector/providers/base.py`
  - 保留适配器基类，但剥离固定 ProviderManager 的主角色
- `collector/providers/factory.py`
  - 从“固定厂商组装”改为“按通道定义构造适配器”
- `collector/providers/volcengine.py`
  - 增加额度耗尽识别映射
- `collector/providers/dashscope.py`
  - 增加通用 OpenAI 兼容错误识别映射
- `collector/document/parse_service.py`
  - 改为依赖 `ChannelRouter`
- `collector/document/answer_service.py`
  - 改为依赖 `ChannelRouter`
- `feishu_bot/intent_parser.py`
  - 不改路由逻辑，保留现有 intent 解析
- `feishu_bot/query_handler.py`
  - 改为依赖 `ChannelRouter`
- `admin/api/main.py`
  - 注册通道管理路由
- `admin/frontend-vue/src/router/index.js`
  - 注册通道管理页
- `admin/frontend-vue/src/views/Layout.vue`
  - 增加导航入口
- `admin/frontend-vue/src/api/index.js`
  - 增加通道管理 API 封装

### Existing Files To Reuse

- `collector/providers/volcengine.py`
- `collector/providers/dashscope.py`
- `admin/api/routes/documents.py`
- `collector/document/rag_service.py`

---

### Task 1: 数据库与配置基础

**Files:**
- Create: `database/migrations/V4__llm_channels.sql`
- Modify: `config/settings.py`
- Modify: `config/.env.example`
- Create: `app/security/crypto.py`
- Test: `tests/test_channel_router.py`

- [ ] **Step 1: Write the failing migration/config test**

```python
def test_settings_loads_llm_router_fallback_json():
    from config.settings import Settings

    settings = Settings(_env_file=None, LLM_ROUTER_FALLBACK_JSON='[{"name":"fallback","provider_type":"openai_compatible","base_url":"https://example.com/v1","api_key":"k","model":"gpt-4.1","priority":1,"enabled":true}]')

    channels = settings.llm_router_fallback
    assert len(channels) == 1
    assert channels[0]["name"] == "fallback"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance && ./.venv/bin/pytest tests/test_channel_router.py::test_settings_loads_llm_router_fallback_json -q`

Expected: FAIL with missing `llm_router_fallback` or equivalent attribute error.

- [ ] **Step 3: Write migration and settings support**

```sql
CREATE TABLE IF NOT EXISTS llm_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    provider_type VARCHAR(50) NOT NULL,
    base_url TEXT NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    model VARCHAR(200) NOT NULL,
    priority INT NOT NULL DEFAULT 100,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    supports_web_search BOOLEAN NOT NULL DEFAULT FALSE,
    quota_exhausted BOOLEAN NOT NULL DEFAULT FALSE,
    manual_pause BOOLEAN NOT NULL DEFAULT FALSE,
    last_error TEXT,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS llm_channel_events (
    id BIGSERIAL PRIMARY KEY,
    channel_id UUID NOT NULL REFERENCES llm_channels(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    message TEXT,
    raw_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

```python
class Settings(BaseSettings):
    llm_router_secret: str = ""

    @property
    def llm_router_fallback(self) -> list[dict]:
        raw = os.getenv("LLM_ROUTER_FALLBACK_JSON", "[]")
        return json.loads(raw)
```

```python
from cryptography.fernet import Fernet

def encrypt_secret(secret: str, key: str) -> str:
    return Fernet(key.encode()).encrypt(secret.encode()).decode()

def decrypt_secret(cipher_text: str, key: str) -> str:
    return Fernet(key.encode()).decrypt(cipher_text.encode()).decode()
```

- [ ] **Step 4: Run targeted tests and syntax checks**

Run:

```bash
cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance
./.venv/bin/pytest tests/test_channel_router.py::test_settings_loads_llm_router_fallback_json -q
python3 -m py_compile config/settings.py app/security/crypto.py
```

Expected: PASS for test, no syntax errors.

- [ ] **Step 5: Checkpoint**

```bash
git add database/migrations/V4__llm_channels.sql config/settings.py config/.env.example app/security/crypto.py tests/test_channel_router.py
git commit -m "feat: add llm channel schema and fallback settings"
```

If the workspace is not a git repo, record this as a manual checkpoint in your session notes and continue.

---

### Task 2: 通道仓储与统一路由器

**Files:**
- Create: `collector/providers/router_models.py`
- Create: `collector/providers/channel_repository.py`
- Create: `collector/providers/channel_router.py`
- Modify: `collector/providers/base.py`
- Modify: `collector/providers/factory.py`
- Modify: `collector/providers/volcengine.py`
- Modify: `collector/providers/dashscope.py`
- Test: `tests/test_channel_router.py`

- [ ] **Step 1: Write the failing router selection tests**

```python
def test_channel_router_skips_quota_exhausted_channel():
    repo = FakeChannelRepository([
        {"id": "1", "name": "a", "provider_type": "openai_compatible", "quota_exhausted": True, "manual_pause": False, "enabled": True, "priority": 1},
        {"id": "2", "name": "b", "provider_type": "openai_compatible", "quota_exhausted": False, "manual_pause": False, "enabled": True, "priority": 2},
    ])
    router = ChannelRouter(repository=repo, adapter_factory=fake_factory({"2": "ok"}))

    response = router.chat(messages=[{"role": "user", "content": "hi"}])

    assert response.content == "ok"
    assert repo.used_channel_ids == ["2"]
```

```python
def test_channel_router_marks_quota_exhausted_and_falls_through():
    repo = FakeChannelRepository([
        {"id": "1", "name": "a", "provider_type": "openai_compatible", "quota_exhausted": False, "manual_pause": False, "enabled": True, "priority": 1},
        {"id": "2", "name": "b", "provider_type": "openai_compatible", "quota_exhausted": False, "manual_pause": False, "enabled": True, "priority": 2},
    ])
    router = ChannelRouter(repository=repo, adapter_factory=fake_factory({"1": QuotaExhaustedError("quota"), "2": "ok"}))

    response = router.chat(messages=[{"role": "user", "content": "hi"}])

    assert response.content == "ok"
    assert repo.quota_marked == ["1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance && ./.venv/bin/pytest tests/test_channel_router.py -q`

Expected: FAIL with missing `ChannelRouter`, `QuotaExhaustedError`, or repository implementation.

- [ ] **Step 3: Implement repository models and routing**

```python
@dataclass
class ChannelConfig:
    id: str
    name: str
    provider_type: str
    base_url: str
    api_key: str
    model: str
    priority: int
    enabled: bool
    supports_web_search: bool
    quota_exhausted: bool
    manual_pause: bool
```

```python
class QuotaExhaustedError(RuntimeError):
    pass


class ChannelRouter:
    def __init__(self, repository: ChannelRepository, adapter_factory: Callable[[ChannelConfig], BaseProvider]):
        self._repository = repository
        self._adapter_factory = adapter_factory

    def chat(self, messages: list[dict], **kwargs):
        channels = self._repository.list_routable_channels()
        last_error = None
        for channel in channels:
            adapter = self._adapter_factory(channel)
            try:
                return adapter.chat(messages=messages, **kwargs)
            except QuotaExhaustedError as exc:
                self._repository.mark_quota_exhausted(channel.id, str(exc))
                self._repository.add_event(channel.id, "quota_exhausted_detected", str(exc), str(exc))
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                raise
        raise RuntimeError("当前无可用 AI 通道，请在后台检查额度或恢复被暂停通道。") from last_error
```

```python
def build_provider_from_channel(channel: ChannelConfig) -> BaseProvider:
    if channel.provider_type == "volcengine_search":
        return VolcengineProvider(...)
    return OpenAICompatProvider(...)
```

- [ ] **Step 4: Teach adapters to raise `QuotaExhaustedError` only for quota cases**

```python
def _is_quota_exhausted_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in (
        "insufficient_quota",
        "quota exceeded",
        "exceeded your current quota",
        "insufficient balance",
        "balance not enough",
        "余额不足",
        "额度已用完",
    ))
```

```python
except APIError as e:
    if _is_quota_exhausted_error(e):
        raise QuotaExhaustedError(str(e)) from e
    raise
```

- [ ] **Step 5: Run full router test suite**

Run:

```bash
cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance
./.venv/bin/pytest tests/test_channel_router.py -q
python3 -m py_compile collector/providers/router_models.py collector/providers/channel_repository.py collector/providers/channel_router.py collector/providers/factory.py collector/providers/volcengine.py collector/providers/dashscope.py
```

Expected: PASS and no syntax errors.

- [ ] **Step 6: Checkpoint**

```bash
git add collector/providers/router_models.py collector/providers/channel_repository.py collector/providers/channel_router.py collector/providers/base.py collector/providers/factory.py collector/providers/volcengine.py collector/providers/dashscope.py tests/test_channel_router.py
git commit -m "feat: add llm channel router and quota failover"
```

If the workspace is not a git repo, record this as a manual checkpoint in your session notes and continue.

---

### Task 3: 接入文档解析、RAG 与飞书

**Files:**
- Modify: `collector/document/parse_service.py`
- Modify: `collector/document/answer_service.py`
- Modify: `collector/document/rag_service.py`
- Modify: `feishu_bot/query_handler.py`
- Test: `tests/test_parse_service.py`
- Test: `tests/test_answer_service.py`
- Test: `tests/test_rag_route.py`

- [ ] **Step 1: Write the failing integration tests**

```python
def test_parse_service_uses_channel_router(monkeypatch):
    used = {}
    monkeypatch.setattr(parse_service_module, "get_channel_router", lambda: FakeRouter(used))
    ...
    service.parse_document("doc-1", write_to_knowledge=False)
    assert used["called"] is True
```

```python
def test_answer_service_uses_channel_router_summary(monkeypatch):
    router = FakeRouter(result_text="grounded answer")
    service = AnswerService(router=router)
    result = service.answer(question="q", retrieval={"hits": strong_hits, "related_records": []})
    assert result["answer"] == "grounded answer"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance
./.venv/bin/pytest tests/test_parse_service.py tests/test_answer_service.py tests/test_rag_route.py -q
```

Expected: FAIL because services still use old provider manager path.

- [ ] **Step 3: Refactor services to depend on router**

```python
from collector.providers.channel_router import get_channel_router

class DocumentParseService:
    def __init__(self, router=None):
        self._router = router or get_channel_router()

    ...
    response = self._router.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2500,
        enable_web_search=False,
    )
```

```python
class AnswerService:
    def __init__(self, router=None, summarizer=None):
        self._router = router or get_channel_router()
        self._summarizer = summarizer

    def _summarize(self, prompt: str) -> str:
        if self._summarizer:
            return self._summarizer(prompt)
        resp = self._router.chat(messages=[{"role": "user", "content": prompt}], temperature=0.1, max_tokens=1200, enable_web_search=False)
        return resp.content
```

```python
def query_rag(...):
    service = RAGService()
    return service.ask(...)
```

- [ ] **Step 4: Run the integration tests again**

Run:

```bash
cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance
./.venv/bin/pytest tests/test_parse_service.py tests/test_answer_service.py tests/test_rag_route.py -q
python3 -m py_compile collector/document/parse_service.py collector/document/answer_service.py collector/document/rag_service.py feishu_bot/query_handler.py
```

Expected: PASS and no syntax errors.

- [ ] **Step 5: Checkpoint**

```bash
git add collector/document/parse_service.py collector/document/answer_service.py collector/document/rag_service.py feishu_bot/query_handler.py tests/test_parse_service.py tests/test_answer_service.py tests/test_rag_route.py
git commit -m "refactor: route ai calls through channel router"
```

If the workspace is not a git repo, record this as a manual checkpoint in your session notes and continue.

---

### Task 4: 后台通道管理 API

**Files:**
- Create: `admin/api/routes/llm_channels.py`
- Modify: `admin/api/main.py`
- Test: `tests/test_llm_channels_route.py`

- [ ] **Step 1: Write the failing API tests**

```python
def test_list_llm_channels_returns_items(client, fake_repo):
    response = client.get("/api/llm-channels", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "primary"
```

```python
def test_mark_quota_exhausted_updates_status(client, fake_repo):
    response = client.post("/api/llm-channels/ch-1/mark-quota-exhausted", headers=auth_headers())
    assert response.status_code == 200
    assert fake_repo.marked == ["ch-1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance && ./.venv/bin/pytest tests/test_llm_channels_route.py -q`

Expected: FAIL with missing route module or route registration.

- [ ] **Step 3: Implement route handlers**

```python
router = APIRouter()

@router.get("/")
async def list_channels(current_user: str = Depends(get_current_user)):
    repo = get_channel_repository()
    return {"items": repo.list_all(), "total": len(repo.list_all())}

@router.post("/{channel_id}/mark-quota-exhausted")
async def mark_quota_exhausted(channel_id: str, current_user: str = Depends(get_current_user)):
    repo = get_channel_repository()
    repo.mark_quota_exhausted(channel_id, "manual mark")
    repo.add_event(channel_id, "quota_exhausted_detected", "manual mark", None)
    return {"message": "已标记额度耗尽", "id": channel_id}
```

```python
app.include_router(llm_channels_router, prefix="/api/llm-channels", tags=["AI通道管理"])
```

- [ ] **Step 4: Run route tests and import smoke**

Run:

```bash
cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance
./.venv/bin/pytest tests/test_llm_channels_route.py -q
./.venv/bin/python - <<'PY'
from admin.api.main import app
print(any(route.path.startswith("/api/llm-channels") for route in app.routes))
PY
```

Expected: PASS and printed `True`.

- [ ] **Step 5: Checkpoint**

```bash
git add admin/api/routes/llm_channels.py admin/api/main.py tests/test_llm_channels_route.py
git commit -m "feat: add llm channel management api"
```

If the workspace is not a git repo, record this as a manual checkpoint in your session notes and continue.

---

### Task 5: 后台通道管理页面

**Files:**
- Create: `admin/frontend-vue/src/views/LlmChannels.vue`
- Modify: `admin/frontend-vue/src/router/index.js`
- Modify: `admin/frontend-vue/src/views/Layout.vue`
- Modify: `admin/frontend-vue/src/api/index.js`

- [ ] **Step 1: Write the failing page/API wiring expectation**

```javascript
// manual verification target
// route "/llm-channels" exists
// sidebar contains "AI 通道管理"
// page loads /api/llm-channels and renders rows
```

- [ ] **Step 2: Verify the route does not exist yet**

Run:

```bash
cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance
rg -n "llm-channels|AI 通道管理" admin/frontend-vue/src
```

Expected: no matches or only comments/test placeholders.

- [ ] **Step 3: Implement the page and API client**

```javascript
export const llmChannelApi = {
  list: () => api.get('/llm-channels'),
  create: (data) => api.post('/llm-channels', data),
  update: (id, data) => api.put(`/llm-channels/${id}`, data),
  pause: (id) => api.post(`/llm-channels/${id}/pause`),
  resume: (id) => api.post(`/llm-channels/${id}/resume`),
  markQuotaExhausted: (id) => api.post(`/llm-channels/${id}/mark-quota-exhausted`),
  clearQuotaExhausted: (id) => api.post(`/llm-channels/${id}/clear-quota-exhausted`),
}
```

```javascript
{ path: 'llm-channels', name: 'llm-channels', component: () => import('@/views/LlmChannels.vue') }
```

```javascript
{ path: '/llm-channels', icon: '◨', label: 'AI 通道管理' }
```

- [ ] **Step 4: Build and verify the frontend**

Run:

```bash
cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance/admin/frontend-vue
npm run build
```

Expected: build succeeds and emits updated bundle assets.

- [ ] **Step 5: Checkpoint**

```bash
git add admin/frontend-vue/src/views/LlmChannels.vue admin/frontend-vue/src/router/index.js admin/frontend-vue/src/views/Layout.vue admin/frontend-vue/src/api/index.js
git commit -m "feat: add llm channel management ui"
```

If the workspace is not a git repo, record this as a manual checkpoint in your session notes and continue.

---

### Task 6: `.env` 兜底与端到端验收

**Files:**
- Modify: `collector/providers/channel_repository.py`
- Modify: `config/.env.example`
- Modify: `README.md`
- Test: `tests/test_channel_router.py`

- [ ] **Step 1: Write the failing fallback tests**

```python
def test_channel_router_uses_env_fallback_when_db_empty():
    repo = FakeChannelRepository([])
    router = ChannelRouter(repository=repo, adapter_factory=fake_factory({"fallback": "ok"}), fallback_channels=[
        ChannelConfig(id="fallback", name="fallback", provider_type="openai_compatible", base_url="https://example.com/v1", api_key="k", model="gpt-4.1", priority=1, enabled=True, supports_web_search=False, quota_exhausted=False, manual_pause=False)
    ])

    response = router.chat(messages=[{"role": "user", "content": "hi"}])

    assert response.content == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance && ./.venv/bin/pytest tests/test_channel_router.py::test_channel_router_uses_env_fallback_when_db_empty -q`

Expected: FAIL because fallback path is not implemented yet.

- [ ] **Step 3: Implement fallback loading and docs**

```python
class ChannelRepository:
    def list_routable_channels(self) -> list[ChannelConfig]:
        rows = self._list_db_channels()
        if rows:
            return rows
        return self._load_env_fallback_channels()
```

```env
LLM_ROUTER_SECRET=replace_with_fernet_key
LLM_ROUTER_FALLBACK_JSON=[{"name":"fallback-openai","provider_type":"openai_compatible","base_url":"https://api.openai.com/v1","api_key":"replace_me","model":"gpt-4.1-mini","priority":1,"enabled":true,"supports_web_search":false}]
```

- [ ] **Step 4: Run end-to-end verification**

Run:

```bash
cd /Users/s1/Desktop/claude-coding/网安合规助手/work/cybersec-compliance
./.venv/bin/pytest tests/test_channel_router.py tests/test_llm_channels_route.py tests/test_parse_service.py tests/test_answer_service.py tests/test_rag_route.py -q
python3 -m py_compile collector/providers/channel_repository.py collector/providers/channel_router.py
```

Expected: full test set PASS, no syntax errors.

- [ ] **Step 5: Remote smoke verification**

Run on server:

```bash
systemctl restart cybersec-admin.service cybersec-feishu-bot.service
curl -s -X POST http://127.0.0.1:8080/api/auth/login -H 'Content-Type: application/x-www-form-urlencoded' --data 'username=wangan&password=dechi@123'
```

Expected: login returns token and existing document parsing / RAG flows still work.

- [ ] **Step 6: Checkpoint**

```bash
git add collector/providers/channel_repository.py config/.env.example README.md tests/test_channel_router.py
git commit -m "feat: add env fallback for llm channel router"
```

If the workspace is not a git repo, record this as a manual checkpoint in your session notes and continue.

---

## Spec Coverage Self-Review

- 通道池主表与事件表：Task 1
- 协议适配器与统一路由：Task 2
- 只在额度用完时切换：Task 2
- 文档解析 / RAG / 飞书统一接入：Task 3
- 后台 API 与页面：Task 4、Task 5
- `.env` 兜底：Task 6
- 自动识别 + 人工标记：Task 2、Task 4

无明显缺项。

## Placeholder Scan

- 无 `TBD` / `TODO`
- 所有代码步骤都给出最小实现方向
- 所有测试步骤都给出明确命令与预期结果

## Type Consistency Check

- 统一使用 `ChannelConfig`
- 统一使用 `QuotaExhaustedError`
- 统一使用 `ChannelRouter.chat(...)`
- API 路径统一为 `/api/llm-channels`

无明显命名冲突。
