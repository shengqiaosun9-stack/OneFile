import copy
from typing import Any, Dict, Optional

import streamlit as st

from ai_service import build_update_input, structure_project
from project_model import (
    apply_rule_overrides,
    apply_schema_to_project,
    compare_field_value,
    get_export_payload,
    get_now_str,
    hard_scrub_project_for_state,
    migrate_project_for_hygiene,
    normalize_project,
    parse_update_signals,
    sanitize_schema,
    validate_title_candidate,
)
from storage import load_projects, save_projects
from text_cleaning import has_markup_contamination, is_timeline_leak_text, sanitize_text_strict


def _contains_legacy_markup_payload(project: Dict[str, Any]) -> bool:
    candidates = []
    for key in ["version_footprint", "summary", "timeline"]:
        candidates.append(project.get(key, ""))
    versions = project.get("versions", [])
    if isinstance(versions, list):
        for item in versions:
            if not isinstance(item, dict):
                continue
            candidates.append(item.get("event", ""))
            candidates.append(item.get("update_text", ""))
            candidates.append(item.get("version_text", ""))
    joined = " ".join([str(x or "") for x in candidates])
    if "<" in joined or ">" in joined:
        return True
    return has_markup_contamination(joined) or is_timeline_leak_text(joined)


def init_state() -> None:
    if "projects" not in st.session_state:
        loaded_projects = load_projects()
        sanitized_projects = []
        for project in loaded_projects:
            if _contains_legacy_markup_payload(project):
                continue
            sanitized_projects.append(hard_scrub_project_for_state(migrate_project_for_hygiene(project)))
        st.session_state.projects = sanitized_projects
        if st.session_state.projects:
            persist_projects()
        elif loaded_projects:
            save_projects([])
    elif st.session_state.projects:
        sanitized_projects = []
        for project in st.session_state.projects:
            if _contains_legacy_markup_payload(project):
                continue
            sanitized_projects.append(hard_scrub_project_for_state(migrate_project_for_hygiene(project)))
        st.session_state.projects = sanitized_projects

    if "last_generated_id" not in st.session_state:
        st.session_state.last_generated_id = None
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "项目库"
    if "show_creator" not in st.session_state:
        st.session_state.show_creator = False
    if "selected_project_id" not in st.session_state:
        st.session_state.selected_project_id = st.session_state.projects[0]["id"] if st.session_state.projects else None
    if "update_target_id" not in st.session_state:
        st.session_state.update_target_id = None
    if "update_preview" not in st.session_state:
        st.session_state.update_preview = None
    if "undo_snapshots" not in st.session_state:
        st.session_state.undo_snapshots = {}
    if "flash_message" not in st.session_state:
        st.session_state.flash_message = None
    if "delete_confirm_id" not in st.session_state:
        st.session_state.delete_confirm_id = None
    if "used_local_structuring" not in st.session_state:
        st.session_state.used_local_structuring = False
    if "last_api_error" not in st.session_state:
        st.session_state.last_api_error = None
    if "data_hygiene_v3_done" not in st.session_state:
        st.session_state.data_hygiene_v3_done = False

    if st.session_state.projects:
        st.session_state.projects = [hard_scrub_project_for_state(project) for project in st.session_state.projects]
        if not st.session_state.data_hygiene_v3_done:
            persist_projects()
            st.session_state.data_hygiene_v3_done = True
    ensure_selected_project()


def ensure_selected_project() -> None:
    if not st.session_state.projects:
        st.session_state.selected_project_id = None
        return
    valid_ids = {project.get("id") for project in st.session_state.projects}
    if st.session_state.selected_project_id not in valid_ids:
        st.session_state.selected_project_id = st.session_state.projects[0]["id"]


def get_project_by_id(project_id: str) -> Optional[Dict[str, Any]]:
    return next((project for project in st.session_state.projects if project.get("id") == project_id), None)


def replace_project_by_id(project_id: str, project: Dict[str, Any]) -> bool:
    for i, existing in enumerate(st.session_state.projects):
        if existing.get("id") == project_id:
            st.session_state.projects[i] = project
            persist_projects()
            return True
    return False


def insert_project_top(project: Dict[str, Any]) -> None:
    st.session_state.projects.insert(0, project)
    persist_projects()


def persist_projects() -> None:
    save_projects(st.session_state.projects)


def _latest_version_text(project: Dict[str, Any]) -> str:
    latest_update = sanitize_text_strict(project.get("latest_update", ""), allow_empty=True, max_len=120)
    if latest_update:
        return latest_update
    versions = project.get("versions", [])
    if isinstance(versions, list) and versions and isinstance(versions[0], dict):
        text = sanitize_text_strict(versions[0].get("event", ""), allow_empty=True, max_len=120)
        if text:
            return text
    return sanitize_text_strict(project.get("version_footprint", ""), allow_empty=True, max_len=120)


