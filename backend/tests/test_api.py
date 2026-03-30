from typing import Dict

import pytest
from fastapi.testclient import TestClient

from backend.config import reset_settings_cache
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


def _fake_generate_object(name: str) -> Dict[str, str]:
    return {
        "name": name,
        "one_liner": "AI 自动生成项目档案",
        "core_problem": "表达门槛高",
        "solution": "自动结构化输入",
        "target_user": "独立开发者",
        "use_case": "快速成型项目档案",
        "monetization": "B2B 订阅",
        "current_stage": "building",
        "progress_note": "已完成首版生成链路",
        "key_metric": "首轮生成成功率 92%",
    }


def test_login_user_id_stable(client: TestClient):
    payload = {"email": "founder@example.com"}
    first = client.post("/v1/auth/login", json=payload)
    second = client.post("/v1/auth/login", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["user"]["id"] == second.json()["user"]["id"]


def test_login_start_rate_limit(client: TestClient, monkeypatch):
    monkeypatch.setenv("ONEFILE_AUTH_START_MAX_PER_HOUR", "2")
    reset_settings_cache()
    try:
        payload = {"email": "ratelimit@example.com"}
        first = client.post("/v1/auth/login/start", json=payload)
        second = client.post("/v1/auth/login/start", json=payload)
        blocked = client.post("/v1/auth/login/start", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert blocked.status_code == 429
        body = blocked.json()
        assert body["error"] == "too_many_requests"
    finally:
        reset_settings_cache()


def test_login_start_rate_limit_by_ip(client: TestClient, monkeypatch):
    monkeypatch.setenv("ONEFILE_AUTH_START_MAX_PER_IP_HOUR", "4")
    reset_settings_cache()
    try:
        payload = {"email": "ip-limit@example.com"}
        for _ in range(4):
            attempt = client.post("/v1/auth/login/start", json=payload, headers={"x-forwarded-for": "1.2.3.4"})
            assert attempt.status_code == 200
        blocked = client.post("/v1/auth/login/start", json=payload, headers={"x-forwarded-for": "1.2.3.4"})

        assert blocked.status_code == 429
        assert blocked.json()["error"] == "too_many_requests"
    finally:
        reset_settings_cache()


def test_create_success_and_fallback_meta(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    response = client.post(
        "/v1/projects",
        json={
            "email": "owner@example.com",
            "title": "Alpha",
            "input_text": "做一个 AI 产品",
            "stage": "MVP",
        },
    )
    assert response.status_code == 200
    assert response.json()["used_fallback"] is False

    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": True, "last_api_error": "api timeout"})
    response2 = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "Beta", "input_text": "另一个产品"},
    )
    assert response2.status_code == 200
    assert response2.json()["used_fallback"] is True
    assert response2.json()["warning"] == "AI 服务暂不可用，已自动使用本地规则完成结构化。"


def test_create_merges_supplemental_text_into_structuring_input(client: TestClient, monkeypatch):
    captured: Dict[str, str] = {}

    def fake_structure(raw_input: str, user_title: str = "") -> Dict[str, str]:
        captured["raw_input"] = raw_input
        return _fake_schema(user_title or "项目")

    monkeypatch.setattr(service, "structure_project", fake_structure)
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    response = client.post(
        "/v1/projects",
        json={
            "email": "owner@example.com",
            "title": "MergedInput",
            "input_text": "这是正文输入",
            "supplemental_text": "这是 BP 解析文本",
        },
    )
    assert response.status_code == 200
    assert "这是正文输入" in captured.get("raw_input", "")
    assert "这是 BP 解析文本" in captured.get("raw_input", "")
    assert "\n\n" in captured.get("raw_input", "")
    assert response.json()["project"]["updates"][0]["input_meta"]["has_file"] is True


def test_generate_project_supports_raw_file_and_optional_title(client: TestClient, monkeypatch):
    captured: Dict[str, str] = {}

    def fake_generate(raw_input: str, optional_title: str = "") -> Dict[str, str]:
        captured["raw_input"] = raw_input
        captured["optional_title"] = optional_title
        return _fake_generate_object(optional_title or "自动标题")

    monkeypatch.setattr(service, "structure_project_object", fake_generate)
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    response = client.post(
        "/v1/project/generate",
        json={
            "raw_input": "一句话输入",
            "file_text": "BP 提取文本",
            "optional_title": "指定标题",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["project"]["title"] == "指定标题"
    assert body["project"]["summary"] == "AI 自动生成项目档案"
    assert body["project"]["model_desc"] == "B2B 订阅"
    assert body["project"]["latest_update"] == "已完成首版生成链路"
    assert body["project"]["stage_metric"] == "当前阶段：首轮生成成功率 92%"
    assert "BP 提取文本" in captured.get("raw_input", "")
    assert "一句话输入" in captured.get("raw_input", "")
    assert captured.get("optional_title", "") == "指定标题"


def test_generate_project_supports_file_only_and_invalid_input(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project_object", lambda raw_input, optional_title="": _fake_generate_object("文件生成标题"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": True, "last_api_error": "timeout"})

    file_only = client.post("/v1/project/generate", json={"file_text": "仅文件内容"})
    assert file_only.status_code == 200
    file_only_body = file_only.json()
    assert file_only_body["project"]["title"] == "文件生成标题"
    assert file_only_body["used_fallback"] is True
    assert file_only_body["warning"] == "AI 服务暂不可用，已自动使用本地规则完成结构化。"

    invalid = client.post("/v1/project/generate", json={"raw_input": "", "file_text": ""})
    assert invalid.status_code == 400
    assert invalid.json()["error"] == "invalid_input"


def test_visibility_rules_owner_public(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    create_resp = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "PrivateOne", "input_text": "private content"},
    )
    project_id = create_resp.json()["project"]["id"]

    list_owner = client.get("/v1/projects", params={"email": "owner@example.com"})
    assert list_owner.status_code == 200
    assert any(item["id"] == project_id for item in list_owner.json()["projects"])

    other_client = TestClient(client.app)
    list_other = other_client.get("/v1/projects", params={"email": "other@example.com"})
    assert list_other.status_code == 200
    assert any(item["id"] == project_id for item in list_other.json()["projects"])

    share_resp = client.patch(
        f"/v1/projects/{project_id}/share",
        json={"email": "owner@example.com", "is_public": False},
    )
    assert share_resp.status_code == 200

    list_other_after_private = other_client.get("/v1/projects", params={"email": "other@example.com"})
    assert not any(item["id"] == project_id for item in list_other_after_private.json()["projects"])


def test_update_owner_only_and_latest_update_changes(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "Gamma", "input_text": "initial"},
    )
    project_id = created.json()["project"]["id"]

    other_client = TestClient(client.app)
    _login(other_client, "other@example.com")
    forbidden = other_client.post(
        f"/v1/projects/{project_id}/update",
        json={"email": "other@example.com", "update_text": "推进了"},
    )
    assert forbidden.status_code == 403

    updated = client.post(
        f"/v1/projects/{project_id}/update",
        json={"email": "owner@example.com", "update_text": "新增3个客户"},
    )
    assert updated.status_code == 200
    assert updated.json()["project"]["latest_update"] == "新增3个客户"


