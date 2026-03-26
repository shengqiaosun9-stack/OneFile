import copy
import hashlib
import importlib
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

from ai_service import build_update_input, structure_project
from project_model import (
    apply_rule_overrides,
    build_update_entry,
    derive_ops_signals,
    evolve_action_loop,
    get_status_theme,
    get_export_payload,
    get_now_str,
    hard_scrub_project_for_state,
    infer_update_kind,
    infer_status_tag,
    migrate_project_for_hygiene,
    normalize_form_type,
    normalize_model_type,
    normalize_project,
    normalize_share_state,
    normalize_stage_value,
    parse_update_signals,
    sanitize_schema,
    validate_title_candidate,
)
try:
    from storage import load_events, load_projects, load_store, load_users, save_events, save_projects, save_store, save_users
except Exception:
    root_dir = str(Path(__file__).resolve().parent)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    storage_module = importlib.import_module("storage")
    load_projects = getattr(storage_module, "load_projects")
    load_store = getattr(storage_module, "load_store")
    load_users = getattr(storage_module, "load_users")
    load_events = getattr(storage_module, "load_events")
    save_events = getattr(storage_module, "save_events")
    save_projects = getattr(storage_module, "save_projects")
    save_store = getattr(storage_module, "save_store")
    save_users = getattr(storage_module, "save_users")

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


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
EVENT_MAX_COUNT = 20000
EVENT_TYPE_VALUES = {
    "project_created",
    "project_updated",
    "next_action_completed",
    "intervention_triggered",
    "intervention_resolved",
    "share_viewed",
    "share_denied",
    "share_cta_clicked",
}


def normalize_email(email: str) -> str:
    return sanitize_text_strict(email or "", allow_empty=True, max_len=120).strip().lower()


def _sanitize_event_value(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        return sanitize_text_strict(value, allow_empty=True, max_len=120)
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str):
            return sanitize_text_strict(value, allow_empty=True, max_len=240)
        if isinstance(value, float):
            return round(value, 4)
        return value
    if isinstance(value, list):
        return [_sanitize_event_value(item, depth + 1) for item in value[:12]]
    if isinstance(value, dict):
        clean_payload: Dict[str, Any] = {}
        for key, item in list(value.items())[:20]:
            clean_key = sanitize_text_strict(key, allow_empty=True, max_len=40)
            if clean_key:
                clean_payload[clean_key] = _sanitize_event_value(item, depth + 1)
        return clean_payload
    return sanitize_text_strict(value, allow_empty=True, max_len=120)


def _sanitize_event_type(event_type: str) -> str:
    safe = sanitize_text_strict(event_type, allow_empty=True, max_len=40).lower()
    return safe if safe in EVENT_TYPE_VALUES else ""


def _sanitize_event_source(source: str) -> str:
    return sanitize_text_strict(source, allow_empty=True, max_len=40).lower() or "system"


def _get_event_ts(ts: str = "") -> str:
    base = sanitize_text_strict(ts, allow_empty=True, max_len=24)
    if base:
        return base
    return _now_ts()


def _load_events_to_session() -> None:
    if "events" not in st.session_state:
        st.session_state.events = [item for item in load_events() if isinstance(item, dict)]


def persist_events() -> None:
    _load_events_to_session()
    save_events(st.session_state.get("events", []))


def append_event(
    event_type: str,
    source: str,
    project_id: str = "",
    payload: Optional[Dict[str, Any]] = None,
    user_id: str = "",
    ts: str = "",
) -> Optional[Dict[str, Any]]:
    _load_events_to_session()
    safe_type = _sanitize_event_type(event_type)
    if not safe_type:
        return None
    safe_source = _sanitize_event_source(source)
    safe_project_id = sanitize_text_strict(project_id, allow_empty=True, max_len=24)
    safe_user_id = sanitize_text_strict(user_id, allow_empty=True, max_len=40) or get_current_user_id()
    clean_event_id = sanitize_text_strict(str(uuid.uuid4())[:12], allow_empty=False, max_len=20)
    if not clean_event_id:
        return None
    event = {
        "id": clean_event_id,
        "ts": _get_event_ts(ts),
        "user_id": safe_user_id,
        "project_id": safe_project_id,
        "event_type": safe_type,
        "source": safe_source,
        "payload": _sanitize_event_value(payload or {}, depth=0),
    }
    events = [item for item in st.session_state.get("events", []) if isinstance(item, dict)]
    events.append(event)
    if len(events) > EVENT_MAX_COUNT:
        events = events[-EVENT_MAX_COUNT:]
    st.session_state.events = events
    persist_events()
    return event


