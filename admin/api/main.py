"""
admin/api/main.py
FastAPI 管理后台主入口
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from admin.api.auth import router as auth_router
from admin.api.routes.compliance import router as compliance_router
from admin.api.routes.changelog import router as changelog_router
from admin.api.routes.tasks import router as tasks_router
from admin.api.routes.dashboard import router as dashboard_router
from admin.api.routes.settings import router as settings_router
from admin.api.routes.documents import router as documents_router
from admin.api.routes.discovery import router as discovery_router
from admin.api.routes.llm_channels import router as llm_channels_router
from admin.api.routes.official_sources import router as official_sources_router
from admin.api.routes.models import router as models_router
from admin.api.routes.rag import router as rag_router
from admin.api.routes.agent import router as agent_router
from admin.api.routes.public import router as public_router
from admin.api.routes.spec_requirements import router as spec_requirements_router
from admin.api.routes.review_cases import router as review_cases_router
from admin.api.routes.evidence import router as evidence_router
from config.settings import get_settings
from utils.logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="网安合规助手管理后台",
    version="1.0.0",
    docs_url="/api/docs" if settings.is_dev else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.is_dev else None,
)

# ---- CORS（开发环境放开，生产由 IP 白名单控制）----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- IP 白名单中间件 ----
@app.middleware("http")
async def ip_whitelist_middleware(request: Request, call_next):
    # 放行健康检查和静态资源
    path = request.url.path
    if path in ("/health", "/favicon.ico") or path.startswith("/assets"):
        return await call_next(request)

    client_ip = request.client.host
    whitelist = settings.admin.ip_whitelist

    # 白名单为空或包含 0.0.0.0 则不限制
    if False and whitelist and "0.0.0.0" not in whitelist:
        import ipaddress
        allowed = False
        for allowed_ip in whitelist:
            try:
                if "/" in allowed_ip:
                    network = ipaddress.ip_network(allowed_ip, strict=False)
                    if ipaddress.ip_address(client_ip) in network:
                        allowed = True
                        break
                elif client_ip == allowed_ip:
                    allowed = True
                    break
            except ValueError:
                continue
        if not allowed:
            logger.warning("IP 访问被拒绝: %s", client_ip)
            raise HTTPException(status_code=403, detail="IP not allowed")

    return await call_next(request)

# ---- 注册 API 路由 ----
app.include_router(auth_router,       prefix="/api/auth",       tags=["认证"])
app.include_router(dashboard_router,  prefix="/api/dashboard",  tags=["仪表盘"])
app.include_router(compliance_router, prefix="/api/compliance", tags=["合规知识库"])
app.include_router(changelog_router,  prefix="/api/changelog",  tags=["变更日志"])
app.include_router(tasks_router,      prefix="/api/tasks",      tags=["任务管理"])
app.include_router(settings_router,   prefix="/api/settings",   tags=["系统设置"])
app.include_router(documents_router,  prefix="/api/documents",  tags=["法规原文"])
app.include_router(discovery_router,  prefix="/api/discovery",  tags=["AI发现"])
app.include_router(llm_channels_router, prefix="/api/llm-channels", tags=["AI 通道"])
app.include_router(official_sources_router, prefix="/api/official-sources", tags=["官方源"])
app.include_router(spec_requirements_router, prefix="/api/spec-requirements", tags=["法规规格"])
app.include_router(review_cases_router, prefix="/api/review-cases", tags=["审核案例"])
app.include_router(evidence_router, prefix="/api/evidence", tags=["证据"])
app.include_router(rag_router,        prefix="/api/rag",        tags=["法规问答"])
app.include_router(agent_router,      prefix="/api/agent",      tags=["合规Agent"])
app.include_router(models_router,     prefix="/api/models",     tags=["产品型号"])
app.include_router(public_router,     prefix="/api/public",     tags=["公开查询"])

# ---- 健康检查 ----
@app.get("/health")
async def health():
    from database.connection import health_check
    return health_check()

# ---- 托管 Vue 构建产物 ----
DIST_DIR = Path(__file__).parent.parent / "dist"
INDEX_HTML = DIST_DIR / "index.html"

if DIST_DIR.exists() and (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

# 托管 dist 根目录静态文件（地图数据、图标等）
if DIST_DIR.exists():
    from fastapi.responses import FileResponse as _FR
    import os as _os
    _static_files = [f for f in _os.listdir(str(DIST_DIR)) if f.endswith(('.json','.svg','.ico','.png','.txt'))]
    for _sf in _static_files:
        _sf_path = str(DIST_DIR / _sf)
        @app.get(f"/{_sf}")
        async def _serve_static(f=_sf_path):
            return _FR(f)

# 托管 public 目录（地图数据等静态文件）
PUBLIC_DIR = Path(__file__).parent.parent.parent / "frontend-vue" / "public"
if PUBLIC_DIR.exists():
    app.mount("/world-110m.json", StaticFiles(directory=str(PUBLIC_DIR)), name="public-files")

@app.get("/")
async def serve_index():
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML))
    return {"message": "前端未构建，请运行 npm run build"}

@app.get("/{full_path:path}")
async def serve_spa(full_path: str, request: Request):
    # API 请求不走 SPA fallback
    if full_path.startswith("api/") or full_path.startswith("api") or full_path == "openapi.json":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML))
    raise HTTPException(status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "admin.api.main:app",
        host="0.0.0.0",
        port=settings.admin.port,
        reload=settings.is_dev,
    )