def test_share_access_public_private_owner_preview(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "Delta", "input_text": "initial"},
    )
    project_id = created.json()["project"]["id"]

    anon_client = TestClient(client.app)
    make_private = client.patch(
        f"/v1/projects/{project_id}/share",
        json={"email": "owner@example.com", "is_public": False},
    )
    assert make_private.status_code == 200

    private_view = anon_client.get(f"/v1/share/{project_id}")
    assert private_view.status_code == 200
    assert private_view.json()["access_granted"] is False

    owner_preview = client.get(f"/v1/share/{project_id}", params={"email": "owner@example.com"})
    assert owner_preview.status_code == 200
    assert owner_preview.json()["access_granted"] is True
    assert owner_preview.json()["owner_preview"] is True

    make_public = client.patch(
        f"/v1/projects/{project_id}/share",
        json={"email": "owner@example.com", "is_public": True},
    )
    assert make_public.status_code == 200

    public_view = client.get(f"/v1/share/{project_id}")
    assert public_view.status_code == 200
    assert public_view.json()["access_granted"] is True


def test_share_cta_click_event_and_ops_signal(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "Epsilon", "input_text": "initial"},
    )
    project_id = created.json()["project"]["id"]

    make_public = client.patch(
        f"/v1/projects/{project_id}/share",
        json={"email": "owner@example.com", "is_public": True},
    )
    assert make_public.status_code == 200

    cta_resp = client.post(
        f"/v1/share/{project_id}/cta",
        json={"cta": "start_project", "source": "share_page_cta"},
    )
    assert cta_resp.status_code == 200
    assert cta_resp.json()["ok"] is True
    assert cta_resp.json()["access_granted"] is True
    assert cta_resp.json()["expires_in_days"] == 7
    assert isinstance(cta_resp.json()["expires_at"], str)
    assert len(cta_resp.json()["expires_at"]) >= 10

    store = storage.load_store()
    assert any(
        item.get("project_id") == project_id and item.get("event_type") == "share_cta_clicked"
        for item in store.get("events", [])
    )

    detail_resp = client.get(f"/v1/projects/{project_id}", params={"email": "owner@example.com"})
    assert detail_resp.status_code == 200
    assert detail_resp.json()["project"]["ops_signals"]["share_cta_clicks_14d"] >= 1


