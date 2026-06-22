from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.api.auth import get_current_user
from admin.api.routes.tasks import router


def _build_client():
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: "tester"
    app.include_router(router, prefix="/api/tasks")
    return TestClient(app)


def test_trigger_official_source_sync_route_exists():
    client = _build_client()
    
    from admin.api.routes import tasks as tasks_route
    tasks_route._running_task = None

    captured = {}
    tasks_route._run_official_source_sync = lambda countries, priority, triggered_by: captured.update(
        {"countries": countries, "priority": priority, "triggered_by": triggered_by}
    )
    response = client.post("/api/tasks/trigger/official-source-sync", json={"countries": None, "priority": "P1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"] == "official_source_sync"
    assert captured["priority"] == "P1"


def test_trigger_read_model_refresh_route_exists():
    client = _build_client()

    from admin.api.routes import tasks as tasks_route
    tasks_route._running_task = None

    captured = {}
    tasks_route._run_simple_task = lambda task_type, runner, triggered_by: captured.update(
        {"task_type": task_type, "triggered_by": triggered_by}
    )

    response = client.post("/api/tasks/trigger/read-model-refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"] == "read_model_refresh"
    assert captured["task_type"] == "read_model_refresh"


def test_trigger_weekly_compliance_update_route_exists():
    client = _build_client()

    from admin.api.routes import tasks as tasks_route
    tasks_route._running_task = None

    captured = {}
    tasks_route._run_simple_task = lambda task_type, runner, triggered_by: captured.update(
        {"task_type": task_type, "triggered_by": triggered_by}
    )

    response = client.post("/api/tasks/trigger/weekly-compliance-update")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"] == "weekly_compliance_update"
    assert captured["task_type"] == "weekly_compliance_update"


def test_trigger_source_registry_refresh_route_exists():
    client = _build_client()

    from admin.api.routes import tasks as tasks_route
    tasks_route._running_task = None

    captured = {}
    tasks_route._run_simple_task = lambda task_type, runner, triggered_by: captured.update(
        {"task_type": task_type, "triggered_by": triggered_by}
    )

    response = client.post("/api/tasks/trigger/source-registry-refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"] == "source_registry_refresh"
    assert captured["task_type"] == "source_registry_refresh"
