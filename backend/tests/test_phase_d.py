from typing import Dict

import pytest
from fastapi.testclient import TestClient

import backend.service as service
import storage
from project_model import sanitize_schema


def _login(client: TestClient, email: str) -> None:
    start = client.post("/v1/auth/login/start", json={"email": email})
    assert start.status_code == 200
    start_body = start.json()
    verify = client.post(
        "/v1/auth/login/verify",
        json={
            "email": email,
            "challenge_id": start_body.get("challenge_id", ""),
            "code": start_body.get("debug_code", ""),
        },
    )
    assert verify.status_code == 200


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    project_file = data_dir / "projects.json"

    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "PROJECTS_FILE", project_file)

    from backend.main import app

    api_client = TestClient(app)
    _login(api_client, "owner@example.com")
    return api_client


def _fake_schema(title: str) -> Dict[str, str]:
    return sanitize_schema(
        {
            "title": title,
            "desc": "desc",
            "tech_stack": ["AI"],
            "users": "中小企业",
            "use_cases": "典型使用场景",
            "problem_statement": "问题",
            "solution_approach": "方案",
            "model": "B2B 订阅",
            "model_desc": "B2B 订阅",
            "model_type": "B2B_SUBSCRIPTION",
            "pricing_strategy": "FREE_TRIAL",
            "form_type": "SAAS",
            "stage": "MVP",
            "version_footprint": "v1.0",
            "latest_update": "v1.0",
            "summary": "一句话亮点",
            "team_text": "核心团队：2人",
            "stage_metric": "当前阶段：完成首轮验证",
        }
    )


def test_portfolio_endpoint_returns_summary_and_stage_distribution(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    create1 = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "PortfolioA", "input_text": "initial A"},
    )
    assert create1.status_code == 200
    create2 = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "PortfolioB", "input_text": "initial B"},
    )
    assert create2.status_code == 200

    share_resp = client.patch(
        f"/v1/projects/{create1.json()['project']['id']}/share",
        json={"email": "owner@example.com", "is_public": True},
    )
    assert share_resp.status_code == 200

    portfolio_resp = client.get("/v1/portfolio", params={"email": "owner@example.com"})
    assert portfolio_resp.status_code == 200
    body = portfolio_resp.json()
    assert body["summary"]["total_projects"] >= 2
    assert body["summary"]["public_projects"] >= 1
    assert sum(body["stage_distribution"].values()) >= 2
    assert len(body["projects"]) >= 2


def test_weekly_report_endpoint_generates_markdown_and_logs_event(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})
    monkeypatch.setattr(service, "_now_ts", lambda: "2026-03-25 10:00:00")

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "WeeklyProj", "input_text": "initial"},
    )
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]

    updated = client.post(
        f"/v1/projects/{project_id}/update",
        json={"email": "owner@example.com", "update_text": "新增3个客户，完成首轮验证"},
    )
    assert updated.status_code == 200

    report_resp = client.post("/v1/reports/weekly", json={"email": "owner@example.com", "week_start": "2026-03-23"})
    assert report_resp.status_code == 200
    body = report_resp.json()
    assert body["window"]["start"] == "2026-03-23"
    assert body["summary"]["projects_covered"] >= 1
    assert body["summary"]["updates_count"] >= 1
    assert "Weekly Report" in body["report_markdown"]

    store = storage.load_store()
    assert any(item.get("event_type") == "weekly_report_generated" for item in store.get("events", []))


def test_weekly_report_invalid_week_start_returns_400(client: TestClient):
    invalid_resp = client.post("/v1/reports/weekly", json={"email": "owner@example.com", "week_start": "2026/03/23"})
    assert invalid_resp.status_code == 400
    assert invalid_resp.json()["error"] == "invalid_week_start"


def test_weekly_report_default_week_start_uses_monday(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "_now_ts", lambda: "2026-03-26 09:30:00")
    report_resp = client.post("/v1/reports/weekly", json={"email": "owner@example.com"})
    assert report_resp.status_code == 200
    assert report_resp.json()["window"]["start"] == "2026-03-23"


def test_intervention_learning_endpoint_returns_effectiveness_and_recommendation(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "InterventionLearn", "input_text": "initial"},
    )
    assert created.status_code == 200
    project_id = created.json()["project"]["id"]

    store = storage.load_store()
    store["events"].append(
        {
            "id": "itv1",
            "ts": "2026-03-26 10:00:00",
            "user_id": "",
            "project_id": project_id,
            "event_type": "intervention_triggered",
            "source": "overlay_update",
            "payload": {"type": "stuck_replan", "message": "replan"},
        }
    )
    store["events"].append(
        {
            "id": "itv2",
            "ts": "2026-03-26 18:00:00",
            "user_id": "",
            "project_id": project_id,
            "event_type": "intervention_resolved",
            "source": "overlay_update",
            "payload": {"type": "stuck_replan", "effectiveness": "improved"},
        }
    )
    storage.save_store(store)

    learning_resp = client.get("/v1/interventions/learning", params={"email": "owner@example.com", "days": 30})
    assert learning_resp.status_code == 200
    body = learning_resp.json()
    assert body["window_days"] == 30
    assert body["totals"]["triggered"] >= 1
    assert body["totals"]["resolved"] >= 1
    assert body["strategy"]["best_type"] in {"stuck_replan", "quality_raise", "none"}
    assert isinstance(body["strategy"]["recommendation"], str)
    assert len(body["strategy"]["recommendation"]) >= 4


def test_intervention_learning_without_samples_returns_none_strategy(client: TestClient):
    learning_resp = client.get("/v1/interventions/learning", params={"email": "owner@example.com", "days": 30})
    assert learning_resp.status_code == 200
    body = learning_resp.json()
    assert body["totals"]["triggered"] == 0
    assert body["strategy"]["best_type"] == "none"


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/v1/portfolio"),
        ("get", "/v1/interventions/learning"),
    ],
)
def test_phase_d_endpoints_require_session(method: str, path: str):
    from backend.main import app

    anon = TestClient(app)
    response = getattr(anon, method)(path)
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