def test_share_cta_token_can_attribute_create_and_update_conversion(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "Origin", "input_text": "origin"},
    )
    source_project_id = created.json()["project"]["id"]
    make_public = client.patch(
        f"/v1/projects/{source_project_id}/share",
        json={"email": "owner@example.com", "is_public": True},
    )
    assert make_public.status_code == 200

    cta_resp = client.post(
        f"/v1/share/{source_project_id}/cta",
        json={"cta": "start_project", "source": "share_page_cta"},
    )
    assert cta_resp.status_code == 200
    cta_token = cta_resp.json().get("cta_token", "")
    assert isinstance(cta_token, str)
    assert len(cta_token) >= 8

    create_resp = client.post(
        "/v1/projects",
        json={
            "email": "visitor@example.com",
            "title": "Visitor Created",
            "input_text": "from share cta",
            "cta_token": cta_token,
        },
    )
    assert create_resp.status_code == 200
    visitor_project_id = create_resp.json()["project"]["id"]

    update_resp = client.post(
        f"/v1/projects/{visitor_project_id}/update",
        json={
            "email": "visitor@example.com",
            "update_text": "完成首批验证",
            "cta_token": cta_token,
        },
    )
    assert update_resp.status_code == 200

    store = storage.load_store()
    conversion_events = [
        item
        for item in store.get("events", [])
        if item.get("event_type") == "share_conversion_attributed"
    ]
    assert any(
        item.get("payload", {}).get("conversion_kind") == "create" and item.get("project_id") == source_project_id
        for item in conversion_events
    )
    assert any(
        item.get("payload", {}).get("conversion_kind") == "update" and item.get("project_id") == source_project_id
        for item in conversion_events
    )


def test_update_returns_quality_feedback(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "Quality", "input_text": "initial"},
    )
    project_id = created.json()["project"]["id"]

    updated = client.post(
        f"/v1/projects/{project_id}/update",
        json={"email": "owner@example.com", "update_text": "先这样，后面再说"},
    )
    assert updated.status_code == 200
    feedback = updated.json()["quality_feedback"]
    assert feedback["level"] in {"low", "medium", "high"}
    assert isinstance(feedback["reasons"], list)
    assert len(feedback["reasons"]) >= 1
    assert isinstance(feedback["suggested_next_input"], str)
    assert len(feedback["suggested_next_input"]) >= 4


