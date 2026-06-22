from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from admin.api import auth
from admin.api.auth import get_current_user, require_admin_user


def _client(monkeypatch):
    monkeypatch.setattr(
        auth,
        "_configured_users",
        lambda: {
            "legacy": {"password": "old-pass", "role": "viewer"},
            "waz": {"password": "new-pass", "role": "admin"},
        },
    )
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth")

    @app.get("/viewer")
    async def viewer_route(current_user: str = Depends(get_current_user)):
        return {"username": current_user}

    @app.get("/admin")
    async def admin_route(current_user: str = Depends(require_admin_user)):
        return {"username": current_user}

    return TestClient(app)


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()


def test_legacy_user_is_viewer_and_cannot_access_admin(monkeypatch):
    client = _client(monkeypatch)
    token = _login(client, "legacy", "old-pass")

    assert token["role"] == "viewer"
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    assert client.get("/viewer", headers=headers).status_code == 200

    response = client.get("/admin", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "需要管理员权限"


def test_super_user_is_admin(monkeypatch):
    client = _client(monkeypatch)
    token = _login(client, "waz", "new-pass")

    assert token["role"] == "admin"
    headers = {"Authorization": f"Bearer {token['access_token']}"}

    response = client.get("/admin", headers=headers)

    assert response.status_code == 200
    assert response.json()["username"] == "waz"