def generate_update_preview(project_id: str, update_text: str) -> Dict[str, Any]:
    project = get_project_by_id(project_id)
    if not project:
        raise ValueError("未找到目标项目。")
    cleaned_update = sanitize_text_strict(update_text, allow_empty=False, max_len=280)
    if not cleaned_update:
        raise ValueError("请输入有效进展内容。")

    signals = parse_update_signals(cleaned_update, project)
    rule_first_project = apply_rule_overrides(project, signals)
    try:
        schema = structure_project(build_update_input(rule_first_project, cleaned_update))
    except Exception:
        schema = sanitize_schema(
            {
                **get_export_payload(rule_first_project),
                "version_footprint": cleaned_update,
                "summary": rule_first_project.get("summary", ""),
            }
        )

    timestamp = get_now_str()
    preview_project = apply_schema_to_project(rule_first_project, schema, cleaned_update, timestamp, signals=None)
    preview_fields = []
    field_specs = [
        ("team_text", "团队规模"),
        ("stage_metric", "当前进展"),
        ("stage", "当前阶段"),
        ("status_tag", "状态标签"),
        ("latest_update", "最新进展"),
    ]
    for field, label in field_specs:
        before = compare_field_value(project.get(field))
        after = compare_field_value(preview_project.get(field))
        preview_fields.append({"label": label, "before": before, "after": after, "changed": before != after})

    before_version = _latest_version_text(project) or "—"
    after_version = _latest_version_text(preview_project) or "—"
    preview_fields.append(
        {
            "label": "最新版本记录",
            "before": before_version,
            "after": after_version,
            "changed": before_version != after_version,
        }
    )

    changed_fields = [item for item in preview_fields if item.get("changed")]

    return {
        "project_id": project_id,
        "timestamp": timestamp,
        "update_text": cleaned_update,
        "schema": schema,
        "signals": signals,
        "preview_project": preview_project,
        "preview_fields": preview_fields,
        "changed_fields": changed_fields,
    }


def commit_update_preview(project_id: str) -> None:
    preview = st.session_state.get("update_preview") or {}
    if preview.get("project_id") != project_id:
        raise ValueError("未找到可确认的更新预览，请重新生成。")

    current = get_project_by_id(project_id)
    if not current:
        raise ValueError("目标项目不存在。")

    st.session_state.undo_snapshots[project_id] = copy.deepcopy(current)
    committed = normalize_project(preview.get("preview_project", {}))
    committed["id"] = project_id

    if not replace_project_by_id(project_id, committed):
        raise ValueError("目标项目不存在。")

    st.session_state.selected_project_id = project_id
    st.session_state.last_generated_id = project_id
    st.session_state.update_target_id = None
    st.session_state.update_preview = None
    st.session_state.flash_message = "项目更新已写入档案，并同步到项目库、完整档案与分享页。"


def undo_last_update(project_id: str) -> None:
    snapshot = st.session_state.undo_snapshots.get(project_id)
    if not snapshot:
        raise ValueError("没有可撤销的最近更新。")

    restored = normalize_project(snapshot)
    if not replace_project_by_id(project_id, restored):
        raise ValueError("目标项目不存在。")

    st.session_state.undo_snapshots.pop(project_id, None)
    st.session_state.selected_project_id = project_id
    st.session_state.last_generated_id = project_id
    st.session_state.update_preview = None
    st.session_state.update_target_id = project_id
    st.session_state.flash_message = "已撤销最近一次更新，项目已恢复到上一个版本。"


def delete_project_by_id(project_id: str) -> None:
    current = get_project_by_id(project_id)
    if not current:
        raise ValueError("目标项目不存在。")

    st.session_state.projects = [
        project for project in st.session_state.projects if project.get("id") != project_id
    ]
    persist_projects()

    st.session_state.undo_snapshots.pop(project_id, None)
    st.session_state.delete_confirm_id = None

    preview = st.session_state.get("update_preview")
    if isinstance(preview, dict) and preview.get("project_id") == project_id:
        st.session_state.update_preview = None
    if st.session_state.update_target_id == project_id:
        st.session_state.update_target_id = None
    if st.session_state.last_generated_id == project_id:
        st.session_state.last_generated_id = None

    ensure_selected_project()
    st.session_state.flash_message = "项目档案已删除。"


def rename_project_title(project_id: str, new_title: str) -> None:
    project = get_project_by_id(project_id)
    if not project:
        raise ValueError("目标项目不存在。")

    resolved = sanitize_text_strict(new_title, allow_empty=True, max_len=42)
    if not resolved or not validate_title_candidate(resolved):
        raise ValueError("请输入有效项目名称。")

    updated = normalize_project({**project, "title": resolved})
    if not replace_project_by_id(project_id, updated):
        raise ValueError("目标项目不存在。")

    st.session_state.selected_project_id = project_id
    st.session_state.last_generated_id = project_id
    st.session_state.flash_message = "项目名称已更新。"