def test_growth_metrics_api_reports_share_funnel(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "GrowthSource", "input_text": "initial"},
    )
    source_project_id = created.json()["project"]["id"]
    make_public = client.patch(
        f"/v1/projects/{source_project_id}/share",
        json={"email": "owner@example.com", "is_public": True},
    )
    assert make_public.status_code == 200

    shared_view = client.get(f"/v1/share/{source_project_id}")
    assert shared_view.status_code == 200
    cta_resp = client.post(
        f"/v1/share/{source_project_id}/cta",
        json={"cta": "start_project", "source": "share_page_cta"},
    )
    cta_token = cta_resp.json()["cta_token"]

    create_resp = client.post(
        "/v1/projects",
        json={
            "email": "visitor@example.com",
            "title": "GrowthTarget",
            "input_text": "from cta",
            "cta_token": cta_token,
        },
    )
    target_project_id = create_resp.json()["project"]["id"]
    update_resp = client.post(
        f"/v1/projects/{target_project_id}/update",
        json={
            "email": "visitor@example.com",
            "update_text": "上线并完成首批验证",
            "cta_token": cta_token,
        },
    )
    assert update_resp.status_code == 200

    metrics_resp = client.get("/v1/metrics/growth", params={"email": "owner@example.com", "days": 14})
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    assert body["window_days"] == 14
    assert body["totals"]["share_views"] >= 1
    assert body["totals"]["share_cta_clicks"] >= 1
    assert body["totals"]["share_create_conversions"] >= 1
    assert body["totals"]["share_update_conversions"] >= 1
    assert body["rates"]["view_to_cta"] > 0
    assert body["rates"]["cta_to_create"] > 0


def test_update_returns_evolution_explanation(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "Explain", "input_text": "initial"},
    )
    project_id = created.json()["project"]["id"]

    updated = client.post(
        f"/v1/projects/{project_id}/update",
        json={"email": "owner@example.com", "update_text": "产品已上线，新增3个客户并完成首轮验证"},
    )
    assert updated.status_code == 200
    explanation = updated.json()["evolution_explanation"]
    assert explanation["stage_before"] in {"IDEA", "BUILDING", "MVP", "VALIDATION", "EARLY_REVENUE", "SCALING", "MATURE"}
    assert explanation["stage_after"] in {"IDEA", "BUILDING", "MVP", "VALIDATION", "EARLY_REVENUE", "SCALING", "MATURE"}
    assert isinstance(explanation["stage_changed"], bool)
    assert isinstance(explanation["progress_delta"], int)
    assert isinstance(explanation["reason_codes"], list)
    assert len(explanation["reason_codes"]) >= 1


def test_growth_metrics_include_source_ref_breakdowns(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "BreakdownSource", "input_text": "initial"},
    )
    source_project_id = created.json()["project"]["id"]
    make_public = client.patch(
        f"/v1/projects/{source_project_id}/share",
        json={"email": "owner@example.com", "is_public": True},
    )
    assert make_public.status_code == 200

    cta_resp = client.post(
        f"/v1/share/{source_project_id}/cta",
        json={"cta": "start_project", "source": "wechat_share", "ref": "moments"},
    )
    assert cta_resp.status_code == 200
    cta_token = cta_resp.json()["cta_token"]

    create_resp = client.post(
        "/v1/projects",
        json={
            "email": "visitor@example.com",
            "title": "BreakdownTarget",
            "input_text": "from share",
            "cta_token": cta_token,
        },
    )
    assert create_resp.status_code == 200

    metrics_resp = client.get("/v1/metrics/growth", params={"email": "owner@example.com", "days": 14})
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    assert body["breakdowns"]["cta_by_source"]["wechat_share"] >= 1
    assert body["breakdowns"]["cta_by_ref"]["moments"] >= 1
    assert body["breakdowns"]["create_conversion_by_source"]["wechat_share"] >= 1
    assert body["breakdowns"]["create_conversion_by_ref"]["moments"] >= 1