def append_event_safe(
    event_type: str,
    source: str,
    project_id: str = "",
    payload: Optional[Dict[str, Any]] = None,
    user_id: str = "",
    ts: str = "",
) -> Optional[Dict[str, Any]]:
    try:
        return append_event(
            event_type=event_type,
            source=source,
            project_id=project_id,
            payload=payload,
            user_id=user_id,
            ts=ts,
        )
    except Exception:
        return None


def get_recent_project_events(project_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    _load_events_to_session()
    pid = sanitize_text_strict(project_id, allow_empty=True, max_len=24)
    if not pid:
        return []
    rows = [item for item in st.session_state.get("events", []) if isinstance(item, dict) and sanitize_text_strict(item.get("project_id", ""), allow_empty=True, max_len=24) == pid]
    rows = sorted(rows, key=lambda item: sanitize_text_strict(item.get("ts", ""), allow_empty=True, max_len=24), reverse=True)
    return rows[: max(limit, 1)]


def _emit_loop_transition_events(
    previous_project: Dict[str, Any],
    current_project: Dict[str, Any],
    project_id: str,
    source: str,
    timestamp: str,
) -> None:
    prev_intervention = previous_project.get("intervention", {}) if isinstance(previous_project.get("intervention", {}), dict) else {}
    curr_intervention = current_project.get("intervention", {}) if isinstance(current_project.get("intervention", {}), dict) else {}
    prev_status = sanitize_text_strict(prev_intervention.get("status", ""), allow_empty=True, max_len=16).lower()
    curr_status = sanitize_text_strict(curr_intervention.get("status", ""), allow_empty=True, max_len=16).lower()

    if prev_status != "active" and curr_status == "active":
        append_event_safe(
            event_type="intervention_triggered",
            source=source,
            project_id=project_id,
            ts=timestamp,
            payload={
                "type": curr_intervention.get("type", ""),
                "message": curr_intervention.get("message", ""),
            },
        )
    if prev_status == "active" and curr_status in {"resolved", "idle"}:
        append_event_safe(
            event_type="intervention_resolved",
            source=source,
            project_id=project_id,
            ts=timestamp,
            payload={
                "type": prev_intervention.get("type", ""),
                "effectiveness": current_project.get("last_intervention_effectiveness", "unknown"),
            },
        )

    latest_update = (current_project.get("updates", []) or [None])[0]
    if isinstance(latest_update, dict) and bool(latest_update.get("completion_signal", False)):
        append_event_safe(
            event_type="next_action_completed",
            source=source,
            project_id=project_id,
            ts=timestamp,
            payload={
                "kind": latest_update.get("kind", ""),
                "evidence_score": latest_update.get("evidence_score", 0),
                "action_alignment": latest_update.get("action_alignment", 0),
            },
        )


def _make_user_id(email: str) -> str:
    digest = hashlib.sha1(email.encode("utf-8")).hexdigest()[:12]
    return f"u_{digest}"


def get_current_user_id() -> str:
    return sanitize_text_strict(st.session_state.get("current_user_id", ""), allow_empty=True, max_len=40)


def get_current_user_email() -> str:
    return sanitize_text_strict(st.session_state.get("current_user_email", ""), allow_empty=True, max_len=120)


def is_authenticated() -> bool:
    return bool(get_current_user_id() and get_current_user_email())


def _save_users_to_session_and_store(users: List[Dict[str, Any]]) -> None:
    st.session_state.users = users
    save_users(users)


def register_or_login_user(email: str) -> Dict[str, Any]:
    normalized_email = normalize_email(email)
    if not normalized_email or not EMAIL_PATTERN.match(normalized_email):
        raise ValueError("请输入有效邮箱地址。")

    users = list(st.session_state.get("users", []))
    now = _now_ts()
    existing = next((u for u in users if normalize_email(u.get("email", "")) == normalized_email), None)
    if existing:
        existing["last_seen_at"] = now
        existing["status"] = "active"
        user = existing
    else:
        user = {
            "id": _make_user_id(normalized_email),
            "email": normalized_email,
            "created_at": now,
            "last_seen_at": now,
            "status": "active",
        }
        users.append(user)
    _save_users_to_session_and_store(users)
    st.session_state.current_user_id = user["id"]
    st.session_state.current_user_email = user["email"]
    _migrate_unowned_projects_to_current_user()
    ensure_selected_project()
    return user


def _migrate_unowned_projects_to_current_user() -> None:
    current_user_id = get_current_user_id()
    if not current_user_id:
        return
    changed = False
    migrated = []
    for project in st.session_state.get("projects", []):
        next_project = copy.deepcopy(project)
        if not sanitize_text_strict(next_project.get("owner_user_id", ""), allow_empty=True, max_len=40):
            next_project["owner_user_id"] = current_user_id
            changed = True
        migrated.append(normalize_project(next_project))
    if changed:
        st.session_state.projects = migrated
        persist_projects()


def get_visible_projects() -> List[Dict[str, Any]]:
    current_user_id = get_current_user_id()
    if not current_user_id:
        return []
    projects = st.session_state.get("projects", [])
    return [item for item in projects if sanitize_text_strict(item.get("owner_user_id", ""), allow_empty=True, max_len=40) == current_user_id]


def refresh_ops_signals_from_events(project_ids: Optional[List[str]] = None, persist: bool = False) -> bool:
    _load_events_to_session()
    events = st.session_state.get("events", [])
    projects = st.session_state.get("projects", [])
    if not isinstance(projects, list):
        return False
    target_ids = set()
    if isinstance(project_ids, list) and project_ids:
        target_ids = {
            sanitize_text_strict(item, allow_empty=True, max_len=24)
            for item in project_ids
            if sanitize_text_strict(item, allow_empty=True, max_len=24)
        }
    changed = False
    updated_projects: List[Dict[str, Any]] = []
    now_ts = _now_ts()
    for project in projects:
        if not isinstance(project, dict):
            continue
        pid = sanitize_text_strict(project.get("id", ""), allow_empty=True, max_len=24)
        next_project = copy.deepcopy(project)
        if not target_ids or pid in target_ids:
            derived = derive_ops_signals(pid, events, now_ts=now_ts)
            if next_project.get("ops_signals") != derived:
                next_project["ops_signals"] = derived
                changed = True
        updated_projects.append(next_project)
    if changed:
        st.session_state.projects = updated_projects
        _sort_projects_in_state()
        if persist:
            persist_projects()
    return changed


def rebuild_ops_signals_from_events(persist: bool = True) -> bool:
    return refresh_ops_signals_from_events(project_ids=None, persist=persist)


def get_pending_projects(limit: int = 4) -> List[Dict[str, Any]]:
    visible = get_visible_projects()
    pending: List[Dict[str, Any]] = []
    for project in visible:
        next_action = project.get("next_action", {}) if isinstance(project.get("next_action", {}), dict) else {}
        status = sanitize_text_strict(next_action.get("status", ""), allow_empty=True, max_len=16).lower()
        if status in {"open", "stale"}:
            pending.append(project)

    def _risk_key(item: Dict[str, Any]) -> tuple:
        progress = item.get("progress_eval", {}) if isinstance(item.get("progress_eval", {}), dict) else {}
        progress_status = sanitize_text_strict(progress.get("status", ""), allow_empty=True, max_len=16).lower()
        try:
            progress_score = int(progress.get("score", 50))
        except Exception:
            progress_score = 50
        progress_score = max(0, min(progress_score, 100))
        next_action = item.get("next_action", {}) if isinstance(item.get("next_action", {}), dict) else {}
        next_status = sanitize_text_strict(next_action.get("status", ""), allow_empty=True, max_len=16).lower()
        intervention = item.get("intervention", {}) if isinstance(item.get("intervention", {}), dict) else {}
        intervention_status = sanitize_text_strict(intervention.get("status", ""), allow_empty=True, max_len=16).lower()
        intervention_type = sanitize_text_strict(intervention.get("type", ""), allow_empty=True, max_len=24).lower()
        ops = item.get("ops_signals", {}) if isinstance(item.get("ops_signals", {}), dict) else {}
        updates_7d = max(int(ops.get("updates_7d", 0) or 0), 0)
        completed_14d = max(int(ops.get("completed_actions_14d", 0) or 0), 0)
        intervention_rate = float(ops.get("intervention_trigger_rate_14d", 0.0) or 0.0)
        intervention_rate = max(0.0, min(intervention_rate, 1.0))
        last_activity_raw = sanitize_text_strict(ops.get("last_activity_at", ""), allow_empty=True, max_len=24)
        last_activity_dt = _parse_updated_at(last_activity_raw) if last_activity_raw else datetime.max

        # Primary driver: evidence risk (events/ops_signals)
        evidence_risk = 0
        if updates_7d == 0:
            evidence_risk += 26
        elif updates_7d == 1:
            evidence_risk += 14
        if completed_14d == 0:
            evidence_risk += 34
        elif completed_14d == 1:
            evidence_risk += 10
        if last_activity_dt != datetime.max:
            inactive_days = max((datetime.now().date() - last_activity_dt.date()).days, 0)
            if inactive_days >= 7:
                evidence_risk += 28
            elif inactive_days >= 3:
                evidence_risk += 14
        if intervention_rate > 0.6:
            evidence_risk += 16
        elif intervention_rate > 0.35:
            evidence_risk += 8

        # Secondary: current inferred state
        secondary_risk = 100 - progress_score
        if progress_status == "stalled":
            secondary_risk += 24
        elif progress_status == "uncertain":
            secondary_risk += 10
        if next_status == "stale":
            secondary_risk += 12
        elif next_status == "open":
            secondary_risk += 6

        # Tertiary: active intervention
        tertiary_risk = 0
        if intervention_status == "active":
            tertiary_risk += 8
            if intervention_type == "stuck_replan":
                tertiary_risk += 4

        total_risk = evidence_risk + secondary_risk + tertiary_risk
        updated_at = _parse_updated_at(item.get("updated_at"))
        stale_rank = 0 if next_status == "stale" else 1
        project_id = sanitize_text_strict(item.get("id", ""), allow_empty=True, max_len=24)
        return (
            -total_risk,  # risk desc
            stale_rank,  # stale before open
            last_activity_dt,  # last_activity asc
            updated_at,  # updated_at asc
            project_id,  # deterministic fallback
        )

    pending = sorted(pending, key=_risk_key)
    return pending[: max(limit, 1)]


def get_project_by_id_any(project_id: str) -> Optional[Dict[str, Any]]:
    target = sanitize_text_strict(project_id or "", allow_empty=True, max_len=24)
    if not target:
        return None
    return next((project for project in st.session_state.get("projects", []) if project.get("id") == target), None)


def init_state() -> None:
    if "projects" not in st.session_state:
        store = load_store()
        loaded_projects = store.get("projects", [])
        sanitized_projects = []
        for project in loaded_projects:
            if _contains_legacy_markup_payload(project):
                continue
            sanitized_projects.append(hard_scrub_project_for_state(migrate_project_for_hygiene(project)))
        st.session_state.projects = sanitized_projects
        st.session_state.users = store.get("users", [])
        st.session_state.events = [item for item in store.get("events", []) if isinstance(item, dict)]
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
        if "users" not in st.session_state:
            st.session_state.users = load_users()
        if "events" not in st.session_state:
            st.session_state.events = [item for item in load_events() if isinstance(item, dict)]

    if "last_generated_id" not in st.session_state:
        st.session_state.last_generated_id = None
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "项目库"
    if "users" not in st.session_state:
        st.session_state.users = load_users()
    if "events" not in st.session_state:
        st.session_state.events = [item for item in load_events() if isinstance(item, dict)]
    if "current_user_id" not in st.session_state:
        st.session_state.current_user_id = ""
    if "current_user_email" not in st.session_state:
        st.session_state.current_user_email = ""
    if "show_creator" not in st.session_state:
        st.session_state.show_creator = False
    if "selected_project_id" not in st.session_state:
        visible = get_visible_projects()
        st.session_state.selected_project_id = visible[0]["id"] if visible else None
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
        ops_changed = refresh_ops_signals_from_events(project_ids=None, persist=False)
        if not st.session_state.data_hygiene_v3_done:
            persist_projects()
            st.session_state.data_hygiene_v3_done = True
        elif ops_changed:
            persist_projects()
    if is_authenticated():
        _migrate_unowned_projects_to_current_user()
    ensure_selected_project()


def ensure_selected_project() -> None:
    visible_projects = get_visible_projects()
    if not visible_projects:
        st.session_state.selected_project_id = None
        return
    valid_ids = {project.get("id") for project in visible_projects}
    if st.session_state.selected_project_id not in valid_ids:
        st.session_state.selected_project_id = visible_projects[0]["id"]


def get_project_by_id(project_id: str) -> Optional[Dict[str, Any]]:
    current_user_id = get_current_user_id()
    if not current_user_id:
        return None
    return next(
        (
            project
            for project in st.session_state.get("projects", [])
            if project.get("id") == project_id
            and sanitize_text_strict(project.get("owner_user_id", ""), allow_empty=True, max_len=40) == current_user_id
        ),
        None,
    )


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
    current_user_id = get_current_user_id()
    next_project = copy.deepcopy(project)
    if current_user_id and not sanitize_text_strict(next_project.get("owner_user_id", ""), allow_empty=True, max_len=40):
        next_project["owner_user_id"] = current_user_id
    next_project["share"] = normalize_share_state(next_project.get("share", {}), next_project.get("id", ""))
    st.session_state.projects.append(normalize_project(next_project))
    _sort_projects_in_state()
    persist_projects()
    project_id = sanitize_text_strict(next_project.get("id", ""), allow_empty=True, max_len=24)
    if project_id:
        first_update = (next_project.get("updates", []) or [None])[0]
        input_meta = first_update.get("input_meta", {}) if isinstance(first_update, dict) else {}
        append_event_safe(
            event_type="project_created",
            source="create_overlay",
            project_id=project_id,
            payload={
                "stage": next_project.get("stage", ""),
                "has_file": bool(input_meta.get("has_file", False)),
                "merged_chars": int(input_meta.get("merged_chars", 0) or 0),
            },
        )
        refresh_ops_signals_from_events(project_ids=[project_id], persist=True)


def persist_projects() -> None:
    save_projects(st.session_state.projects)


def set_project_share_state(project_id: str, is_public: bool) -> None:
    project = get_project_by_id(project_id)
    if not project:
        raise ValueError("目标项目不存在。")
    next_project = copy.deepcopy(project)
    share = normalize_share_state(next_project.get("share", {}), next_project.get("id", project_id))
    now = _now_ts()
    share["is_public"] = bool(is_public)
    if share["is_public"]:
        if not share.get("published_at"):
            share["published_at"] = now
        share["last_shared_at"] = now
    next_project["share"] = share
    next_project["updated_at"] = now
    normalized = normalize_project(next_project)
    normalized["id"] = project_id
    if not replace_project_by_id(project_id, normalized):
        raise ValueError("目标项目不存在。")
    st.session_state.selected_project_id = project_id
    st.session_state.flash_message = "分享状态已更新。"


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
    previous_project = copy.deepcopy(project)

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
    current_user_id = get_current_user_id()
    update_kind = infer_update_kind(cleaned_update)

    # 必改字段：latest_update / updated_at
    next_project["latest_update"] = cleaned_update
    next_project["version_footprint"] = cleaned_update
    next_project["updated_at"] = timestamp

    existing_updates = next_project.get("updates", [])
    if not isinstance(existing_updates, list):
        existing_updates = []
    new_update = build_update_entry(
        project_id=project_id,
        author_user_id=current_user_id or next_project.get("owner_user_id", ""),
        content=cleaned_update,
        source="overlay_update",
        created_at=timestamp,
        input_meta={
            "has_text": True,
            "has_file": bool(cleaned_supplemental),
            "merged_chars": len(merged_input),
        },
        kind=update_kind,
        next_action_text=(next_project.get("next_action", {}) or {}).get("text", ""),
    )
    next_project["updates"] = [new_update] + [item for item in existing_updates if isinstance(item, dict)]

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
    next_project = evolve_action_loop(next_project, cleaned_update, timestamp)

    normalized = normalize_project(next_project)
    normalized["id"] = project_id
    normalized["updated_at"] = timestamp
    normalized["latest_update"] = cleaned_update
    normalized["version_footprint"] = cleaned_update

    if not replace_project_by_id(project_id, normalized):
        raise ValueError("目标项目不存在。")

    append_event_safe(
        event_type="project_updated",
        source="overlay_update",
        project_id=project_id,
        ts=timestamp,
        payload={
            "kind": new_update.get("kind", ""),
            "evidence_score": new_update.get("evidence_score", 0),
            "action_alignment": new_update.get("action_alignment", 0),
            "completion_signal": bool(new_update.get("completion_signal", False)),
            "has_file": bool(cleaned_supplemental),
        },
    )
    _emit_loop_transition_events(
        previous_project=previous_project,
        current_project=normalized,
        project_id=project_id,
        source="overlay_update",
        timestamp=timestamp,
    )
    refresh_ops_signals_from_events(project_ids=[project_id], persist=True)

    st.session_state.selected_project_id = project_id
    st.session_state.last_generated_id = project_id
    st.session_state.flash_message = "项目进展已更新，系统已评估推进状态并刷新下一步建议。"


def save_project_direct_edit(project_id: str, payload: Dict[str, Any]) -> None:
    current = get_project_by_id(project_id)
    if not current:
        raise ValueError("目标项目不存在。")
    previous_project = copy.deepcopy(current)

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
    current_user_id = get_current_user_id()
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
        update_kind = infer_update_kind(latest_update)
        next_project["version_footprint"] = latest_update
        next_project["versions"] = [{"event": latest_update, "date": get_now_str()}]
        existing_updates = next_project.get("updates", [])
        if not isinstance(existing_updates, list):
            existing_updates = []
        new_update = build_update_entry(
            project_id=project_id,
            author_user_id=current_user_id or next_project.get("owner_user_id", ""),
            content=latest_update,
            source="direct_edit",
            created_at=timestamp,
            input_meta={"has_text": True, "has_file": False, "merged_chars": len(latest_update)},
            kind=update_kind,
            next_action_text=(next_project.get("next_action", {}) or {}).get("text", ""),
        )
        next_project["updates"] = [new_update] + [item for item in existing_updates if isinstance(item, dict)]
    next_project = evolve_action_loop(next_project, latest_update or next_project.get("latest_update", ""), timestamp)

    normalized = normalize_project(next_project)
    normalized["id"] = project_id
    normalized["updated_at"] = timestamp

    if not replace_project_by_id(project_id, normalized):
        raise ValueError("目标项目不存在。")

    append_event_safe(
        event_type="project_updated",
        source="direct_edit",
        project_id=project_id,
        ts=timestamp,
        payload={
            "kind": "direct_edit",
            "completion_signal": bool((normalized.get("updates", []) or [{}])[0].get("completion_signal", False)),
        },
    )
    _emit_loop_transition_events(
        previous_project=previous_project,
        current_project=normalized,
        project_id=project_id,
        source="direct_edit",
        timestamp=timestamp,
    )
    refresh_ops_signals_from_events(project_ids=[project_id], persist=True)

    st.session_state.selected_project_id = project_id
    st.session_state.last_generated_id = project_id
    st.session_state.flash_message = "项目档案已保存，系统已重新评估项目推进状态。"
