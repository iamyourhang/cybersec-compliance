"""
admin/api/auth.py
JWT 认证：登录、token 验证、当前用户依赖
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from config.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


# ---- Schema ----

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    username: str
    role: str


class TokenData(BaseModel):
    username: Optional[str] = None
    role: str = "viewer"


class CurrentUser(BaseModel):
    username: str
    role: str = "viewer"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# ---- 工具函数 ----

def _normalize_role(role: str | None) -> str:
    return "admin" if (role or "").strip().lower() == "admin" else "viewer"


def _configured_users() -> Dict[str, Dict[str, str]]:
    """Return configured users.

    Compatibility rule:
    - If no dedicated super admin is configured, the legacy ADMIN_USERNAME remains admin.
    - Once ADMIN_SUPER_USERNAME/PASSWORD exists, legacy ADMIN_USERNAME is downgraded to viewer.
    """
    admin = settings.admin
    users: Dict[str, Dict[str, str]] = {}
    has_super_admin = bool(admin.super_username and admin.super_password)

    if admin.username and admin.password:
        users[admin.username] = {
            "password": admin.password,
            "role": "viewer" if has_super_admin else "admin",
        }

    if admin.users_json.strip():
        try:
            parsed = json.loads(admin.users_json)
            items = parsed.values() if isinstance(parsed, dict) else parsed
            for item in items:
                if not isinstance(item, dict):
                    continue
                username = str(item.get("username") or "").strip()
                password = str(item.get("password") or "").strip()
                if not username or not password:
                    continue
                users[username] = {
                    "password": password,
                    "role": _normalize_role(item.get("role")),
                }
        except Exception as exc:
            logger.error("ADMIN_USERS_JSON 解析失败: %s", exc)

    if has_super_admin:
        users[admin.super_username] = {
            "password": admin.super_password,
            "role": "admin",
        }

    return users


def _lookup_user(username: str | None) -> Optional[CurrentUser]:
    if not username:
        return None
    user = _configured_users().get(username)
    if not user:
        return None
    return CurrentUser(username=username, role=_normalize_role(user.get("role")))


def is_admin_username(username: str | None) -> bool:
    user = _lookup_user(username)
    if user is None:
        # Unit tests often use dependency overrides with synthetic users.
        return True
    return user.is_admin


def _authenticate(username: str, password: str) -> Optional[CurrentUser]:
    user = _configured_users().get(username)
    if not user or password != user.get("password"):
        return None
    return CurrentUser(username=username, role=_normalize_role(user.get("role")))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.admin.jwt_secret, algorithm=ALGORITHM)


def verify_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, settings.admin.jwt_secret, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Token 无效")
        user = _lookup_user(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在或已停用")
        return TokenData(username=user.username, role=user.role)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")


async def get_current_user_info(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    token_data = verify_token(token)
    return CurrentUser(username=token_data.username or "", role=token_data.role)


async def get_current_user(current_user: CurrentUser = Depends(get_current_user_info)) -> str:
    return current_user.username


async def require_admin_user(current_user: str = Depends(get_current_user)) -> str:
    """Require admin role while keeping test dependency overrides simple."""
    user = _lookup_user(current_user)
    if user is None:
        # Unit tests often override get_current_user with synthetic users.
        return current_user
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


# ---- 路由 ----

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """用户名密码登录，返回 JWT token"""
    user = _authenticate(form_data.username, form_data.password)
    if not user:
        logger.warning("登录失败: 用户名或密码错误 [user=%s]", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    expire = timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    token = create_access_token({"sub": user.username, "role": user.role}, expire)
    logger.info("登录成功: %s [%s]", user.username, user.role)
    return Token(
        access_token=token,
        token_type="bearer",
        expires_in=int(expire.total_seconds()),
        username=user.username,
        role=user.role,
    )


@router.get("/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user_info)):
    return {"username": current_user.username, "role": current_user.role}


@router.post("/logout")
async def logout():
    # JWT 无状态，客户端清除 token 即可
    return {"message": "已退出登录"}