def test_cta_token_ttl_and_replay_prevention(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "ReplaySource", "input_text": "initial"},
    )
    source_project_id = created.json()["project"]["id"]
    public_resp = client.patch(
        f"/v1/projects/{source_project_id}/share",
        json={"email": "owner@example.com", "is_public": True},
    )
    assert public_resp.status_code == 200

    monkeypatch.setattr(service, "_now_ts", lambda: "2026-03-01 10:00:00")
    cta_resp = client.post(
        f"/v1/share/{source_project_id}/cta",
        json={"cta": "start_project", "source": "share_page_cta"},
    )
    token_expired = cta_resp.json()["cta_token"]

    monkeypatch.setattr(service, "_now_ts", lambda: "2026-03-20 10:00:00")
    expired_create = client.post(
        "/v1/projects",
        json={
            "email": "visitor@example.com",
            "title": "ExpiredCreate",
            "input_text": "late create",
            "cta_token": token_expired,
        },
    )
    assert expired_create.status_code == 200

    monkeypatch.setattr(service, "_now_ts", lambda: "2026-03-21 10:00:00")
    fresh_cta_resp = client.post(
        f"/v1/share/{source_project_id}/cta",
        json={"cta": "start_project", "source": "share_page_cta"},
    )
    token_fresh = fresh_cta_resp.json()["cta_token"]

    first_create = client.post(
        "/v1/projects",
        json={
            "email": "a@example.com",
            "title": "ReplayCreateA",
            "input_text": "create A",
            "cta_token": token_fresh,
        },
    )
    assert first_create.status_code == 200
    second_create = client.post(
        "/v1/projects",
        json={
            "email": "b@example.com",
            "title": "ReplayCreateB",
            "input_text": "create B",
            "cta_token": token_fresh,
        },
    )
    assert second_create.status_code == 200

    created_project_id = first_create.json()["project"]["id"]
    first_update = client.post(
        f"/v1/projects/{created_project_id}/update",
        json={"email": "a@example.com", "update_text": "完成试点", "cta_token": token_fresh},
    )
    assert first_update.status_code == 200
    second_update = client.post(
        f"/v1/projects/{created_project_id}/update",
        json={"email": "a@example.com", "update_text": "继续推进", "cta_token": token_fresh},
    )
    assert second_update.status_code == 200

    store = storage.load_store()
    conversion_events = [
        item for item in store.get("events", []) if item.get("event_type") == "share_conversion_attributed"
    ]
    skipped_events = [
        item for item in store.get("events", []) if item.get("event_type") == "share_conversion_skipped"
    ]
    assert sum(1 for item in conversion_events if item.get("payload", {}).get("cta_token") == token_expired) == 0
    assert sum(
        1
        for item in conversion_events
        if item.get("payload", {}).get("cta_token") == token_fresh
        and item.get("payload", {}).get("conversion_kind") == "create"
    ) == 1
    assert sum(
        1
        for item in conversion_events
        if item.get("payload", {}).get("cta_token") == token_fresh
        and item.get("payload", {}).get("conversion_kind") == "update"
    ) == 1
    assert any(
        item.get("payload", {}).get("cta_token") == token_expired
        and item.get("payload", {}).get("reason") == "token_expired"
        for item in skipped_events
    )
    assert any(
        item.get("payload", {}).get("cta_token") == token_fresh
        and item.get("payload", {}).get("reason") == "replay_blocked"
        for item in skipped_events
    )


def test_project_growth_metrics_endpoint(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "ProjectFunnelSource", "input_text": "initial"},
    )
    source_project_id = created.json()["project"]["id"]
    public_resp = client.patch(
        f"/v1/projects/{source_project_id}/share",
        json={"email": "owner@example.com", "is_public": True},
    )
    assert public_resp.status_code == 200
    share_view = client.get(f"/v1/share/{source_project_id}")
    assert share_view.status_code == 200
    cta_resp = client.post(
        f"/v1/share/{source_project_id}/cta",
        json={"cta": "start_project", "source": "share_page_cta", "ref": "home_banner"},
    )
    token = cta_resp.json()["cta_token"]
    create_resp = client.post(
        "/v1/projects",
        json={"email": "visitor@example.com", "title": "ProjectFunnelTarget", "input_text": "from cta", "cta_token": token},
    )
    target_project_id = create_resp.json()["project"]["id"]
    update_resp = client.post(
        f"/v1/projects/{target_project_id}/update",
        json={"email": "visitor@example.com", "update_text": "完成一次更新", "cta_token": token},
    )
    assert update_resp.status_code == 200

    metrics_resp = client.get(
        f"/v1/metrics/growth/projects/{source_project_id}",
        params={"email": "owner@example.com", "days": 14},
    )
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    assert body["project_id"] == source_project_id
    assert body["totals"]["share_views"] >= 1
    assert body["totals"]["share_cta_clicks"] >= 1
    assert body["totals"]["share_create_conversions"] >= 1
    assert body["totals"]["share_update_conversions"] >= 1


