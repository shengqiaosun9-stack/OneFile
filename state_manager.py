import copy
import importlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

from ai_service import build_update_input, structure_project
from project_model import (
    apply_rule_overrides,
    get_status_theme,
    get_export_payload,
    get_now_str,
    hard_scrub_project_for_state,
    infer_status_tag,
    migrate_project_for_hygiene,
    normalize_form_type,
    normalize_model_type,
    normalize_project,
    normalize_stage_value,
    parse_update_signals,
    sanitize_schema,
    validate_title_candidate,
)
try:
    from storage import load_projects, save_projects
except Exception:
    root_dir = str(Path(__file__).resolve().parent)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    storage_module = importlib.import_module("storage")
    load_projects = getattr(storage_module, "load_projects")
    save_projects = getattr(storage_module, "save_projects")

try:
    from text_cleaning import has_markup_contamination, is_timeline_leak_text, sanitize_text_strict
except Exception:
    root_dir = str(Path(__file__).resolve().parent)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    cleaning_module = importlib.import_module("text_cleaning")
    has_markup_contamination = getattr(cleaning_module, "has_markup_contamination")
    is_timeline_leak_text = getattr(cleaning_module, "is_timeline_leak_text")
    sanitize_text_strict = getattr(cleaning_module, "sanitize_text_strict")


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
            _sort_projects_in_state()
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
        _sort_projects_in_state()

    if "last_generated_id" not in st.session_state:
        st.session_state.last_generated_id = None
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "项目库"
    if "show_creator" not in st.session_state:
        st.session_state.show_creator = False
    if "selected_project_id" not in st.session_state:
        st.session_state.selected_project_id = st.session_state.projects[0]["id"] if st.session_state.projects else None
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
    if "update_dialog_open" not in st.session_state:
        st.session_state.update_dialog_open = False
    if "update_target_project_id" not in st.session_state:
        st.session_state.update_target_project_id = ""
    if "update_draft_text" not in st.session_state:
        st.session_state.update_draft_text = ""
    if "update_status" not in st.session_state:
        st.session_state.update_status = "idle"
    if "update_error" not in st.session_state:
        st.session_state.update_error = None
    if "update_file_error" not in st.session_state:
        st.session_state.update_file_error = None
    if "update_submit_nonce" not in st.session_state:
        st.session_state.update_submit_nonce = None

    if st.session_state.projects:
        st.session_state.projects = [hard_scrub_project_for_state(project) for project in st.session_state.projects]
        _sort_projects_in_state()
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


def _parse_updated_at(value: Any) -> datetime:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=32)
    if not raw:
        return datetime.min
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return datetime.min


def _sort_projects_in_state() -> None:
    st.session_state.projects = sorted(
        st.session_state.projects,
        key=lambda item: (_parse_updated_at(item.get("updated_at")), str(item.get("id", ""))),
        reverse=True,
    )


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def replace_project_by_id(project_id: str, project: Dict[str, Any]) -> bool:
    for i, existing in enumerate(st.session_state.projects):
        if existing.get("id") == project_id:
            st.session_state.projects[i] = project
            _sort_projects_in_state()
            persist_projects()
            return True
    return False


def insert_project_top(project: Dict[str, Any]) -> None:
    st.session_state.projects.append(project)
    _sort_projects_in_state()
    persist_projects()


def persist_projects() -> None:
    save_projects(st.session_state.projects)


def delete_project_by_id(project_id: str) -> None:
    current = get_project_by_id(project_id)
    if not current:
        raise ValueError("目标项目不存在。")

    st.session_state.projects = [
        project for project in st.session_state.projects if project.get("id") != project_id
    ]
    persist_projects()

    st.session_state.delete_confirm_id = None
    if st.session_state.last_generated_id == project_id:
        st.session_state.last_generated_id = None
    if st.session_state.get("update_target_project_id") == project_id:
        st.session_state.update_target_project_id = ""
        st.session_state.update_dialog_open = False
        st.session_state.update_draft_text = ""
        st.session_state.update_status = "idle"
        st.session_state.update_error = None
        st.session_state.update_file_error = None
        st.session_state.update_submit_nonce = None

    ensure_selected_project()
    st.session_state.flash_message = "项目档案已删除。"


