from fastapi.testclient import TestClient

from backend.config import reset_settings_cache
import storage


def _client(tmp_path, monkeypatch) -> TestClient:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "PROJECTS_FILE", data_dir / "projects.json")
    monkeypatch.setenv("ONEFILE_LOCAL_MODE", "1")
    reset_settings_cache()
    from backend.main import app

    return TestClient(app)


def test_public_diagnosis_creates_bp_project_without_public_project_leak(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    resp = client.post(
        "/v1/bp/diagnoses",
        json={
            "name": "AI 慢病用药助手",
            "founder_name": "药师小顾",
            "tagline": "面向老年慢病患者的合理用药 Web Agent",
            "stage": "prototype",
            "current_resource_need": ["技术团队", "医疗健康场景"],
            "raw_material": "已经开发 Web 应用并申请软著，信息药师背景。现在开发维护吃力，需要团队支持。",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["project"]["name"] == "AI 慢病用药助手"
    assert body["project"]["user_visible_token"]
    assert "internal_notes" not in body["project"]
    assert body["insight"]["problem"]
    assert body["insight"]["resource_readiness"]
    assert body["insight"]["likely_questions"]
    assert body["insight"]["next_actions"]
    assert body["insight"]["bp_structure_preview"]
    share_card = body["insight"]["share_card"]
    assert share_card["core_problem"]
    assert share_card["solution"]
    assert share_card["ai_role"]
    assert share_card["current_needs"]
    assert share_card["can_provide"]
    assert share_card["suitable_for"]
    assert "已有收入" not in share_card["business_model_status"]
    assert share_card["sensitive_info_boundary"].startswith("这张卡不包含完整 BP")
    assert share_card["contact_visibility"] == "hidden"
    assert share_card["contact_method"] == ""
    assert len(body["pages"]) == 14
    assert body["pages"][0]["title"] == "项目封面"
    assert body["pages"][0]["draft_copy"] == ""
    assert body["pages"][0]["is_locked"] is True
    assert body["gap_report"]["items"]

    public_projects = client.get("/v1/projects")
    assert public_projects.status_code == 200
    assert all(item.get("title") != "AI 慢病用药助手" for item in public_projects.json()["projects"])

    stored = storage.load_store()
    assert len(stored["bp_projects"]) == 1
    assert len(stored["projects"]) == 0


def test_bp_diagnosis_marks_ai_generation_success(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    def fake_ai_assets(project, materials, fallback_assets):
        insight = dict(fallback_assets["insight"])
        insight["problem"] = "DeepSeek 判断：项目需要把医疗场景、AI Agent 和团队资源讲清楚。"
        pages = [dict(item) for item in fallback_assets["pages"]]
        pages[0]["draft_copy"] = "DeepSeek 生成的项目封面文案。"
        return {
            "insight": insight,
            "pages": pages,
            "gap_report": fallback_assets["gap_report"],
        }

    from backend import service

    monkeypatch.setattr(service, "generate_bp_assets_with_ai", fake_ai_assets)

    resp = client.post(
        "/v1/bp/diagnoses",
        json={
            "name": "AI 慢病用药助手",
            "tagline": "面向老年慢病患者的合理用药 Web Agent",
            "stage": "prototype",
            "raw_material": "已经开发 Web 应用并申请软著，信息药师背景。现在开发维护吃力，需要团队支持。",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["used_ai"] is True
    assert body["fallback_reason"] == ""
    assert body["insight"]["problem"].startswith("DeepSeek 判断")
    assert body["pages"][0]["draft_copy"] == ""

    project_id = body["project"]["id"]
    ops_detail = client.get(f"/v1/ops/bp/projects/{project_id}")
    assert ops_detail.status_code == 200
    assert ops_detail.json()["pages"][0]["draft_copy"] == "DeepSeek 生成的项目封面文案。"


def test_bp_diagnosis_falls_back_when_ai_generation_fails(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    def broken_ai_assets(project, materials, fallback_assets):
        raise RuntimeError("upstream unavailable")

    from backend import service

    monkeypatch.setattr(service, "generate_bp_assets_with_ai", broken_ai_assets)

    resp = client.post(
        "/v1/bp/diagnoses",
        json={
            "name": "园区 AI 私有化部署项目",
            "tagline": "帮助企业把知识库和 Agent 部署到本地算力环境",
            "stage": "pilot",
            "raw_material": "已有 Demo，想对接园区和企业客户。缺少客户案例和商业模式说明。",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["used_ai"] is False
    assert body["fallback_reason"]
    assert len(body["pages"]) == 14


def test_public_token_view_hides_internal_fields_and_service_request_enters_ops(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/v1/bp/diagnoses",
        json={
            "name": "园区 AI 私有化部署项目",
            "tagline": "帮助企业把知识库和 Agent 部署到本地算力环境",
            "stage": "pilot",
            "raw_material": "已有 Demo，想对接园区和企业客户。缺少客户案例和商业模式说明。",
        },
    ).json()
    token = created["project"]["user_visible_token"]
    project_id = created["project"]["id"]

    service_resp = client.post(
        f"/v1/bp/diagnoses/{token}/service-requests",
        json={
            "service_type": "bp_restructure",
            "contact_name": "张同学",
            "contact_wechat": "wechat-demo",
            "user_message": "想先判断是否适合对接园区。",
        },
    )

    assert service_resp.status_code == 200
    service_body = service_resp.json()
    assert service_body["service_request"]["status"] == "new"
    assert service_body["next_action"]["project_id"] == project_id

    public_detail = client.get(f"/v1/bp/diagnoses/{token}")
    assert public_detail.status_code == 200
    public_body = public_detail.json()
    assert "internal_notes" not in public_body["project"]
    assert "budget_signal" not in public_body["project"]
    assert "service_quote" not in public_body["service_requests"][0]
    assert public_body["pages"][0]["draft_copy"] == ""
    assert public_body["pages"][0]["suggested_content"] == ""
    assert public_body["pages"][0]["existing_materials"] == []
    assert public_body["raw_materials"] == []
    assert public_body["insight"]["share_card"]["contact_visibility"] == "hidden"
    assert public_body["insight"]["share_card"]["contact_method"] == ""
    assert "完整 BP" in public_body["insight"]["share_card"]["sensitive_info_boundary"]

    ops_list = client.get("/v1/ops/bp/projects")
    assert ops_list.status_code == 200
    assert ops_list.json()["projects"][0]["id"] == project_id
    assert ops_list.json()["projects"][0]["internal_status"] == "new_service_request"

    ops_detail = client.get(f"/v1/ops/bp/projects/{project_id}")
    assert ops_detail.status_code == 200
    assert ops_detail.json()["project"]["budget_signal"] == "unknown"
    assert ops_detail.json()["service_requests"][0]["contact_wechat"] == "wechat-demo"


def test_supplement_material_regenerates_public_report(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/v1/bp/diagnoses",
        json={
            "name": "电竞 AI 业务提效项目",
            "tagline": "用 AI 做电竞知识付费和团队业务提效",
            "stage": "idea",
            "raw_material": "有现成电竞业务和变现渠道，正在找 AI 技术合伙人。",
        },
    ).json()
    token = created["project"]["user_visible_token"]

    supplement = client.post(
        f"/v1/bp/diagnoses/{token}/supplements",
        json={
            "title": "补充材料",
            "content": "补充：有稳定业务和变现渠道，需要智能体搭建、内容赋能和系统搭建。",
            "related_page_number": 8,
        },
    )

    assert supplement.status_code == 200
    body = supplement.json()
    assert body["raw_materials"] == []
    assert len(body["pages"]) == 14
    assert body["project"]["updated_at"]
    assert any(item["version_name"] == "补充材料并重新生成" for item in body["versions"])