def test_growth_metrics_window_boundary_includes_exact_day_and_excludes_older(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})
    monkeypatch.setattr(service, "_now_ts", lambda: "2026-03-27 12:00:00")

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "BoundarySource", "input_text": "initial"},
    )
    source_project_id = created.json()["project"]["id"]

    store = storage.load_store()
    store_events = store.get("events", [])
    store_events.append(
        {
            "id": "evt_in_14",
            "ts": "2026-03-13 08:00:00",
            "user_id": "",
            "project_id": source_project_id,
            "event_type": "share_viewed",
            "source": "share_api",
            "payload": {},
        }
    )
    store_events.append(
        {
            "id": "evt_out_15",
            "ts": "2026-03-12 08:00:00",
            "user_id": "",
            "project_id": source_project_id,
            "event_type": "share_viewed",
            "source": "share_api",
            "payload": {},
        }
    )
    store["events"] = store_events
    storage.save_store(store)

    metrics_resp = client.get("/v1/metrics/growth", params={"email": "owner@example.com", "days": 14})
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    assert body["totals"]["share_views"] == 1


def test_update_emits_next_action_completed_event(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "ActionComplete", "input_text": "initial"},
    )
    project_id = created.json()["project"]["id"]

    update_resp = client.post(
        f"/v1/projects/{project_id}/update",
        json={"email": "owner@example.com", "update_text": "已完成下一步：完成首批验证"},
    )
    assert update_resp.status_code == 200

    store = storage.load_store()
    assert any(
        item.get("project_id") == project_id and item.get("event_type") == "next_action_completed"
        for item in store.get("events", [])
    )

    detail_resp = client.get(f"/v1/projects/{project_id}", params={"email": "owner@example.com"})
    assert detail_resp.status_code == 200
    assert detail_resp.json()["project"]["ops_signals"]["completed_actions_14d"] >= 1


def test_growth_metrics_include_share_to_7d_update_rate(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "ShareFollowup", "input_text": "initial"},
    )
    project_id = created.json()["project"]["id"]

    share_resp = client.patch(
        f"/v1/projects/{project_id}/share",
        json={"email": "owner@example.com", "is_public": True},
    )
    assert share_resp.status_code == 200

    update_resp = client.post(
        f"/v1/projects/{project_id}/update",
        json={"email": "owner@example.com", "update_text": "完成分享后跟进更新"},
    )
    assert update_resp.status_code == 200

    metrics_resp = client.get("/v1/metrics/growth", params={"email": "owner@example.com", "days": 14})
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    assert body["rates"]["share_to_7d_update"] > 0


def test_project_growth_metrics_forbidden_for_non_owner(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "OwnerOnlyMetrics", "input_text": "initial"},
    )
    project_id = created.json()["project"]["id"]

    other_client = TestClient(client.app)
    _login(other_client, "other@example.com")
    forbidden_resp = other_client.get(
        f"/v1/metrics/growth/projects/{project_id}",
        params={"days": 14},
    )
    assert forbidden_resp.status_code == 403


def test_growth_projects_dashboard_endpoint_returns_sorted_projects(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    p1 = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "DashboardP1", "input_text": "initial"},
    ).json()["project"]["id"]
    p2 = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "DashboardP2", "input_text": "initial"},
    ).json()["project"]["id"]

    client.patch(f"/v1/projects/{p1}/share", json={"email": "owner@example.com", "is_public": True})
    client.patch(f"/v1/projects/{p2}/share", json={"email": "owner@example.com", "is_public": True})
    client.get(f"/v1/share/{p1}")
    client.get(f"/v1/share/{p2}")

    client.post(f"/v1/share/{p1}/cta", json={"cta": "start_project", "source": "share_page_cta"})
    client.post(f"/v1/share/{p1}/cta", json={"cta": "start_project", "source": "share_page_cta"})
    client.post(f"/v1/share/{p2}/cta", json={"cta": "start_project", "source": "share_page_cta"})

    dashboard_resp = client.get(
        "/v1/metrics/growth/projects",
        params={"email": "owner@example.com", "days": 14, "limit": 10},
    )
    assert dashboard_resp.status_code == 200
    body = dashboard_resp.json()
    assert body["window_days"] == 14
    assert isinstance(body["projects"], list)
    assert len(body["projects"]) >= 2
    assert body["projects"][0]["totals"]["share_cta_clicks"] >= body["projects"][1]["totals"]["share_cta_clicks"]