def submit_overlay_update(project_id: str, update_text: str, supplemental_text: str = "") -> None:
    project = get_project_by_id(project_id)
    if not project:
        raise ValueError("目标项目不存在。")

    cleaned_update = sanitize_text_strict(update_text, allow_empty=False, max_len=280)
    if not cleaned_update:
        raise ValueError("请输入有效的更新内容。")

    cleaned_supplemental = sanitize_text_strict(supplemental_text, allow_empty=True, max_len=12000)
    merged_input = cleaned_update
    if cleaned_supplemental:
        merged_input = f"{cleaned_update}\n\n{cleaned_supplemental}"

    signals = parse_update_signals(cleaned_update, project)
    context_project = apply_rule_overrides(project, signals)
    try:
        schema = structure_project(build_update_input(context_project, merged_input))
    except Exception:
        schema = sanitize_schema(
            {
                **get_export_payload(context_project),
                "latest_update": cleaned_update,
                "version_footprint": cleaned_update,
                "summary": context_project.get("summary", ""),
            }
        )

    timestamp = _now_ts()
    next_project = copy.deepcopy(project)

    # 必改字段：latest_update / updated_at
    next_project["latest_update"] = cleaned_update
    next_project["version_footprint"] = cleaned_update
    next_project["versions"] = [{"event": cleaned_update, "date": get_now_str()}]
    next_project["updated_at"] = timestamp

    # 局部可选更新字段（AI有效输出时才覆盖）
    stage_candidate = sanitize_text_strict(schema.get("stage", ""), allow_empty=True, max_len=36)
    if stage_candidate:
        next_project["stage"] = normalize_stage_value(stage_candidate)
    model_type_candidate = sanitize_text_strict(schema.get("model_type", ""), allow_empty=True, max_len=36)
    if model_type_candidate:
        next_project["model_type"] = normalize_model_type(
            model_type_candidate,
            model_desc=next_project.get("model_desc", next_project.get("model", "")),
        )
    users_candidate = sanitize_text_strict(schema.get("users", ""), allow_empty=True, max_len=44)
    if users_candidate:
        next_project["users"] = users_candidate
    use_cases_candidate = sanitize_text_strict(schema.get("use_cases", ""), allow_empty=True, max_len=120)
    if use_cases_candidate:
        next_project["use_cases"] = use_cases_candidate

    # 规则信号可更新阶段/进展标签，但不改 title/problem/solution
    next_project = apply_rule_overrides(next_project, signals)
    next_project["stage"] = normalize_stage_value(next_project.get("stage", ""))
    next_project["status_tag"] = infer_status_tag(next_project["stage"])
    next_project["status_theme"] = get_status_theme(next_project["status_tag"])

    normalized = normalize_project(next_project)
    normalized["id"] = project_id
    normalized["updated_at"] = timestamp
    normalized["latest_update"] = cleaned_update
    normalized["version_footprint"] = cleaned_update
    normalized["versions"] = [{"event": cleaned_update, "date": get_now_str()}]

    if not replace_project_by_id(project_id, normalized):
        raise ValueError("目标项目不存在。")

    st.session_state.selected_project_id = project_id
    st.session_state.last_generated_id = project_id
    st.session_state.flash_message = "项目进展已更新。"


def save_project_direct_edit(project_id: str, payload: Dict[str, Any]) -> None:
    current = get_project_by_id(project_id)
    if not current:
        raise ValueError("目标项目不存在。")

    title = sanitize_text_strict(payload.get("title", ""), allow_empty=True, max_len=42)
    if not title or not validate_title_candidate(title):
        raise ValueError("请输入有效项目名称。")

    problem_statement = sanitize_text_strict(payload.get("problem_statement", ""), allow_empty=True, max_len=220)
    solution_approach = sanitize_text_strict(payload.get("solution_approach", ""), allow_empty=True, max_len=220)
    summary = sanitize_text_strict(payload.get("summary", ""), allow_empty=True, max_len=140)
    model_desc = sanitize_text_strict(payload.get("model_desc", ""), allow_empty=True, max_len=120)
    users = sanitize_text_strict(payload.get("users", ""), allow_empty=True, max_len=120) or current.get("users", "")
    use_cases = sanitize_text_strict(payload.get("use_cases", ""), allow_empty=True, max_len=220)
    latest_update = sanitize_text_strict(payload.get("latest_update", ""), allow_empty=True, max_len=280)
    if not latest_update:
        latest_update = sanitize_text_strict(current.get("latest_update", ""), allow_empty=True, max_len=280)

    stage = normalize_stage_value(payload.get("stage", current.get("stage", "")))
    model_type = normalize_model_type(
        payload.get("model_type", current.get("model_type", "")),
        model_desc=current.get("model_desc", current.get("model", "")),
    )
    form_type = normalize_form_type(
        payload.get("form_type", current.get("form_type", "")),
        context=f"{title} {current.get('summary', '')} {current.get('model_desc', current.get('model', ''))}",
    )

    timestamp = _now_ts()
    next_project = copy.deepcopy(current)
    next_project["title"] = title
    next_project["problem_statement"] = problem_statement
    next_project["solution_approach"] = solution_approach
    next_project["summary"] = summary or sanitize_text_strict(current.get("summary", ""), allow_empty=True, max_len=140)
    next_project["model_desc"] = model_desc or sanitize_text_strict(
        current.get("model_desc", current.get("model", "")),
        allow_empty=True,
        max_len=120,
    )
    next_project["model"] = next_project["model_desc"]
    next_project["users"] = users
    next_project["use_cases"] = use_cases
    next_project["latest_update"] = latest_update
    next_project["stage"] = stage
    next_project["model_type"] = model_type
    next_project["form_type"] = form_type
    next_project["updated_at"] = timestamp
    if latest_update:
        next_project["version_footprint"] = latest_update
        next_project["versions"] = [{"event": latest_update, "date": get_now_str()}]

    normalized = normalize_project(next_project)
    normalized["id"] = project_id
    normalized["updated_at"] = timestamp

    if not replace_project_by_id(project_id, normalized):
        raise ValueError("目标项目不存在。")

    st.session_state.selected_project_id = project_id
    st.session_state.last_generated_id = project_id
    st.session_state.flash_message = "项目档案已保存。"