def test_growth_metrics_include_update_quality_summary(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "QualityMetrics", "input_text": "initial"},
    )
    project_id = created.json()["project"]["id"]

    low_update = client.post(
        f"/v1/projects/{project_id}/update",
        json={"email": "owner@example.com", "update_text": "先这样，后面再说"},
    )
    assert low_update.status_code == 200
    high_update = client.post(
        f"/v1/projects/{project_id}/update",
        json={"email": "owner@example.com", "update_text": "新增3个客户，收入提升20%，已完成下一步"},
    )
    assert high_update.status_code == 200

    metrics_resp = client.get("/v1/metrics/growth", params={"email": "owner@example.com", "days": 14})
    assert metrics_resp.status_code == 200
    body = metrics_resp.json()
    assert body["quality"]["project_updates"] >= 2
    assert body["quality"]["avg_update_quality_score"] > 0
    assert body["quality"]["high_quality_update_rate"] >= 0


def test_backup_export_requires_auth_and_scopes_owner_data(client: TestClient, monkeypatch):
    monkeypatch.setattr(service, "structure_project", lambda raw_input, user_title="": _fake_schema(user_title or "项目"))
    monkeypatch.setattr(service, "get_last_structuring_meta", lambda: {"used_local_structuring": False, "last_api_error": ""})

    owner_created = client.post(
        "/v1/projects",
        json={"email": "owner@example.com", "title": "OwnerBackupProject", "input_text": "owner content"},
    )
    assert owner_created.status_code == 200
    owner_project_id = owner_created.json()["project"]["id"]

    other_client = TestClient(client.app)
    _login(other_client, "other@example.com")
    other_created = other_client.post(
        "/v1/projects",
        json={"email": "other@example.com", "title": "OtherBackupProject", "input_text": "other content"},
    )
    assert other_created.status_code == 200
    other_project_id = other_created.json()["project"]["id"]

    export_resp = client.get("/v1/backup/export")
    assert export_resp.status_code == 200
    export_body = export_resp.json()
    exported_ids = {item.get("id") for item in export_body.get("projects", [])}
    assert owner_project_id in exported_ids
    assert other_project_id not in exported_ids
    assert export_body["user"]["email"] == "owner@example.com"

    anon_client = TestClient(client.app)
    anon_resp = anon_client.get("/v1/backup/export")
    assert anon_resp.status_code == 401
    assert anon_resp.json()["error"] == "unauthorized"


def test_bp_extract_endpoint_requires_auth_and_supports_pdf(client: TestClient, monkeypatch):
    import backend.main as main_module

    anon_client = TestClient(client.app)
    anon_resp = anon_client.post(
        "/v1/uploads/bp-extract",
        files={"file": ("demo.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert anon_resp.status_code == 401

    invalid_type = client.post(
        "/v1/uploads/bp-extract",
        files={"file": ("demo.txt", b"plain text", "text/plain")},
    )
    assert invalid_type.status_code == 400
    assert invalid_type.json()["error"] == "invalid_file_type"

    monkeypatch.setattr(
        main_module,
        "extract_pdf_text",
        lambda payload: {
            "extracted_text": "BP 文本内容",
            "page_count": 3,
            "text_chars": 6,
            "truncated": False,
        },
    )
    valid_resp = client.post(
        "/v1/uploads/bp-extract",
        files={"file": ("demo.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert valid_resp.status_code == 200
    body = valid_resp.json()
    assert body["extracted_text"] == "BP 文本内容"
    assert body["page_count"] == 3
    assert body["truncated"] is False
