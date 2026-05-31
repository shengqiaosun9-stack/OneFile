import copy
import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ai_service import (
    build_update_input,
    create_chat_completion,
    extract_json_object,
    get_ai_provider,
    get_client,
    get_last_structuring_meta,
    get_model_name,
    structure_project,
    structure_project_object,
)
from backend.config import get_settings
from backend.email_sender import EmailSendError, build_email_sender
from project_model import (
    apply_rule_overrides,
    build_update_entry,
    derive_ops_signals,
    enrich_generated_project,
    evolve_action_loop,
    get_now_str,
    get_status_theme,
    hard_scrub_project_for_state,
    infer_update_kind,
    infer_status_tag,
    migrate_project_for_hygiene,
    normalize_form_type,
    normalize_business_model_type,
    normalize_model_type,
    normalize_project,
    normalize_share_state,
    normalize_stage_value,
    parse_update_signals,
    sanitize_schema,
    validate_title_candidate,
)
from backend.repository import get_store_repository
from text_cleaning import has_markup_contamination, is_timeline_leak_text, sanitize_text_strict

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
SESSION_TOKEN_MIN_LENGTH = 32
EVENT_MAX_COUNT = 20000
EVENT_TYPE_VALUES = {
    "auth_code_requested",
    "project_created",
    "project_updated",
    "next_action_completed",
    "intervention_triggered",
    "intervention_resolved",
    "share_published",
    "share_unpublished",
    "share_viewed",
    "share_denied",
    "share_cta_clicked",
    "share_conversion_attributed",
    "share_conversion_skipped",
    "portfolio_viewed",
    "weekly_report_generated",
    "intervention_learning_viewed",
    "ai_structuring_fallback",
}
FALLBACK_WARNING_TEXT = "AI 服务暂不可用，已自动使用本地规则完成结构化。"
OPS_STORE_KEYS = [
    "ops_inbox_items",
    "ops_people",
    "ops_organizations",
    "ops_projects",
    "ops_opportunities",
    "ops_needs",
    "ops_offers",
    "ops_interactions",
    "ops_contents",
    "ops_next_actions",
    "ops_leads",
    "ops_profiles",
    "ops_activities",
    "ops_activity_memberships",
    "ops_routing_records",
    "ops_events",
]
BP_STORE_KEYS = [
    "bp_projects",
    "bp_raw_materials",
    "bp_project_insights",
    "bp_evidence",
    "bp_pages",
    "bp_gap_reports",
    "bp_service_requests",
    "bp_feedback",
    "bp_next_actions",
    "bp_versions",
]
OPS_PROFILE_BOOL_FIELDS = [
    "has_budget",
    "accepts_paid_service",
    "accepts_equity_or_revenue_share",
    "seeking_cofounder",
    "needs_investment",
    "needs_customers",
    "needs_tech",
    "needs_content_growth",
    "needs_private_domain",
    "needs_industry_scene",
    "needs_school_scene",
    "needs_park_scene",
    "needs_medical_scene",
    "suitable_offline_event",
    "suitable_remote_interview",
    "suitable_content_interview",
    "accepts_filming",
]
TECH_NEED_TYPES = {"cofounder", "outsourcing", "part_time", "advisor", "long_term_cto", "none", "unknown"}
TECH_OFFER_TYPES = {"paid", "revenue_share", "cofounder", "freelance", "none", "unknown"}
OPS_SUBJECT_TYPES = {"lead", "project"}
OPS_PENDING_ROUTING_STATUSES = {"想法", "待介绍", "已介绍", "推进中"}


class ServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _build_structuring_warning(meta: Dict[str, Any]) -> Optional[str]:
    if not bool(meta.get("used_local_structuring", False)):
        return None
    # Never expose provider internals (e.g. missing API keys) to end users.
    return FALLBACK_WARNING_TEXT


def _record_ai_fallback_event(
    state: Dict[str, Any],
    *,
    user_id: str,
    source: str,
    project_id: str = "",
    meta: Optional[Dict[str, Any]] = None,
    ts: str = "",
) -> None:
    payload_meta = meta or {}
    if not bool(payload_meta.get("used_local_structuring", False)):
        return
    _append_event(
        state=state,
        event_type="ai_structuring_fallback",
        source=source,
        user_id=user_id,
        project_id=project_id,
        ts=ts or _now_ts(),
        payload={
            "error_type": sanitize_text_strict(payload_meta.get("last_api_error_type", ""), allow_empty=True, max_len=32) or "unknown",
            "has_error": bool(sanitize_text_strict(payload_meta.get("last_api_error", ""), allow_empty=True, max_len=180)),
        },
    )


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


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


def _sort_projects(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        projects,
        key=lambda item: (_parse_updated_at(item.get("updated_at")), str(item.get("id", ""))),
        reverse=True,
    )


def normalize_email(email: str) -> str:
    return sanitize_text_strict(email or "", allow_empty=True, max_len=120).strip().lower()


def _make_user_id(email: str) -> str:
    digest = hashlib.sha1(email.encode("utf-8")).hexdigest()[:12]
    return f"u_{digest}"


def _hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now_datetime() -> datetime:
    parsed = _parse_updated_at(_now_ts())
    if parsed != datetime.min:
        return parsed
    return datetime.now()


def _generate_login_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _prune_auth_state(state: Dict[str, Any]) -> bool:
    changed = False
    now_dt = _now_datetime()

    challenges: List[Dict[str, Any]] = []
    for item in state.get("auth_challenges", []):
        if not isinstance(item, dict):
            changed = True
            continue
        expires_at = _parse_updated_at(item.get("expires_at", ""))
        if expires_at == datetime.min or expires_at < now_dt:
            changed = True
            continue
        attempts = int(item.get("attempts", 0) or 0)
        max_attempts = int(item.get("max_attempts", get_settings().auth_code_max_attempts) or get_settings().auth_code_max_attempts)
        if attempts >= max_attempts:
            changed = True
            continue
        challenges.append(item)

    sessions: List[Dict[str, Any]] = []
    for item in state.get("auth_sessions", []):
        if not isinstance(item, dict):
            changed = True
            continue
        expires_at = _parse_updated_at(item.get("expires_at", ""))
        if expires_at == datetime.min or expires_at < now_dt:
            changed = True
            continue
        token_hash = sanitize_text_strict(item.get("token_hash", ""), allow_empty=True, max_len=80)
        if len(token_hash) < 24:
            changed = True
            continue
        sessions.append(item)

    if changed:
        state["auth_challenges"] = challenges
        state["auth_sessions"] = sessions
    return changed


def _count_recent_auth_code_requests(state: Dict[str, Any], email: str, now_dt: datetime) -> int:
    normalized_email = normalize_email(email)
    if not normalized_email:
        return 0
    window_start = now_dt - timedelta(hours=1)
    total = 0
    for item in state.get("events", []):
        if not isinstance(item, dict):
            continue
        if sanitize_text_strict(item.get("event_type", ""), allow_empty=True, max_len=40).lower() != "auth_code_requested":
            continue
        payload = item.get("payload", {}) if isinstance(item.get("payload", {}), dict) else {}
        if normalize_email(payload.get("email", "")) != normalized_email:
            continue
        ts = _parse_updated_at(item.get("ts", ""))
        if ts == datetime.min or ts < window_start:
            continue
        total += 1
    return total


def _sanitize_ip(ip: str) -> str:
    raw = sanitize_text_strict(ip or "", allow_empty=True, max_len=64).strip()
    if not raw:
        return ""
    return raw.split(",")[0].strip()


def _ip_hash(ip: str) -> str:
    safe_ip = _sanitize_ip(ip)
    if not safe_ip:
        return ""
    return hashlib.sha256(safe_ip.encode("utf-8")).hexdigest()[:16]


def _count_recent_auth_code_requests_by_ip(state: Dict[str, Any], ip: str, now_dt: datetime) -> int:
    token = _ip_hash(ip)
    if not token:
        return 0
    window_start = now_dt - timedelta(hours=1)
    total = 0
    for item in state.get("events", []):
        if not isinstance(item, dict):
            continue
        if sanitize_text_strict(item.get("event_type", ""), allow_empty=True, max_len=40).lower() != "auth_code_requested":
            continue
        payload = item.get("payload", {}) if isinstance(item.get("payload", {}), dict) else {}
        if sanitize_text_strict(payload.get("ip_hash", ""), allow_empty=True, max_len=24) != token:
            continue
        ts = _parse_updated_at(item.get("ts", ""))
        if ts == datetime.min or ts < window_start:
            continue
        total += 1
    return total


def start_login(email: str, client_ip: str = "") -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)
    changed = _migrate_unowned_projects(state, user["id"])
    changed = _prune_auth_state(state) or changed

    normalized_email = normalize_email(email)
    now_dt = _now_datetime()
    if _count_recent_auth_code_requests(state, normalized_email, now_dt) >= get_settings().auth_start_max_per_hour:
        raise ServiceError(429, "too_many_requests", "验证码请求过于频繁，请稍后再试。")
    if _count_recent_auth_code_requests_by_ip(state, client_ip, now_dt) >= get_settings().auth_start_max_per_ip_hour:
        raise ServiceError(429, "too_many_requests", "当前网络请求过于频繁，请稍后再试。")

    code = _generate_login_code()
    ttl_minutes = get_settings().auth_code_ttl_minutes
    expires_at = (now_dt + timedelta(minutes=ttl_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    challenge_id = uuid.uuid4().hex[:16]

    remaining = []
    for item in state.get("auth_challenges", []):
        if normalize_email(item.get("email", "")) == normalized_email:
            continue
        remaining.append(item)
    remaining.append(
        {
            "id": challenge_id,
            "email": normalized_email,
            "code_hash": _hash_secret(code),
            "created_at": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at": expires_at,
            "attempts": 0,
            "max_attempts": get_settings().auth_code_max_attempts,
        }
    )
    if not get_settings().auth_debug_codes:
        sender = build_email_sender(get_settings())
        try:
            sender.send_login_code(normalized_email, code, ttl_minutes)
        except EmailSendError as exc:
            if str(exc) == "email_not_configured":
                raise ServiceError(503, "email_not_configured", "验证码服务尚未配置，请稍后再试。") from None
            raise ServiceError(503, "email_send_failed", "验证码发送失败，请稍后重试。") from None

    state["auth_challenges"] = remaining
    _append_event(
        state=state,
        event_type="auth_code_requested",
        source="auth_login_start",
        user_id=user["id"],
        ts=now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        payload={"email": normalized_email, "ip_hash": _ip_hash(client_ip)},
    )
    save_state(state)

    response: Dict[str, Any] = {
        "ok": True,
        "challenge_id": challenge_id,
        "expires_in_seconds": ttl_minutes * 60,
    }
    if get_settings().auth_debug_codes:
        response["debug_code"] = code
    return response


def verify_login(email: str, challenge_id: str, code: str) -> Dict[str, Any]:
    state = load_state()
    _prune_auth_state(state)
    normalized_email = normalize_email(email)
    if not normalized_email or not EMAIL_PATTERN.match(normalized_email):
        raise ServiceError(400, "invalid_email", "请输入有效邮箱地址。")

    safe_challenge_id = sanitize_text_strict(challenge_id, allow_empty=True, max_len=24)
    safe_code = sanitize_text_strict(code, allow_empty=True, max_len=12)
    if not safe_challenge_id or not safe_code:
        raise ServiceError(400, "invalid_code", "验证码无效，请重试。")

    challenges: List[Dict[str, Any]] = []
    matched: Optional[Dict[str, Any]] = None
    for item in state.get("auth_challenges", []):
        if not isinstance(item, dict):
            continue
        if sanitize_text_strict(item.get("id", ""), allow_empty=True, max_len=24) == safe_challenge_id and normalize_email(item.get("email", "")) == normalized_email:
            matched = item
            continue
        challenges.append(item)

    if not matched:
        state["auth_challenges"] = challenges
        save_state(state)
        raise ServiceError(400, "invalid_code", "验证码无效或已过期。")

    max_attempts = int(matched.get("max_attempts", get_settings().auth_code_max_attempts) or get_settings().auth_code_max_attempts)
    attempts = int(matched.get("attempts", 0) or 0)
    if _hash_secret(safe_code) != sanitize_text_strict(matched.get("code_hash", ""), allow_empty=True, max_len=80):
        attempts += 1
        if attempts < max_attempts:
            matched["attempts"] = attempts
            challenges.append(matched)
            state["auth_challenges"] = challenges
            save_state(state)
            raise ServiceError(400, "invalid_code", "验证码错误，请重试。")
        state["auth_challenges"] = challenges
        save_state(state)
        raise ServiceError(429, "too_many_attempts", "验证码尝试次数过多，请重新获取。")

    user = _ensure_user(state, normalized_email)
    _migrate_unowned_projects(state, user["id"])

    token_raw = f"{uuid.uuid4().hex}{uuid.uuid4().hex}"
    token_hash = _hash_secret(token_raw)
    now_dt = _now_datetime()
    expires_at = (now_dt + timedelta(days=get_settings().auth_session_ttl_days)).strftime("%Y-%m-%d %H:%M:%S")
    state["auth_challenges"] = challenges
    sessions = [item for item in state.get("auth_sessions", []) if normalize_email(item.get("email", "")) != normalized_email]
    sessions.append(
        {
            "id": uuid.uuid4().hex[:16],
            "token_hash": token_hash,
            "user_id": user["id"],
            "email": normalized_email,
            "created_at": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "last_seen_at": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at": expires_at,
        }
    )
    state["auth_sessions"] = sessions
    save_state(state)

    return {
        "user": user,
        "projects": _get_visible_projects(state, user["id"]),
        "session_token": token_raw,
        "expires_at": expires_at,
    }


def get_session_user(session_token: str) -> Optional[Dict[str, Any]]:
    safe_token = sanitize_text_strict(session_token, allow_empty=True, max_len=200)
    if len(safe_token) < SESSION_TOKEN_MIN_LENGTH:
        return None

    state = load_state()
    changed = _prune_auth_state(state)
    token_hash = _hash_secret(safe_token)
    sessions: List[Dict[str, Any]] = []
    matched: Optional[Dict[str, Any]] = None
    for item in state.get("auth_sessions", []):
        if not isinstance(item, dict):
            changed = True
            continue
        current_hash = sanitize_text_strict(item.get("token_hash", ""), allow_empty=True, max_len=80)
        if current_hash == token_hash:
            matched = item
            continue
        sessions.append(item)

    if not matched:
        if changed:
            state["auth_sessions"] = sessions
            save_state(state)
        return None

    normalized_email = normalize_email(matched.get("email", ""))
    if not normalized_email:
        state["auth_sessions"] = sessions
        save_state(state)
        return None

    user = _ensure_user(state, normalized_email)
    matched["last_seen_at"] = _now_ts()
    sessions.append(matched)
    state["auth_sessions"] = sessions
    save_state(state)
    return user


def logout_session(session_token: str) -> Dict[str, Any]:
    safe_token = sanitize_text_strict(session_token, allow_empty=True, max_len=200)
    if len(safe_token) < SESSION_TOKEN_MIN_LENGTH:
        return {"ok": True}

    state = load_state()
    token_hash = _hash_secret(safe_token)
    sessions = [
        item
        for item in state.get("auth_sessions", [])
        if sanitize_text_strict(item.get("token_hash", ""), allow_empty=True, max_len=80) != token_hash
    ]
    state["auth_sessions"] = sessions
    save_state(state)
    return {"ok": True}


def _sanitize_event_type(event_type: str) -> str:
    safe = sanitize_text_strict(event_type, allow_empty=True, max_len=40).lower()
    return safe if safe in EVENT_TYPE_VALUES else ""


def _sanitize_event_source(source: str) -> str:
    return sanitize_text_strict(source, allow_empty=True, max_len=40).lower() or "system"


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


def load_state() -> Dict[str, Any]:
    store = get_store_repository().load_store()
    projects = store.get("projects", []) if isinstance(store.get("projects", []), list) else []
    users = store.get("users", []) if isinstance(store.get("users", []), list) else []
    events = [item for item in (store.get("events", []) or []) if isinstance(item, dict)]
    auth_challenges = [item for item in (store.get("auth_challenges", []) or []) if isinstance(item, dict)]
    auth_sessions = [item for item in (store.get("auth_sessions", []) or []) if isinstance(item, dict)]

    sanitized_projects: List[Dict[str, Any]] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        if _contains_legacy_markup_payload(project):
            continue
        sanitized_projects.append(hard_scrub_project_for_state(migrate_project_for_hygiene(project)))

    state = {
        "schema_version": int(store.get("schema_version", 2)),
        "users": [item for item in users if isinstance(item, dict)],
        "projects": _sort_projects(sanitized_projects),
        "events": events,
        "auth_challenges": auth_challenges,
        "auth_sessions": auth_sessions,
    }
    for key in BP_STORE_KEYS + OPS_STORE_KEYS:
        state[key] = [item for item in (store.get(key, []) or []) if isinstance(item, dict)]
    return state


def save_state(state: Dict[str, Any]) -> None:
    payload = {
        "schema_version": int(state.get("schema_version", 2)),
        "users": [item for item in state.get("users", []) if isinstance(item, dict)],
        "projects": _sort_projects([item for item in state.get("projects", []) if isinstance(item, dict)]),
        "events": [item for item in state.get("events", []) if isinstance(item, dict)],
        "auth_challenges": [item for item in state.get("auth_challenges", []) if isinstance(item, dict)],
        "auth_sessions": [item for item in state.get("auth_sessions", []) if isinstance(item, dict)],
    }
    for key in BP_STORE_KEYS + OPS_STORE_KEYS:
        payload[key] = [item for item in state.get(key, []) if isinstance(item, dict)]
    get_store_repository().save_store(payload)


def _ensure_user(state: Dict[str, Any], email: str) -> Dict[str, Any]:
    normalized_email = normalize_email(email)
    if not normalized_email or not EMAIL_PATTERN.match(normalized_email):
        raise ServiceError(400, "invalid_email", "请输入有效邮箱地址。")

    users = list(state.get("users", []))
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
    state["users"] = users
    return user


def _migrate_unowned_projects(state: Dict[str, Any], user_id: str) -> bool:
    changed = False
    migrated: List[Dict[str, Any]] = []
    for project in state.get("projects", []):
        next_project = copy.deepcopy(project)
        owner_id = sanitize_text_strict(next_project.get("owner_user_id", ""), allow_empty=True, max_len=40)
        entity_type = sanitize_text_strict(next_project.get("entity_type", ""), allow_empty=True, max_len=24).lower()
        if not owner_id and entity_type != "temporary_card":
            next_project["owner_user_id"] = user_id
            changed = True
        migrated.append(next_project)
    state["projects"] = migrated
    return changed


def _get_visible_projects(state: Dict[str, Any], user_id: str) -> List[Dict[str, Any]]:
    visible: List[Dict[str, Any]] = []
    for item in state.get("projects", []):
        if not bool(item.get("visible_in_library", True)):
            continue
        owner_id = sanitize_text_strict(item.get("owner_user_id", ""), allow_empty=True, max_len=40)
        share_state = item.get("share", {}) if isinstance(item.get("share", {}), dict) else {}
        is_public = bool(share_state.get("is_public", False))
        if owner_id == user_id or is_public:
            visible.append(item)
    return _sort_projects(visible)


def _find_project_index(state: Dict[str, Any], project_id: str) -> int:
    target = sanitize_text_strict(project_id, allow_empty=True, max_len=24)
    for idx, item in enumerate(state.get("projects", [])):
        if sanitize_text_strict(item.get("id", ""), allow_empty=True, max_len=24) == target:
            return idx
    return -1


def _sanitize_request_id(value: Any) -> str:
    return sanitize_text_strict(value, allow_empty=True, max_len=64).strip().lower()


def _find_recent_idempotent_project(
    state: Dict[str, Any],
    *,
    user_id: str,
    action: str,
    request_id: str,
) -> Optional[Dict[str, Any]]:
    safe_action = sanitize_text_strict(action, allow_empty=True, max_len=16).lower()
    safe_request_id = _sanitize_request_id(request_id)
    safe_user_id = sanitize_text_strict(user_id, allow_empty=True, max_len=40)
    if not safe_action or not safe_request_id or not safe_user_id:
        return None

    for event in reversed(state.get("events", [])):
        if not isinstance(event, dict):
            continue
        event_type = sanitize_text_strict(event.get("event_type", ""), allow_empty=True, max_len=40).lower()
        if event_type not in {"project_created", "project_updated"}:
            continue
        if sanitize_text_strict(event.get("user_id", ""), allow_empty=True, max_len=40) != safe_user_id:
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
        if _sanitize_request_id(payload.get("request_id", "")) != safe_request_id:
            continue
        if sanitize_text_strict(payload.get("action", ""), allow_empty=True, max_len=16).lower() != safe_action:
            continue

        project_id = sanitize_text_strict(event.get("project_id", ""), allow_empty=True, max_len=24)
        idx = _find_project_index(state, project_id)
        if idx < 0:
            continue
        project = state["projects"][idx]
        if not isinstance(project, dict):
            continue
        return copy.deepcopy(project)
    return None


def _append_event(
    state: Dict[str, Any],
    event_type: str,
    source: str,
    project_id: str = "",
    payload: Optional[Dict[str, Any]] = None,
    user_id: str = "",
    ts: str = "",
) -> Optional[Dict[str, Any]]:
    safe_type = _sanitize_event_type(event_type)
    if not safe_type:
        return None
    safe_source = _sanitize_event_source(source)
    safe_project_id = sanitize_text_strict(project_id, allow_empty=True, max_len=24)
    safe_user_id = sanitize_text_strict(user_id, allow_empty=True, max_len=40)
    clean_event_id = sanitize_text_strict(hashlib.md5(f"{safe_type}{_now_ts()}".encode("utf-8")).hexdigest()[:12], allow_empty=False, max_len=20)
    event = {
        "id": clean_event_id,
        "ts": sanitize_text_strict(ts, allow_empty=True, max_len=24) or _now_ts(),
        "user_id": safe_user_id,
        "project_id": safe_project_id,
        "event_type": safe_type,
        "source": safe_source,
        "payload": _sanitize_event_value(payload or {}, depth=0),
    }
    events = [item for item in state.get("events", []) if isinstance(item, dict)]
    events.append(event)
    if len(events) > EVENT_MAX_COUNT:
        events = events[-EVENT_MAX_COUNT:]
    state["events"] = events
    return event


def _sanitize_cta_token(value: Any) -> str:
    return sanitize_text_strict(value, allow_empty=True, max_len=40).lower()


def _generate_cta_token(project_id: str, cta: str, source: str) -> str:
    seed = f"{project_id}:{cta}:{source}:{_now_ts()}:{uuid.uuid4().hex}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _is_cta_event_expired(cta_event_ts: str, now_ts: str) -> bool:
    event_dt = _parse_updated_at(cta_event_ts)
    now_dt = _parse_updated_at(now_ts)
    if event_dt == datetime.min or now_dt == datetime.min:
        return True
    age_days = max((now_dt.date() - event_dt.date()).days, 0)
    return age_days > get_settings().cta_token_ttl_days


def _find_cta_event_by_token(state: Dict[str, Any], cta_token: str) -> Optional[Dict[str, Any]]:
    token = _sanitize_cta_token(cta_token)
    if not token:
        return None

    events = [item for item in state.get("events", []) if isinstance(item, dict)]
    for event in reversed(events):
        if sanitize_text_strict(event.get("event_type", ""), allow_empty=True, max_len=40).lower() != "share_cta_clicked":
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
        current = _sanitize_cta_token(payload.get("cta_token", ""))
        if current == token:
            return event

    return get_store_repository().find_latest_event_by_payload(
        event_type="share_cta_clicked",
        payload_key="cta_token",
        payload_value=token,
    )


def _conversion_event_exists(
    state: Dict[str, Any],
    cta_token: str,
    conversion_kind: str,
    converted_project_id: str = "",
) -> bool:
    token = _sanitize_cta_token(cta_token)
    kind = sanitize_text_strict(conversion_kind, allow_empty=True, max_len=16).lower()
    target_project_id = sanitize_text_strict(converted_project_id, allow_empty=True, max_len=24)
    if not token or not kind:
        return False

    for event in state.get("events", []):
        if not isinstance(event, dict):
            continue
        if sanitize_text_strict(event.get("event_type", ""), allow_empty=True, max_len=40).lower() != "share_conversion_attributed":
            continue
        payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
        if _sanitize_cta_token(payload.get("cta_token", "")) != token:
            continue
        if sanitize_text_strict(payload.get("conversion_kind", ""), allow_empty=True, max_len=16).lower() != kind:
            continue
        if target_project_id and sanitize_text_strict(payload.get("converted_project_id", ""), allow_empty=True, max_len=24) != target_project_id:
            continue
        return True
    return False


def _attribute_conversion_from_cta(
    state: Dict[str, Any],
    cta_token: str,
    conversion_kind: str,
    converted_project_id: str,
    actor_user_id: str,
    source: str,
    timestamp: str,
) -> str:
    def _log_skipped(reason: str, source_project_id: str = "") -> None:
        _append_event(
            state=state,
            event_type="share_conversion_skipped",
            source=source,
            project_id=source_project_id,
            user_id=actor_user_id,
            ts=timestamp,
            payload={
                "cta_token": _sanitize_cta_token(cta_token),
                "conversion_kind": sanitize_text_strict(conversion_kind, allow_empty=True, max_len=16).lower(),
                "converted_project_id": sanitize_text_strict(converted_project_id, allow_empty=True, max_len=24),
                "reason": sanitize_text_strict(reason, allow_empty=True, max_len=24).lower(),
            },
        )

    token = _sanitize_cta_token(cta_token)
    kind = sanitize_text_strict(conversion_kind, allow_empty=True, max_len=16).lower()
    if kind not in {"create", "update"}:
        return ""
    if not token:
        return ""

    cta_event = _find_cta_event_by_token(state, token)
    if not isinstance(cta_event, dict):
        _log_skipped("token_not_found")
        return ""

    source_project_id = sanitize_text_strict(cta_event.get("project_id", ""), allow_empty=True, max_len=24)
    if _is_cta_event_expired(str(cta_event.get("ts", "")), timestamp):
        _log_skipped("token_expired", source_project_id=source_project_id)
        return ""
    if not source_project_id:
        _log_skipped("source_project_missing")
        return ""
    if _conversion_event_exists(state, token, kind):
        _log_skipped("replay_blocked", source_project_id=source_project_id)
        return source_project_id

    cta_payload = cta_event.get("payload", {}) if isinstance(cta_event.get("payload", {}), dict) else {}
    cta_source = sanitize_text_strict(cta_payload.get("source", ""), allow_empty=True, max_len=40) or sanitize_text_strict(
        cta_event.get("source", ""),
        allow_empty=True,
        max_len=40,
    )
    cta_ref = sanitize_text_strict(cta_payload.get("ref", ""), allow_empty=True, max_len=80).lower()
    _append_event(
        state=state,
        event_type="share_conversion_attributed",
        source=source,
        project_id=source_project_id,
        user_id=actor_user_id,
        ts=timestamp,
        payload={
            "cta_token": token,
            "conversion_kind": kind,
            "converted_project_id": sanitize_text_strict(converted_project_id, allow_empty=True, max_len=24),
            "cta": sanitize_text_strict(cta_payload.get("cta", ""), allow_empty=True, max_len=40),
            "cta_source": cta_source,
            "cta_ref": cta_ref,
        },
    )
    return source_project_id


def _build_quality_feedback(update_entry: Dict[str, Any], project: Dict[str, Any]) -> Dict[str, Any]:
    evidence = float(update_entry.get("evidence_score", 0) or 0)
    alignment = float(update_entry.get("action_alignment", 0) or 0)
    completed = bool(update_entry.get("completion_signal", False))
    progress_score = int((project.get("progress_eval", {}) or {}).get("score", 50) or 50)

    score = min(1.0, evidence * 0.5 + alignment * 0.35 + (0.15 if completed else 0.0))
    level = "low"
    if score >= 0.75:
        level = "high"
    elif score >= 0.5:
        level = "medium"

    reasons: List[str] = []
    if evidence < 0.45:
        reasons.append("证据偏弱：建议补充数据、客户反馈或里程碑结果。")
    else:
        reasons.append("证据有效：更新包含可验证的信息。")
    if alignment < 0.45:
        reasons.append("行动对齐偏弱：建议明确与当前 next_action 的对应关系。")
    else:
        reasons.append("行动对齐较好：与当前 next_action 方向一致。")
    if completed:
        reasons.append("检测到动作完成信号：可进入下一轮动作定义。")
    if progress_score < 45:
        reasons.append("当前项目进展分偏低：建议缩小目标并给出 24 小时内可执行动作。")

    if level == "high":
        suggested_next_input = "继续补充结果证据（数字或用户反馈）并说明下一步节奏。"
    elif level == "medium":
        suggested_next_input = "补充一个可量化结果，并说明该结果如何验证当前假设。"
    else:
        suggested_next_input = "请按“动作-结果-证据”格式更新：做了什么、产出什么、用什么数据证明。"

    return {
        "level": level,
        "score": round(score, 2),
        "reasons": reasons[:4],
        "suggested_next_input": suggested_next_input,
    }


def _build_evolution_explanation(previous_project: Dict[str, Any], current_project: Dict[str, Any], signals: Dict[str, Any]) -> Dict[str, Any]:
    prev_stage = normalize_stage_value(previous_project.get("stage", ""))
    curr_stage = normalize_stage_value(current_project.get("stage", ""))
    prev_progress = int((previous_project.get("progress_eval", {}) or {}).get("score", 50) or 50)
    curr_progress = int((current_project.get("progress_eval", {}) or {}).get("score", 50) or 50)
    progress_delta = curr_progress - prev_progress

    reason_codes: List[str] = []
    if prev_stage != curr_stage:
        reason_codes.append("stage_transition")
    if progress_delta > 0:
        reason_codes.append("progress_up")
    elif progress_delta < 0:
        reason_codes.append("progress_down")

    signal_hits = signals.get("hits", []) if isinstance(signals.get("hits", []), list) else []
    if signal_hits:
        reason_codes.append("rule_signal_detected")

    prev_intervention = (previous_project.get("intervention", {}) or {}).get("status", "")
    curr_intervention = (current_project.get("intervention", {}) or {}).get("status", "")
    if sanitize_text_strict(prev_intervention, allow_empty=True, max_len=20) != sanitize_text_strict(curr_intervention, allow_empty=True, max_len=20):
        reason_codes.append("intervention_state_changed")

    if not reason_codes:
        reason_codes.append("projection_refreshed")

    return {
        "stage_before": prev_stage,
        "stage_after": curr_stage,
        "stage_changed": prev_stage != curr_stage,
        "progress_before": prev_progress,
        "progress_after": curr_progress,
        "progress_delta": progress_delta,
        "reason_codes": reason_codes[:6],
    }


def _refresh_ops_signals(state: Dict[str, Any], project_ids: Optional[List[str]] = None) -> None:
    target_ids = set()
    if isinstance(project_ids, list) and project_ids:
        target_ids = {
            sanitize_text_strict(item, allow_empty=True, max_len=24)
            for item in project_ids
            if sanitize_text_strict(item, allow_empty=True, max_len=24)
        }

    now_ts = _now_ts()
    updated_projects: List[Dict[str, Any]] = []
    for project in state.get("projects", []):
        next_project = copy.deepcopy(project)
        pid = sanitize_text_strict(next_project.get("id", ""), allow_empty=True, max_len=24)
        if not target_ids or pid in target_ids:
            next_project["ops_signals"] = derive_ops_signals(pid, state.get("events", []), now_ts=now_ts)
        updated_projects.append(next_project)
    state["projects"] = updated_projects


def _emit_loop_transition_events(
    state: Dict[str, Any],
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
        _append_event(
            state=state,
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
        _append_event(
            state=state,
            event_type="intervention_resolved",
            source=source,
            project_id=project_id,
            ts=timestamp,
            payload={
                "effectiveness": current_project.get("last_intervention_effectiveness", "unknown"),
                "progress_score": (current_project.get("progress_eval", {}) or {}).get("score", 0),
            },
        )


def login(email: str) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)
    changed = _migrate_unowned_projects(state, user["id"])
    if changed:
        save_state(state)
    return {"user": user, "projects": _get_visible_projects(state, user["id"])}


def _merge_generate_input(raw_input: str, file_text: str) -> str:
    if file_text and raw_input:
        return f"{file_text}\n\n{raw_input}"
    if file_text:
        return file_text
    return raw_input


def _extract_output_language(payload: Dict[str, Any], default: str = "zh-CN") -> str:
    lang = sanitize_text_strict(payload.get("output_language", payload.get("outputLanguage", "")), allow_empty=True, max_len=24)
    if not lang:
        return default
    return lang


def _resolve_ai_path(meta: Dict[str, Any]) -> str:
    return "fallback" if bool((meta or {}).get("used_local_structuring", False)) else "remote"


def _map_generate_stage_to_project(value: str) -> str:
    safe = sanitize_text_strict(value, allow_empty=True, max_len=24).lower()
    if safe == "idea":
        return "IDEA"
    if safe == "launched":
        return "EARLY_REVENUE"
    return "BUILDING"


def _materialize_structured_project(
    *,
    state: Dict[str, Any],
    user: Optional[Dict[str, Any]],
    schema: Dict[str, Any],
    merged_input: str,
    has_file: bool,
    cta_token: str,
    source: str,
    request_id: str = "",
    entity_type: str = "claimed_project",
    visible_in_library: bool = True,
    ai_path: str = "unknown",
) -> Dict[str, Any]:
    project = enrich_generated_project(schema)
    project["desc"] = merged_input
    owner_user_id = sanitize_text_strict((user or {}).get("id", ""), allow_empty=True, max_len=40)
    safe_entity_type = "temporary_card" if sanitize_text_strict(entity_type, allow_empty=True, max_len=24).lower() == "temporary_card" else "claimed_project"
    project["owner_user_id"] = owner_user_id if safe_entity_type == "claimed_project" else ""
    project["claimed_by_user_id"] = owner_user_id if safe_entity_type == "claimed_project" else ""
    project["entity_type"] = safe_entity_type
    project["claim_status"] = "claimed" if safe_entity_type == "claimed_project" else "unclaimed"
    project["visible_in_library"] = bool(visible_in_library and safe_entity_type == "claimed_project")
    created_ts = _now_ts()
    project["share"] = {
        "is_public": True,
        "published_at": created_ts,
        "last_shared_at": created_ts,
    }
    project["updates"] = [
        build_update_entry(
            project_id=project.get("id", ""),
            author_user_id=owner_user_id,
            content=project.get("latest_update", project.get("version_footprint", "")),
            source=source,
            created_at=project.get("updated_at", get_now_str()),
            input_meta={"has_text": True, "has_file": has_file, "merged_chars": len(merged_input)},
            next_action_text=(project.get("next_action", {}) or {}).get("text", ""),
        )
    ]

    normalized = normalize_project(project)
    state["projects"].append(normalized)
    state["projects"] = _sort_projects(state["projects"])

    project_id = sanitize_text_strict(normalized.get("id", ""), allow_empty=True, max_len=24)
    if project_id:
        _append_event(
            state=state,
            event_type="project_created",
            source="card_generate_api" if safe_entity_type == "temporary_card" else "create_api",
            project_id=project_id,
            user_id=owner_user_id,
            payload={
                "action": "create",
                "request_id": _sanitize_request_id(request_id),
                "stage": normalized.get("stage", ""),
                "has_file": has_file,
                "merged_chars": len(merged_input),
                "entity_type": safe_entity_type,
                "ai_path": sanitize_text_strict(ai_path, allow_empty=True, max_len=16) or "unknown",
            },
        )
        source_project_id = _attribute_conversion_from_cta(
            state=state,
            cta_token=cta_token,
            conversion_kind="create",
            converted_project_id=project_id,
            actor_user_id=owner_user_id,
            source="share_cta_create",
            timestamp=_now_ts(),
        )
        refresh_ids = [project_id]
        if source_project_id:
            refresh_ids.append(source_project_id)
        _refresh_ops_signals(state, project_ids=refresh_ids)
    return normalized


def _build_project_schema_from_generated_object(
    generated: Dict[str, Any],
    *,
    merged_input: str,
    optional_title: str,
) -> Dict[str, Any]:
    generated_name = sanitize_text_strict(generated.get("name", ""), allow_empty=True, max_len=42)
    project_title = optional_title or generated_name or "未命名项目"
    project_title = sanitize_text_strict(project_title, allow_empty=True, max_len=42) or "未命名项目"

    one_liner = sanitize_text_strict(generated.get("one_liner", ""), allow_empty=True, max_len=140) or "项目摘要待补充"
    core_problem = sanitize_text_strict(generated.get("core_problem", ""), allow_empty=True, max_len=220) or "核心问题待补充"
    solution = sanitize_text_strict(generated.get("solution", ""), allow_empty=True, max_len=220) or "解决方案待补充"
    target_user = sanitize_text_strict(generated.get("target_user", ""), allow_empty=True, max_len=120) or "目标用户待补充"
    use_case = sanitize_text_strict(generated.get("use_case", ""), allow_empty=True, max_len=220) or "使用场景待补充"
    monetization = sanitize_text_strict(generated.get("monetization", ""), allow_empty=True, max_len=120) or "变现方式待补充"
    progress_note = sanitize_text_strict(generated.get("progress_note", ""), allow_empty=True, max_len=220) or "已完成首次结构化生成"
    key_metric = sanitize_text_strict(generated.get("key_metric", ""), allow_empty=True, max_len=120) or "关键指标待补充"
    stage = _map_generate_stage_to_project(sanitize_text_strict(generated.get("current_stage", ""), allow_empty=True, max_len=24))

    return sanitize_schema(
        {
            "title": project_title,
            "desc": merged_input,
            "users": target_user,
            "use_cases": use_case,
            "problem_statement": core_problem,
            "solution_approach": solution,
            "model": monetization,
            "model_desc": monetization,
            "business_model_type": normalize_business_model_type("", context=f"{target_user} {one_liner}"),
            "model_type": normalize_model_type("", model_desc=monetization),
            "pricing_strategy": "",
            "form_type": "OTHER",
            "stage": stage,
            "latest_update": progress_note,
            "version_footprint": progress_note,
            "summary": one_liner,
            "stage_metric": key_metric,
        }
    )


def _generate_structured_schema_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_input = sanitize_text_strict(payload.get("raw_input", ""), allow_empty=True, max_len=12000)
    file_text = sanitize_text_strict(payload.get("file_text", ""), allow_empty=True, max_len=12000)
    optional_title = sanitize_text_strict(payload.get("optional_title", ""), allow_empty=True, max_len=42)
    if not raw_input and not file_text:
        raise ServiceError(400, "invalid_input", "请先输入项目描述或添加材料。")

    output_language = _extract_output_language(payload, default="zh-CN")
    merged_input = _merge_generate_input(raw_input=raw_input, file_text=file_text)
    generated = structure_project_object(merged_input, optional_title=optional_title, output_language=output_language)
    meta = get_last_structuring_meta()
    schema = _build_project_schema_from_generated_object(generated, merged_input=merged_input, optional_title=optional_title)
    return {"schema": schema, "meta": meta, "merged_input": merged_input, "has_file": bool(file_text)}


def generate_card(payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    request_id = _sanitize_request_id(payload.get("request_id", payload.get("requestId", "")))
    generated_payload = _generate_structured_schema_from_payload(payload)
    schema = generated_payload["schema"]
    meta = generated_payload["meta"]
    merged_input = generated_payload["merged_input"]
    has_file = bool(generated_payload["has_file"])

    cta_token = _sanitize_cta_token(payload.get("cta_token", payload.get("ctaToken", "")))
    normalized = _materialize_structured_project(
        state=state,
        user=None,
        schema=schema,
        merged_input=merged_input,
        has_file=has_file,
        cta_token=cta_token,
        source="anonymous_generate",
        request_id=request_id,
        entity_type="temporary_card",
        visible_in_library=False,
        ai_path=_resolve_ai_path(meta),
    )
    _record_ai_fallback_event(
        state=state,
        user_id="",
        source="card_generate_structuring",
        project_id=sanitize_text_strict(normalized.get("id", ""), allow_empty=True, max_len=24),
        meta=meta,
    )
    save_state(state)
    return {
        "project": normalized,
        "used_fallback": bool(meta.get("used_local_structuring", False)),
        "warning": _build_structuring_warning(meta),
        "idempotent_replay": False,
    }


def create_project(payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, str(payload.get("email", "")))
    _migrate_unowned_projects(state, user["id"])
    request_id = _sanitize_request_id(payload.get("request_id", payload.get("requestId", "")))
    replayed = _find_recent_idempotent_project(
        state,
        user_id=str(user.get("id", "")),
        action="create",
        request_id=request_id,
    )
    if replayed is not None:
        return {
            "project": replayed,
            "used_fallback": False,
            "warning": "",
            "idempotent_replay": True,
        }

    title = sanitize_text_strict(payload.get("title", ""), allow_empty=True, max_len=42)
    if not title:
        raise ServiceError(400, "invalid_title", "请先填写主体名称。")
    if not validate_title_candidate(title):
        raise ServiceError(400, "invalid_title", "主体名称格式无效，请使用简短清晰的名称。")

    input_text = sanitize_text_strict(
        payload.get("input_text", payload.get("inputText", "")),
        allow_empty=True,
        max_len=12000,
    )
    supplemental_text = sanitize_text_strict(
        payload.get("supplemental_text", payload.get("supplementalText", "")),
        allow_empty=True,
        max_len=12000,
    )
    if not input_text:
        raise ServiceError(400, "invalid_input", "请先输入项目描述。")
    merged_input = input_text
    if supplemental_text:
        merged_input = f"{input_text}\n\n{supplemental_text}"

    schema = structure_project(merged_input, user_title=title)
    meta = get_last_structuring_meta()
    schema = sanitize_schema({**schema, "title": title})

    stage_override = sanitize_text_strict(payload.get("stage", ""), allow_empty=True, max_len=40)
    form_override = sanitize_text_strict(payload.get("form_type", payload.get("formType", "")), allow_empty=True, max_len=40)
    business_model_override = sanitize_text_strict(
        payload.get("business_model_type", payload.get("businessModelType", "")),
        allow_empty=True,
        max_len=40,
    )
    model_override = sanitize_text_strict(payload.get("model_type", payload.get("modelType", "")), allow_empty=True, max_len=40)

    if stage_override:
        schema["stage"] = normalize_stage_value(stage_override)
    if form_override:
        schema["form_type"] = normalize_form_type(form_override, context=input_text)
    if business_model_override:
        schema["business_model_type"] = normalize_business_model_type(
            business_model_override,
            context=f"{schema.get('users', '')} {schema.get('summary', '')}",
        )
    if model_override:
        schema["model_type"] = normalize_model_type(model_override, model_desc=schema.get("model_desc", schema.get("model", "")))

    cta_token = _sanitize_cta_token(payload.get("cta_token", payload.get("ctaToken", "")))
    normalized = _materialize_structured_project(
        state=state,
        user=user,
        schema=schema,
        merged_input=merged_input,
        has_file=bool(supplemental_text),
        cta_token=cta_token,
        source="create",
        request_id=request_id,
        ai_path=_resolve_ai_path(meta),
    )
    _record_ai_fallback_event(
        state=state,
        user_id=user["id"],
        source="create_structuring",
        project_id=sanitize_text_strict(normalized.get("id", ""), allow_empty=True, max_len=24),
        meta=meta,
    )

    save_state(state)
    return {
        "project": normalized,
        "used_fallback": bool(meta.get("used_local_structuring", False)),
        "warning": _build_structuring_warning(meta),
        "idempotent_replay": False,
    }


def generate_project(payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, str(payload.get("email", "")))
    _migrate_unowned_projects(state, user["id"])
    request_id = _sanitize_request_id(payload.get("request_id", payload.get("requestId", "")))
    replayed = _find_recent_idempotent_project(
        state,
        user_id=str(user.get("id", "")),
        action="create",
        request_id=request_id,
    )
    if replayed is not None:
        return {
            "project": replayed,
            "used_fallback": False,
            "warning": "",
            "idempotent_replay": True,
        }

    generated_payload = _generate_structured_schema_from_payload(payload)
    schema = generated_payload["schema"]
    meta = generated_payload["meta"]
    merged_input = generated_payload["merged_input"]
    has_file = bool(generated_payload["has_file"])

    cta_token = _sanitize_cta_token(payload.get("cta_token", payload.get("ctaToken", "")))
    normalized = _materialize_structured_project(
        state=state,
        user=user,
        schema=schema,
        merged_input=merged_input,
        has_file=has_file,
        cta_token=cta_token,
        source="create",
        request_id=request_id,
        ai_path=_resolve_ai_path(meta),
    )
    _record_ai_fallback_event(
        state=state,
        user_id=user["id"],
        source="generate_structuring",
        project_id=sanitize_text_strict(normalized.get("id", ""), allow_empty=True, max_len=24),
        meta=meta,
    )

    save_state(state)
    return {
        "project": normalized,
        "used_fallback": bool(meta.get("used_local_structuring", False)),
        "warning": _build_structuring_warning(meta),
        "idempotent_replay": False,
    }


def edit_project(project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, str(payload.get("email", "")))

    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")

    current = state["projects"][idx]
    owner_id = sanitize_text_strict(current.get("owner_user_id", ""), allow_empty=True, max_len=40)
    if owner_id != user["id"]:
        raise ServiceError(403, "forbidden", "无权限编辑该项目。")

    previous_project = copy.deepcopy(current)

    title = sanitize_text_strict(payload.get("title", current.get("title", "")), allow_empty=True, max_len=42)
    if not title or not validate_title_candidate(title):
        raise ServiceError(400, "invalid_title", "请输入有效项目名称。")

    latest_update = sanitize_text_strict(payload.get("latest_update", ""), allow_empty=True, max_len=280)
    if not latest_update:
        latest_update = sanitize_text_strict(current.get("latest_update", ""), allow_empty=True, max_len=280)

    timestamp = _now_ts()
    next_project = copy.deepcopy(current)
    next_project["title"] = title
    next_project["problem_statement"] = sanitize_text_strict(payload.get("problem_statement", current.get("problem_statement", "")), allow_empty=True, max_len=220)
    next_project["solution_approach"] = sanitize_text_strict(payload.get("solution_approach", current.get("solution_approach", "")), allow_empty=True, max_len=220)
    next_project["summary"] = sanitize_text_strict(payload.get("summary", current.get("summary", "")), allow_empty=True, max_len=140) or sanitize_text_strict(current.get("summary", ""), allow_empty=True, max_len=140)
    next_project["model_desc"] = sanitize_text_strict(payload.get("model_desc", current.get("model_desc", current.get("model", ""))), allow_empty=True, max_len=120) or sanitize_text_strict(current.get("model_desc", current.get("model", "")), allow_empty=True, max_len=120)
    next_project["model"] = next_project["model_desc"]
    next_project["users"] = sanitize_text_strict(payload.get("users", current.get("users", "")), allow_empty=True, max_len=120) or current.get("users", "")
    next_project["use_cases"] = sanitize_text_strict(payload.get("use_cases", current.get("use_cases", "")), allow_empty=True, max_len=220)
    next_project["latest_update"] = latest_update
    next_project["stage_metric"] = sanitize_text_strict(payload.get("stage_metric", current.get("stage_metric", "")), allow_empty=True, max_len=120)
    next_project["stage"] = normalize_stage_value(payload.get("stage", current.get("stage", "")))
    next_project["business_model_type"] = normalize_business_model_type(
        payload.get("business_model_type", current.get("business_model_type", "")),
        context=f"{next_project.get('users', '')} {next_project.get('summary', '')}",
    )
    next_project["model_type"] = normalize_model_type(payload.get("model_type", current.get("model_type", "")), model_desc=next_project.get("model_desc", current.get("model", "")))
    next_project["form_type"] = normalize_form_type(payload.get("form_type", current.get("form_type", "")), context=f"{title} {next_project.get('summary', '')} {next_project.get('model_desc', '')}")

    existing_next_action = current.get("next_action", {}) if isinstance(current.get("next_action", {}), dict) else {}
    has_next_action_text = "next_action_text" in payload
    has_next_action_status = "next_action_status" in payload
    next_action_text = sanitize_text_strict(
        payload.get("next_action_text", existing_next_action.get("text", "")),
        allow_empty=True,
        max_len=180,
    )
    next_action_status = sanitize_text_strict(
        payload.get("next_action_status", existing_next_action.get("status", "open")),
        allow_empty=True,
        max_len=24,
    ).lower() or "open"
    next_project["next_action"] = {
        "text": next_action_text,
        "status": next_action_status,
        "completed_at": sanitize_text_strict(existing_next_action.get("completed_at", ""), allow_empty=True, max_len=32),
        "generated_at": sanitize_text_strict(existing_next_action.get("generated_at", ""), allow_empty=True, max_len=32),
        "confidence": existing_next_action.get("confidence", 0.6),
    }

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
            author_user_id=user["id"],
            content=latest_update,
            source="direct_edit",
            created_at=timestamp,
            input_meta={"has_text": True, "has_file": False, "merged_chars": len(latest_update)},
            kind=update_kind,
            next_action_text=(next_project.get("next_action", {}) or {}).get("text", ""),
        )
        next_project["updates"] = [new_update] + [item for item in existing_updates if isinstance(item, dict)]

    next_project = evolve_action_loop(next_project, latest_update or next_project.get("latest_update", ""), timestamp)
    if has_next_action_text or has_next_action_status:
        evolved_next_action = next_project.get("next_action", {}) if isinstance(next_project.get("next_action", {}), dict) else {}
        if has_next_action_text:
            evolved_next_action["text"] = next_action_text
        if has_next_action_status:
            evolved_next_action["status"] = next_action_status
            if next_action_status != "completed":
                evolved_next_action["completed_at"] = ""
        next_project["next_action"] = evolved_next_action
    normalized = normalize_project(next_project)
    normalized["id"] = project_id
    normalized["updated_at"] = timestamp
    state["projects"][idx] = normalized

    _append_event(
        state=state,
        event_type="project_updated",
        source="direct_edit",
        project_id=project_id,
        user_id=user["id"],
        ts=timestamp,
        payload={
            "kind": "direct_edit",
            "completion_signal": bool((normalized.get("updates", []) or [{}])[0].get("completion_signal", False)),
        },
    )
    _emit_loop_transition_events(state, previous_project, normalized, project_id, "direct_edit", timestamp)
    _refresh_ops_signals(state, project_ids=[project_id])

    save_state(state)
    return {"project": normalized}


def update_project_progress(project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, str(payload.get("email", "")))

    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")

    project = state["projects"][idx]
    owner_id = sanitize_text_strict(project.get("owner_user_id", ""), allow_empty=True, max_len=40)
    if owner_id != user["id"]:
        raise ServiceError(403, "forbidden", "无权限更新该项目。")

    previous_project = copy.deepcopy(project)
    request_id = _sanitize_request_id(payload.get("request_id", payload.get("requestId", "")))
    replayed = _find_recent_idempotent_project(
        state,
        user_id=str(user.get("id", "")),
        action="update",
        request_id=request_id,
    )
    if replayed is not None:
        return {
            "project": replayed,
            "used_fallback": False,
            "warning": "",
            "quality_feedback": {},
            "evolution_explanation": {},
            "idempotent_replay": True,
        }

    cleaned_update = sanitize_text_strict(
        payload.get("update_text", payload.get("input_text", "")),
        allow_empty=False,
        max_len=280,
    )
    if not cleaned_update:
        raise ServiceError(400, "invalid_update", "请输入有效的更新内容。")

    cleaned_supplemental = sanitize_text_strict(payload.get("supplemental_text", ""), allow_empty=True, max_len=12000)
    cta_token = _sanitize_cta_token(payload.get("cta_token", payload.get("ctaToken", "")))
    merged_input = cleaned_update
    if cleaned_supplemental:
        merged_input = f"{cleaned_update}\n\n{cleaned_supplemental}"

    signals = parse_update_signals(cleaned_update, project)
    context_project = apply_rule_overrides(project, signals)
    schema = structure_project(build_update_input(context_project, merged_input))
    meta = get_last_structuring_meta()

    timestamp = _now_ts()
    next_project = copy.deepcopy(project)
    update_kind = infer_update_kind(cleaned_update)

    next_project["latest_update"] = cleaned_update
    next_project["version_footprint"] = cleaned_update
    next_project["updated_at"] = timestamp

    existing_updates = next_project.get("updates", [])
    if not isinstance(existing_updates, list):
        existing_updates = []
    new_update = build_update_entry(
        project_id=project_id,
        author_user_id=user["id"],
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

    stage_candidate = sanitize_text_strict(schema.get("stage", ""), allow_empty=True, max_len=36)
    if stage_candidate:
        next_project["stage"] = normalize_stage_value(stage_candidate)
    model_type_candidate = sanitize_text_strict(schema.get("model_type", ""), allow_empty=True, max_len=36)
    if model_type_candidate:
        next_project["model_type"] = normalize_model_type(model_type_candidate, model_desc=next_project.get("model_desc", next_project.get("model", "")))
    business_model_candidate = sanitize_text_strict(
        payload.get("business_model_type", payload.get("businessModelType", schema.get("business_model_type", ""))),
        allow_empty=True,
        max_len=36,
    )
    if business_model_candidate:
        next_project["business_model_type"] = normalize_business_model_type(
            business_model_candidate,
            context=f"{next_project.get('users', '')} {next_project.get('summary', '')}",
        )
    users_candidate = sanitize_text_strict(schema.get("users", ""), allow_empty=True, max_len=44)
    if users_candidate:
        next_project["users"] = users_candidate
    use_cases_candidate = sanitize_text_strict(schema.get("use_cases", ""), allow_empty=True, max_len=120)
    if use_cases_candidate:
        next_project["use_cases"] = use_cases_candidate

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
    state["projects"][idx] = normalized
    quality_feedback = _build_quality_feedback(new_update, normalized)

    _append_event(
        state=state,
        event_type="project_updated",
        source="overlay_update",
        project_id=project_id,
        user_id=user["id"],
        ts=timestamp,
        payload={
            "action": "update",
            "request_id": request_id,
            "kind": new_update.get("kind", ""),
            "evidence_score": new_update.get("evidence_score", 0),
            "action_alignment": new_update.get("action_alignment", 0),
            "completion_signal": bool(new_update.get("completion_signal", False)),
            "has_file": bool(cleaned_supplemental),
            "quality_level": quality_feedback.get("level", ""),
            "quality_score": quality_feedback.get("score", 0),
        },
    )
    if bool(new_update.get("completion_signal", False)):
        _append_event(
            state=state,
            event_type="next_action_completed",
            source="overlay_update",
            project_id=project_id,
            user_id=user["id"],
            ts=timestamp,
            payload={
                "update_id": sanitize_text_strict(new_update.get("id", ""), allow_empty=True, max_len=20),
                "kind": sanitize_text_strict(new_update.get("kind", ""), allow_empty=True, max_len=16),
            },
        )
    source_project_id = _attribute_conversion_from_cta(
        state=state,
        cta_token=cta_token,
        conversion_kind="update",
        converted_project_id=project_id,
        actor_user_id=user["id"],
        source="share_cta_update",
        timestamp=timestamp,
    )
    _emit_loop_transition_events(state, previous_project, normalized, project_id, "overlay_update", timestamp)
    _record_ai_fallback_event(
        state=state,
        user_id=user["id"],
        source="update_structuring",
        project_id=project_id,
        meta=meta,
        ts=timestamp,
    )
    refresh_ids = [project_id]
    if source_project_id:
        refresh_ids.append(source_project_id)
    _refresh_ops_signals(state, project_ids=refresh_ids)

    save_state(state)
    evolution_explanation = _build_evolution_explanation(previous_project, normalized, signals)
    return {
        "project": normalized,
        "used_fallback": bool(meta.get("used_local_structuring", False)),
        "warning": _build_structuring_warning(meta),
        "quality_feedback": quality_feedback,
        "evolution_explanation": evolution_explanation,
        "idempotent_replay": False,
    }


def _recompute_project_updates_projection(next_project: Dict[str, Any]) -> None:
    updates = next_project.get("updates", [])
    if not isinstance(updates, list):
        updates = []
    cleaned_updates = [item for item in updates if isinstance(item, dict)]
    next_project["updates"] = cleaned_updates
    if cleaned_updates:
        head_content = sanitize_text_strict(cleaned_updates[0].get("content", ""), allow_empty=True, max_len=280)
        if head_content:
            next_project["latest_update"] = head_content
            next_project["version_footprint"] = head_content
    else:
        next_project["latest_update"] = ""
        next_project["version_footprint"] = ""


def edit_project_progress_item(project_id: str, update_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, str(payload.get("email", "")))

    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")
    project = state["projects"][idx]
    owner_id = sanitize_text_strict(project.get("owner_user_id", ""), allow_empty=True, max_len=40)
    if owner_id != user["id"]:
        raise ServiceError(403, "forbidden", "无权限编辑该项目进展。")

    safe_update_id = sanitize_text_strict(update_id, allow_empty=True, max_len=24)
    if not safe_update_id:
        raise ServiceError(400, "invalid_update", "进展标识无效。")
    new_content = sanitize_text_strict(payload.get("content", ""), allow_empty=False, max_len=280)
    if not new_content:
        raise ServiceError(400, "invalid_update", "请输入有效的进展内容。")

    previous_project = copy.deepcopy(project)
    next_project = copy.deepcopy(project)
    updates = next_project.get("updates", [])
    if not isinstance(updates, list):
        updates = []

    found = False
    for item in updates:
        if not isinstance(item, dict):
            continue
        if sanitize_text_strict(item.get("id", ""), allow_empty=True, max_len=24) != safe_update_id:
            continue
        found = True
        item["content"] = new_content
        item["kind"] = infer_update_kind(new_content)
        item["edited_at"] = _now_ts()
        break
    if not found:
        raise ServiceError(404, "not_found", "目标进展不存在或已删除。")

    timestamp = _now_ts()
    next_project["updated_at"] = timestamp
    _recompute_project_updates_projection(next_project)
    next_project["stage"] = normalize_stage_value(next_project.get("stage", ""))
    next_project["status_tag"] = infer_status_tag(next_project["stage"])
    next_project["status_theme"] = get_status_theme(next_project["status_tag"])
    next_project = evolve_action_loop(next_project, next_project.get("latest_update", ""), timestamp)

    normalized = normalize_project(next_project)
    normalized["id"] = project_id
    normalized["updated_at"] = timestamp
    state["projects"][idx] = normalized

    _append_event(
        state=state,
        event_type="project_updated",
        source="progress_edit",
        project_id=project_id,
        user_id=user["id"],
        ts=timestamp,
        payload={
            "action": "update_item",
            "update_id": safe_update_id,
        },
    )
    _emit_loop_transition_events(state, previous_project, normalized, project_id, "progress_edit", timestamp)
    _refresh_ops_signals(state, project_ids=[project_id])
    save_state(state)
    return {"project": normalized}


def delete_project_progress_item(project_id: str, update_id: str, email: str) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)

    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")
    project = state["projects"][idx]
    owner_id = sanitize_text_strict(project.get("owner_user_id", ""), allow_empty=True, max_len=40)
    if owner_id != user["id"]:
        raise ServiceError(403, "forbidden", "无权限删除该项目进展。")

    safe_update_id = sanitize_text_strict(update_id, allow_empty=True, max_len=24)
    if not safe_update_id:
        raise ServiceError(400, "invalid_update", "进展标识无效。")

    previous_project = copy.deepcopy(project)
    next_project = copy.deepcopy(project)
    updates = next_project.get("updates", [])
    if not isinstance(updates, list):
        updates = []
    kept_updates = []
    removed = False
    for item in updates:
        if not isinstance(item, dict):
            continue
        if sanitize_text_strict(item.get("id", ""), allow_empty=True, max_len=24) == safe_update_id:
            removed = True
            continue
        kept_updates.append(item)
    if not removed:
        raise ServiceError(404, "not_found", "目标进展不存在或已删除。")

    next_project["updates"] = kept_updates
    timestamp = _now_ts()
    next_project["updated_at"] = timestamp
    _recompute_project_updates_projection(next_project)
    next_project["stage"] = normalize_stage_value(next_project.get("stage", ""))
    next_project["status_tag"] = infer_status_tag(next_project["stage"])
    next_project["status_theme"] = get_status_theme(next_project["status_tag"])
    next_project = evolve_action_loop(next_project, next_project.get("latest_update", ""), timestamp)

    normalized = normalize_project(next_project)
    normalized["id"] = project_id
    normalized["updated_at"] = timestamp
    state["projects"][idx] = normalized

    _append_event(
        state=state,
        event_type="project_updated",
        source="progress_delete",
        project_id=project_id,
        user_id=user["id"],
        ts=timestamp,
        payload={
            "action": "delete_item",
            "update_id": safe_update_id,
        },
    )
    _emit_loop_transition_events(state, previous_project, normalized, project_id, "progress_delete", timestamp)
    _refresh_ops_signals(state, project_ids=[project_id])
    save_state(state)
    return {"project": normalized}


def toggle_share(project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, str(payload.get("email", "")))

    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")

    project = state["projects"][idx]
    owner_id = sanitize_text_strict(project.get("owner_user_id", ""), allow_empty=True, max_len=40)
    if owner_id != user["id"]:
        raise ServiceError(403, "forbidden", "无权限修改该项目分享状态。")

    next_project = copy.deepcopy(project)
    share = normalize_share_state(next_project.get("share", {}), next_project.get("id", project_id))
    now = _now_ts()
    share["is_public"] = bool(payload.get("is_public", False))
    share_event_type = "share_unpublished"
    if share["is_public"]:
        if not share.get("published_at"):
            share["published_at"] = now
        share["last_shared_at"] = now
        share_event_type = "share_published"
    else:
        share["published_at"] = ""
        share["last_shared_at"] = ""
    next_project["share"] = share
    next_project["updated_at"] = now

    normalized = normalize_project(next_project)
    normalized["id"] = project_id
    state["projects"][idx] = normalized
    _append_event(
        state=state,
        event_type=share_event_type,
        source="share_api",
        project_id=project_id,
        user_id=user["id"],
        ts=now,
        payload={"is_public": bool(share["is_public"])},
    )
    _refresh_ops_signals(state, project_ids=[project_id])
    save_state(state)
    return {"project": normalized}


def delete_project(project_id: str, email: str) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)

    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")

    project = state["projects"][idx]
    owner_id = sanitize_text_strict(project.get("owner_user_id", ""), allow_empty=True, max_len=40)
    if owner_id != user["id"]:
        raise ServiceError(403, "forbidden", "无权限删除该项目。")

    state["projects"].pop(idx)
    save_state(state)
    return {"ok": True}


def get_share(project_id: str, email: str = "") -> Dict[str, Any]:
    state = load_state()
    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")

    project = state["projects"][idx]
    share_state = project.get("share", {}) if isinstance(project.get("share", {}), dict) else {}
    is_public = bool(share_state.get("is_public", False))

    owner_preview = False
    if email:
        user = _ensure_user(state, email)
        owner_preview = bool(project.get("owner_user_id") == user.get("id"))

    can_view = bool(is_public or owner_preview)
    _append_event(
        state=state,
        event_type="share_viewed" if can_view else "share_denied",
        source="share_api",
        project_id=project_id,
        payload={
            "owner_preview": owner_preview,
            "is_public": is_public,
        },
    )
    _refresh_ops_signals(state, project_ids=[project_id])
    save_state(state)

    if not can_view:
        return {
            "project": {
                "id": project_id,
                "title": "Private Project",
                "summary": "This project is private.",
                "share": {"is_public": False},
            },
            "access_granted": False,
            "owner_preview": owner_preview,
        }

    return {
        "project": project,
        "access_granted": True,
        "owner_preview": owner_preview,
    }


def get_card(project_id: str, email: str = "") -> Dict[str, Any]:
    return get_share(project_id, email=email)


def claim_card(project_id: str, email: str) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)

    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标卡片不存在。")

    current = state["projects"][idx]
    entity_type = sanitize_text_strict(current.get("entity_type", ""), allow_empty=True, max_len=24).lower()
    owner_id = sanitize_text_strict(current.get("owner_user_id", ""), allow_empty=True, max_len=40)

    if entity_type != "temporary_card":
        if owner_id and owner_id != user["id"]:
            raise ServiceError(403, "forbidden", "该项目已属于其他用户，无法认领。")
        return {"project": current}

    next_project = copy.deepcopy(current)
    next_project["owner_user_id"] = user["id"]
    next_project["claimed_by_user_id"] = user["id"]
    next_project["entity_type"] = "claimed_project"
    next_project["claim_status"] = "claimed"
    next_project["visible_in_library"] = True
    next_project["updated_at"] = _now_ts()

    normalized = normalize_project(next_project)
    state["projects"][idx] = normalized
    _append_event(
        state=state,
        event_type="project_updated",
        source="card_claim_api",
        project_id=project_id,
        user_id=user["id"],
        payload={"action": "claim", "entity_type": "claimed_project"},
    )
    _refresh_ops_signals(state, project_ids=[project_id])
    save_state(state)
    return {"project": normalized}


def track_share_cta(project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")

    project = state["projects"][idx]
    share_state = project.get("share", {}) if isinstance(project.get("share", {}), dict) else {}
    is_public = bool(share_state.get("is_public", False))

    owner_preview = False
    email = sanitize_text_strict(payload.get("email", ""), allow_empty=True, max_len=120)
    if email:
        user = _ensure_user(state, email)
        owner_preview = bool(project.get("owner_user_id") == user.get("id"))

    can_view = bool(is_public or owner_preview)
    cta = sanitize_text_strict(payload.get("cta", ""), allow_empty=True, max_len=40).lower() or "start_project"
    source = sanitize_text_strict(payload.get("source", ""), allow_empty=True, max_len=40).lower() or "share_page_cta"
    ref = sanitize_text_strict(payload.get("ref", ""), allow_empty=True, max_len=80).lower()
    issued_at = _now_ts()
    cta_token = _generate_cta_token(project_id=project_id, cta=cta, source=source)

    _append_event(
        state=state,
        event_type="share_cta_clicked",
        source=source,
        project_id=project_id,
        ts=issued_at,
        payload={
            "cta": cta,
            "cta_token": cta_token,
            "source": source,
            "ref": ref,
            "owner_preview": owner_preview,
            "is_public": is_public,
            "access_granted": can_view,
        },
    )
    _refresh_ops_signals(state, project_ids=[project_id])
    save_state(state)
    issued_dt = _parse_updated_at(issued_at)
    if issued_dt == datetime.min:
        expires_at = issued_at
    else:
        expires_at = (issued_dt + timedelta(days=get_settings().cta_token_ttl_days)).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "ok": True,
        "access_granted": can_view,
        "cta_token": cta_token,
        "expires_in_days": get_settings().cta_token_ttl_days,
        "expires_at": expires_at,
    }


def get_project_detail(project_id: str, email: str) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)
    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")
    project = state["projects"][idx]

    owner = project.get("owner_user_id") == user.get("id")
    is_public = bool((project.get("share", {}) or {}).get("is_public", False))
    if not owner and not is_public:
        raise ServiceError(403, "forbidden", "该项目未公开，你无权查看。")
    return {"project": project}


def _increase_counter(counter: Dict[str, int], key: str) -> None:
    if not key:
        return
    counter[key] = counter.get(key, 0) + 1


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _parse_iso_date_strict(value: str, field_name: str) -> datetime:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=16)
    if not raw:
        raise ServiceError(400, f"invalid_{field_name}", f"{field_name} 格式无效，请使用 YYYY-MM-DD。")
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise ServiceError(400, f"invalid_{field_name}", f"{field_name} 格式无效，请使用 YYYY-MM-DD。") from None


def _to_date_or_min(value: Any) -> datetime:
    dt = _parse_updated_at(value)
    if dt == datetime.min:
        return datetime.min
    return datetime(dt.year, dt.month, dt.day)


def _build_growth_metrics_from_events(events: List[Dict[str, Any]], window_days: int, now_ts: str) -> Dict[str, Any]:
    current_dt = _parse_updated_at(now_ts)
    if current_dt == datetime.min:
        current_dt = datetime.now()

    share_views = 0
    share_cta_clicks = 0
    share_create_conversions = 0
    share_update_conversions = 0
    share_published = 0
    share_followup_updates_7d = 0
    project_updates = 0
    high_quality_updates = 0
    quality_scores: List[float] = []

    source_counter: Dict[str, int] = {}
    cta_by_source: Dict[str, int] = {}
    cta_by_ref: Dict[str, int] = {}
    create_conversion_by_source: Dict[str, int] = {}
    create_conversion_by_ref: Dict[str, int] = {}
    update_conversion_by_source: Dict[str, int] = {}
    update_conversion_by_ref: Dict[str, int] = {}
    share_published_windows: List[Dict[str, Any]] = []
    project_updated_times: Dict[str, List[datetime]] = {}

    for event in events:
        if not isinstance(event, dict):
            continue
        event_dt = _parse_updated_at(event.get("ts", ""))
        if event_dt == datetime.min:
            continue
        age_days = max((current_dt.date() - event_dt.date()).days, 0)
        if age_days > window_days:
            continue

        event_type = sanitize_text_strict(event.get("event_type", ""), allow_empty=True, max_len=40).lower()
        event_project_id = sanitize_text_strict(event.get("project_id", ""), allow_empty=True, max_len=24)
        source = sanitize_text_strict(event.get("source", ""), allow_empty=True, max_len=40).lower() or "unknown"
        payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}

        if event_type == "share_published" and event_project_id:
            share_published += 1
            share_published_windows.append({"project_id": event_project_id, "published_at": event_dt})
        elif event_type == "project_updated" and event_project_id:
            project_updated_times.setdefault(event_project_id, []).append(event_dt)
            project_updates += 1
            quality_level = sanitize_text_strict(payload.get("quality_level", ""), allow_empty=True, max_len=16).lower()
            quality_score_raw = payload.get("quality_score")
            try:
                quality_score = max(0.0, min(float(quality_score_raw), 1.0))
                quality_scores.append(quality_score)
                if quality_score >= 0.75:
                    high_quality_updates += 1
            except Exception:
                if quality_level == "high":
                    high_quality_updates += 1

        if event_type == "share_viewed":
            share_views += 1
            _increase_counter(source_counter, source)
            continue

        if event_type == "share_cta_clicked":
            share_cta_clicks += 1
            cta_ref = sanitize_text_strict(payload.get("ref", ""), allow_empty=True, max_len=80).lower() or "unknown"
            _increase_counter(source_counter, source)
            _increase_counter(cta_by_source, source)
            _increase_counter(cta_by_ref, cta_ref)
            continue

        if event_type != "share_conversion_attributed":
            continue

        conversion_kind = sanitize_text_strict(payload.get("conversion_kind", ""), allow_empty=True, max_len=16).lower()
        cta_source = sanitize_text_strict(payload.get("cta_source", ""), allow_empty=True, max_len=40).lower() or source
        cta_ref = sanitize_text_strict(payload.get("cta_ref", ""), allow_empty=True, max_len=80).lower() or "unknown"
        if conversion_kind == "create":
            share_create_conversions += 1
            _increase_counter(create_conversion_by_source, cta_source)
            _increase_counter(create_conversion_by_ref, cta_ref)
        elif conversion_kind == "update":
            share_update_conversions += 1
            _increase_counter(update_conversion_by_source, cta_source)
            _increase_counter(update_conversion_by_ref, cta_ref)

    for window in share_published_windows:
        pid = sanitize_text_strict(window.get("project_id", ""), allow_empty=True, max_len=24)
        published_at = window.get("published_at")
        if not pid or not isinstance(published_at, datetime):
            continue
        followups = project_updated_times.get(pid, [])
        deadline = published_at + timedelta(days=7)
        if any(published_at <= updated_at <= deadline for updated_at in followups):
            share_followup_updates_7d += 1

    avg_update_quality_score = 0.0
    if quality_scores:
        avg_update_quality_score = round(sum(quality_scores) / len(quality_scores), 4)

    top_sources = sorted(source_counter.items(), key=lambda item: item[1], reverse=True)[:5]
    return {
        "totals": {
            "share_views": share_views,
            "share_cta_clicks": share_cta_clicks,
            "share_create_conversions": share_create_conversions,
            "share_update_conversions": share_update_conversions,
            "share_published": share_published,
            "share_followup_updates_7d": share_followup_updates_7d,
        },
        "rates": {
            "view_to_cta": _safe_rate(share_cta_clicks, share_views),
            "cta_to_create": _safe_rate(share_create_conversions, share_cta_clicks),
            "cta_to_update": _safe_rate(share_update_conversions, share_cta_clicks),
            "share_to_7d_update": _safe_rate(share_followup_updates_7d, share_published),
        },
        "quality": {
            "project_updates": project_updates,
            "avg_update_quality_score": avg_update_quality_score,
            "high_quality_updates": high_quality_updates,
            "high_quality_update_rate": _safe_rate(high_quality_updates, project_updates),
        },
        "breakdowns": {
            "cta_by_source": cta_by_source,
            "cta_by_ref": cta_by_ref,
            "create_conversion_by_source": create_conversion_by_source,
            "create_conversion_by_ref": create_conversion_by_ref,
            "update_conversion_by_source": update_conversion_by_source,
            "update_conversion_by_ref": update_conversion_by_ref,
        },
        "top_sources": [{"source": source, "count": count} for source, count in top_sources],
    }


def get_growth_metrics(email: str, days: int = 14) -> Dict[str, Any]:
    state = load_state()
    _ensure_user(state, email)

    settings = get_settings()
    window_days = max(1, min(int(days or settings.growth_window_default_days), settings.growth_window_max_days))
    metrics = _build_growth_metrics_from_events(
        events=[item for item in state.get("events", []) if isinstance(item, dict)],
        window_days=window_days,
        now_ts=_now_ts(),
    )
    return {"window_days": window_days, **metrics}


def get_project_growth_metrics(project_id: str, email: str, days: int = 14) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)
    idx = _find_project_index(state, project_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标项目不存在。")

    project = state["projects"][idx]
    owner_id = sanitize_text_strict(project.get("owner_user_id", ""), allow_empty=True, max_len=40)
    if owner_id != user.get("id", ""):
        raise ServiceError(403, "forbidden", "无权限查看该项目增长指标。")

    settings = get_settings()
    window_days = max(1, min(int(days or settings.growth_window_default_days), settings.growth_window_max_days))
    pid = sanitize_text_strict(project_id, allow_empty=True, max_len=24)
    project_events = [
        item
        for item in state.get("events", [])
        if isinstance(item, dict) and sanitize_text_strict(item.get("project_id", ""), allow_empty=True, max_len=24) == pid
    ]
    metrics = _build_growth_metrics_from_events(
        events=project_events,
        window_days=window_days,
        now_ts=_now_ts(),
    )
    return {"project_id": pid, "window_days": window_days, **metrics}


def get_portfolio(email: str) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)
    owner_id = sanitize_text_strict(user.get("id", ""), allow_empty=True, max_len=40)
    now_dt = _parse_updated_at(_now_ts())
    if now_dt == datetime.min:
        now_dt = datetime.now()

    owned_projects = [
        item
        for item in state.get("projects", [])
        if isinstance(item, dict)
        and sanitize_text_strict(item.get("owner_user_id", ""), allow_empty=True, max_len=40) == owner_id
    ]
    owned_projects = _sort_projects(owned_projects)

    stage_distribution: Dict[str, int] = {}
    total_projects = len(owned_projects)
    public_projects = 0
    stale_projects_7d = 0
    active_interventions = 0
    open_actions = 0
    quality_values: List[float] = []
    cards: List[Dict[str, Any]] = []

    for project in owned_projects:
        stage = normalize_stage_value(project.get("stage", ""))
        stage_distribution[stage] = stage_distribution.get(stage, 0) + 1
        is_public = bool((project.get("share", {}) or {}).get("is_public", False))
        if is_public:
            public_projects += 1

        updated_dt = _parse_updated_at(project.get("updated_at", ""))
        if updated_dt != datetime.min:
            if max((now_dt.date() - updated_dt.date()).days, 0) > 7:
                stale_projects_7d += 1

        intervention_status = sanitize_text_strict(
            ((project.get("intervention", {}) or {}).get("status", "")),
            allow_empty=True,
            max_len=20,
        ).lower()
        if intervention_status == "active":
            active_interventions += 1

        next_action_status = sanitize_text_strict(
            ((project.get("next_action", {}) or {}).get("status", "")),
            allow_empty=True,
            max_len=20,
        ).lower()
        if next_action_status in {"open", "stale"}:
            open_actions += 1

        quality = float(project.get("decision_quality_score", 0) or 0)
        quality = max(0.0, min(quality, 1.0))
        quality_values.append(quality)

        cards.append(
            {
                "id": sanitize_text_strict(project.get("id", ""), allow_empty=True, max_len=24),
                "title": sanitize_text_strict(project.get("title", ""), allow_empty=True, max_len=80),
                "stage": stage,
                "updated_at": sanitize_text_strict(project.get("updated_at", ""), allow_empty=True, max_len=24),
                "is_public": is_public,
                "progress": {
                    "status": sanitize_text_strict(
                        ((project.get("progress_eval", {}) or {}).get("status", "")),
                        allow_empty=True,
                        max_len=20,
                    ),
                    "score": int(((project.get("progress_eval", {}) or {}).get("score", 50) or 50)),
                },
                "intervention_status": intervention_status or "idle",
                "next_action_status": next_action_status or "open",
                "next_action_text": sanitize_text_strict(
                    ((project.get("next_action", {}) or {}).get("text", "")),
                    allow_empty=True,
                    max_len=140,
                ),
                "decision_quality_score": round(quality, 4),
            }
        )

    avg_quality = round(sum(quality_values) / len(quality_values), 4) if quality_values else 0.0
    _append_event(
        state=state,
        event_type="portfolio_viewed",
        source="portfolio_api",
        user_id=owner_id,
        payload={"total_projects": total_projects},
    )
    save_state(state)
    return {
        "user": user,
        "summary": {
            "total_projects": total_projects,
            "public_projects": public_projects,
            "stale_projects_7d": stale_projects_7d,
            "active_interventions": active_interventions,
            "open_actions": open_actions,
            "avg_decision_quality_score": avg_quality,
        },
        "stage_distribution": stage_distribution,
        "projects": cards,
    }


def generate_weekly_report(email: str, week_start: str = "") -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)
    owner_id = sanitize_text_strict(user.get("id", ""), allow_empty=True, max_len=40)

    if week_start:
        start_dt = _parse_iso_date_strict(week_start, "week_start")
    else:
        now_dt = _parse_updated_at(_now_ts())
        if now_dt == datetime.min:
            now_dt = datetime.now()
        start_dt = now_dt - timedelta(days=now_dt.weekday())
        start_dt = datetime(start_dt.year, start_dt.month, start_dt.day)
    end_dt = start_dt + timedelta(days=6)

    owned_projects = [
        item
        for item in state.get("projects", [])
        if isinstance(item, dict)
        and sanitize_text_strict(item.get("owner_user_id", ""), allow_empty=True, max_len=40) == owner_id
    ]

    updates_count = 0
    wins: List[str] = []
    risks: List[str] = []
    next_focus: List[str] = []
    touched_project_ids: set[str] = set()

    for project in owned_projects:
        project_id = sanitize_text_strict(project.get("id", ""), allow_empty=True, max_len=24)
        updates = project.get("updates", [])
        if not isinstance(updates, list):
            continue
        for update in updates:
            if not isinstance(update, dict):
                continue
            created_dt = _to_date_or_min(update.get("created_at", ""))
            if created_dt == datetime.min:
                continue
            if created_dt < start_dt or created_dt > end_dt:
                continue
            updates_count += 1
            touched_project_ids.add(project_id)
            content = sanitize_text_strict(update.get("content", ""), allow_empty=True, max_len=180)
            kind = sanitize_text_strict(update.get("kind", ""), allow_empty=True, max_len=16).lower()
            completion_signal = bool(update.get("completion_signal", False))
            evidence = float(update.get("evidence_score", 0) or 0)
            if kind == "result" or completion_signal:
                wins.append(content)
            if kind == "hypothesis" or evidence < 0.45:
                risks.append(content)

        next_action_text = sanitize_text_strict(((project.get("next_action", {}) or {}).get("text", "")), allow_empty=True, max_len=140)
        if next_action_text:
            next_focus.append(f"{sanitize_text_strict(project.get('title', ''), allow_empty=True, max_len=80)}: {next_action_text}")

    wins = wins[:5]
    risks = risks[:5]
    next_focus = next_focus[:5]
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    report_markdown_lines = [
        "# Weekly Report",
        "",
        f"- Window: {start_str} to {end_str}",
        f"- Projects covered: {len(touched_project_ids)}",
        f"- Updates count: {updates_count}",
        "",
        "## Wins",
    ]
    report_markdown_lines.extend([f"- {item}" for item in wins] or ["- 本周暂无明确成果，建议聚焦一个可验证里程碑。"])
    report_markdown_lines.append("")
    report_markdown_lines.append("## Risks")
    report_markdown_lines.extend([f"- {item}" for item in risks] or ["- 未识别到高风险更新。"])
    report_markdown_lines.append("")
    report_markdown_lines.append("## Next Focus")
    report_markdown_lines.extend([f"- {item}" for item in next_focus] or ["- 暂无 next_action，建议先补齐下一步动作。"])
    report_markdown = "\n".join(report_markdown_lines)

    _append_event(
        state=state,
        event_type="weekly_report_generated",
        source="weekly_report_api",
        user_id=owner_id,
        payload={
            "week_start": start_str,
            "week_end": end_str,
            "projects_covered": len(touched_project_ids),
            "updates_count": updates_count,
        },
    )
    save_state(state)
    return {
        "window": {"start": start_str, "end": end_str},
        "summary": {
            "projects_covered": len(touched_project_ids),
            "updates_count": updates_count,
        },
        "sections": {
            "wins": wins,
            "risks": risks,
            "next_focus": next_focus,
        },
        "report_markdown": report_markdown,
    }


def get_intervention_learning(email: str, days: int = 30) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)
    owner_id = sanitize_text_strict(user.get("id", ""), allow_empty=True, max_len=40)
    settings = get_settings()
    window_days = max(
        1,
        min(int(days or settings.intervention_window_default_days), settings.intervention_window_max_days),
    )

    owner_project_ids = {
        sanitize_text_strict(item.get("id", ""), allow_empty=True, max_len=24)
        for item in state.get("projects", [])
        if isinstance(item, dict) and sanitize_text_strict(item.get("owner_user_id", ""), allow_empty=True, max_len=40) == owner_id
    }
    now_dt = _parse_updated_at(_now_ts())
    if now_dt == datetime.min:
        now_dt = datetime.now()

    triggered = 0
    resolved = 0
    by_type: Dict[str, Dict[str, int]] = {}
    improved_by_type: Dict[str, int] = {}

    for event in state.get("events", []):
        if not isinstance(event, dict):
            continue
        pid = sanitize_text_strict(event.get("project_id", ""), allow_empty=True, max_len=24)
        if pid not in owner_project_ids:
            continue
        event_dt = _parse_updated_at(event.get("ts", ""))
        if event_dt == datetime.min:
            continue
        age_days = max((now_dt.date() - event_dt.date()).days, 0)
        if age_days > window_days:
            continue

        event_type = sanitize_text_strict(event.get("event_type", ""), allow_empty=True, max_len=40).lower()
        payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
        itv_type = sanitize_text_strict(payload.get("type", ""), allow_empty=True, max_len=24).lower() or "unknown"
        by_type.setdefault(itv_type, {"triggered": 0, "resolved": 0})
        if event_type == "intervention_triggered":
            triggered += 1
            by_type[itv_type]["triggered"] += 1
        elif event_type == "intervention_resolved":
            resolved += 1
            by_type[itv_type]["resolved"] += 1
            effectiveness = sanitize_text_strict(payload.get("effectiveness", ""), allow_empty=True, max_len=20).lower()
            if effectiveness == "improved":
                improved_by_type[itv_type] = improved_by_type.get(itv_type, 0) + 1

    effectiveness_rows: List[Dict[str, Any]] = []
    best_type = "none"
    best_score = -1.0
    for itv_type, stats in by_type.items():
        trig = stats.get("triggered", 0)
        res = stats.get("resolved", 0)
        improved = improved_by_type.get(itv_type, 0)
        resolve_rate = _safe_rate(res, trig)
        improved_rate = _safe_rate(improved, res)
        score = improved_rate * max(res, 1)
        effectiveness_rows.append(
            {
                "type": itv_type,
                "triggered": trig,
                "resolved": res,
                "improved": improved,
                "resolve_rate": resolve_rate,
                "improved_rate": improved_rate,
            }
        )
        if score > best_score:
            best_score = score
            best_type = itv_type

    effectiveness_rows = sorted(effectiveness_rows, key=lambda item: (item["improved_rate"], item["resolved"]), reverse=True)
    if best_type == "none" or not effectiveness_rows:
        recommendation = "当前样本不足，建议先保持默认干预策略并扩大样本。"
    else:
        recommendation = f"优先采用 {best_type} 策略；其改进率更高，建议继续 A/B 验证文案与触发阈值。"

    _append_event(
        state=state,
        event_type="intervention_learning_viewed",
        source="intervention_learning_api",
        user_id=owner_id,
        payload={"window_days": window_days, "triggered": triggered},
    )
    save_state(state)
    return {
        "window_days": window_days,
        "totals": {"triggered": triggered, "resolved": resolved},
        "effectiveness": effectiveness_rows,
        "strategy": {
            "best_type": best_type,
            "recommendation": recommendation,
        },
    }


def get_growth_projects_dashboard(email: str, days: int = 14, limit: int = 10) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)

    owner_id = sanitize_text_strict(user.get("id", ""), allow_empty=True, max_len=40)
    settings = get_settings()
    window_days = max(1, min(int(days or settings.growth_window_default_days), settings.growth_window_max_days))
    safe_limit = max(1, min(int(limit or 10), 50))
    now_ts = _now_ts()

    project_cards: List[Dict[str, Any]] = []
    for project in state.get("projects", []):
        if not isinstance(project, dict):
            continue
        if sanitize_text_strict(project.get("owner_user_id", ""), allow_empty=True, max_len=40) != owner_id:
            continue
        pid = sanitize_text_strict(project.get("id", ""), allow_empty=True, max_len=24)
        if not pid:
            continue

        project_events = [
            item
            for item in state.get("events", [])
            if isinstance(item, dict) and sanitize_text_strict(item.get("project_id", ""), allow_empty=True, max_len=24) == pid
        ]
        metrics = _build_growth_metrics_from_events(
            events=project_events,
            window_days=window_days,
            now_ts=now_ts,
        )
        project_cards.append(
            {
                "project_id": pid,
                "title": sanitize_text_strict(project.get("title", ""), allow_empty=True, max_len=80),
                "stage": normalize_stage_value(project.get("stage", "")),
                **metrics,
            }
        )

    project_cards = sorted(
        project_cards,
        key=lambda item: (
            int((item.get("totals", {}) or {}).get("share_cta_clicks", 0)),
            int((item.get("totals", {}) or {}).get("share_views", 0)),
            int((item.get("totals", {}) or {}).get("share_create_conversions", 0)),
        ),
        reverse=True,
    )
    return {
        "window_days": window_days,
        "projects": project_cards[:safe_limit],
    }


def get_visible_projects(email: str) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)
    changed = _migrate_unowned_projects(state, user["id"])
    if changed:
        save_state(state)
    return {"user": user, "projects": _get_visible_projects(state, user["id"])}


def export_user_backup(email: str) -> Dict[str, Any]:
    state = load_state()
    user = _ensure_user(state, email)
    owner_id = sanitize_text_strict(user.get("id", ""), allow_empty=True, max_len=40)

    owned_projects: List[Dict[str, Any]] = []
    owned_ids: set[str] = set()
    for item in state.get("projects", []):
        if not isinstance(item, dict):
            continue
        if sanitize_text_strict(item.get("owner_user_id", ""), allow_empty=True, max_len=40) != owner_id:
            continue
        pid = sanitize_text_strict(item.get("id", ""), allow_empty=True, max_len=24)
        if not pid:
            continue
        owned_ids.add(pid)
        owned_projects.append(item)

    owned_events = [
        item
        for item in state.get("events", [])
        if isinstance(item, dict) and sanitize_text_strict(item.get("project_id", ""), allow_empty=True, max_len=24) in owned_ids
    ]

    return {
        "exported_at": _now_ts(),
        "user": {"id": owner_id, "email": sanitize_text_strict(user.get("email", ""), allow_empty=True, max_len=120)},
        "projects": owned_projects,
        "events": owned_events,
    }


def require_ops_admin(user: Dict[str, Any]) -> None:
    if not get_settings().ops_enabled:
        raise ServiceError(404, "ops_disabled", "Ops 工作台未启用。")
    if get_settings().local_mode:
        return
    email = normalize_email(str(user.get("email", "")))
    admins = {
        normalize_email(item)
        for item in str(get_settings().ops_admin_emails or "").replace("；", ",").replace(";", ",").split(",")
        if normalize_email(item)
    }
    if not email or email not in admins:
        raise ServiceError(403, "forbidden", "无权限访问 Ops 工作台。")


def _ops_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _ops_text(value: Any, max_len: int = 240) -> str:
    return sanitize_text_strict(value, allow_empty=True, max_len=max_len).strip()


def _ops_list(value: Any, max_items: int = 12, max_len: int = 40) -> List[str]:
    raw_items = value if isinstance(value, list) else []
    out: List[str] = []
    for item in raw_items:
        safe = _ops_text(item, max_len=max_len)
        if safe and safe not in out:
            out.append(safe)
        if len(out) >= max_items:
            break
    return out


def _ops_bool(payload: Dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    return bool(value)


def _ops_subject_type(value: Any) -> str:
    safe = _ops_text(value, max_len=16).lower()
    if safe not in OPS_SUBJECT_TYPES:
        raise ServiceError(400, "invalid_subject", "Ops 对象类型无效。")
    return safe


def _ops_find_index(items: List[Dict[str, Any]], item_id: str) -> int:
    target = _ops_text(item_id, max_len=64)
    for idx, item in enumerate(items):
        if _ops_text(item.get("id", ""), max_len=64) == target:
            return idx
    return -1


def _ops_append_event(state: Dict[str, Any], event_type: str, user: Dict[str, Any], payload: Dict[str, Any]) -> None:
    events = [item for item in state.get("ops_events", []) if isinstance(item, dict)]
    events.append(
        {
            "id": _ops_id("oev"),
            "ts": _now_ts(),
            "user_id": _ops_text(user.get("id", ""), max_len=40),
            "event_type": _ops_text(event_type, max_len=60),
            "payload": _sanitize_event_value(payload, depth=0),
        }
    )
    state["ops_events"] = events[-EVENT_MAX_COUNT:]


def _normalize_ops_lead(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    lead = {
        "id": _ops_text(current.get("id", ""), max_len=24) or _ops_id("lead"),
        "display_name": _ops_text(payload.get("display_name", current.get("display_name", "")), max_len=80),
        "source_channel": _ops_text(payload.get("source_channel", current.get("source_channel", "")), max_len=40),
        "source_handle": _ops_text(payload.get("source_handle", current.get("source_handle", "")), max_len=80),
        "wechat_status": _ops_text(payload.get("wechat_status", current.get("wechat_status", "")), max_len=40),
        "city": _ops_text(payload.get("city", current.get("city", "")), max_len=40),
        "direction": _ops_text(payload.get("direction", current.get("direction", "")), max_len=120),
        "one_liner": _ops_text(payload.get("one_liner", current.get("one_liner", "")), max_len=240),
        "stage": _ops_text(payload.get("stage", current.get("stage", "")), max_len=40),
        "project_id": _ops_text(payload.get("project_id", current.get("project_id", "")), max_len=24),
        "private_notes": _ops_text(payload.get("private_notes", current.get("private_notes", "")), max_len=1200),
        "followup_status": _ops_text(payload.get("followup_status", current.get("followup_status", "new")), max_len=40) or "new",
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not lead["display_name"] and not lead["one_liner"] and not lead["direction"]:
        raise ServiceError(400, "invalid_lead", "请至少填写姓名、方向或一句话介绍。")
    return lead


def _empty_ops_profile(subject_type: str, subject_id: str) -> Dict[str, Any]:
    profile = {
        "id": f"{subject_type}_{subject_id}",
        "subject_type": subject_type,
        "subject_id": subject_id,
        "core_need": "",
        "need_tags": [],
        "target_people": "",
        "offers": "",
        "offer_tags": [],
        "cooperation_preferences": [],
        "tech_need_type": "unknown",
        "tech_offer_type": "unknown",
        "filming_boundary": "",
        "internal_score": 0,
        "next_action": "",
        "private_notes": "",
        "created_at": _now_ts(),
        "updated_at": _now_ts(),
    }
    for key in OPS_PROFILE_BOOL_FIELDS:
        profile[key] = False
    return profile


def _normalize_ops_profile(subject_type: str, subject_id: str, payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or _empty_ops_profile(subject_type, subject_id))
    profile = _empty_ops_profile(subject_type, subject_id)
    profile["created_at"] = _ops_text(current.get("created_at", ""), max_len=24) or profile["created_at"]
    for key, max_len in [
        ("core_need", 500),
        ("target_people", 500),
        ("offers", 500),
        ("filming_boundary", 500),
        ("next_action", 500),
        ("private_notes", 1200),
    ]:
        profile[key] = _ops_text(payload.get(key, current.get(key, "")), max_len=max_len)
    profile["need_tags"] = _ops_list(payload.get("need_tags", current.get("need_tags", [])))
    profile["offer_tags"] = _ops_list(payload.get("offer_tags", current.get("offer_tags", [])))
    profile["cooperation_preferences"] = _ops_list(payload.get("cooperation_preferences", current.get("cooperation_preferences", [])))
    for key in OPS_PROFILE_BOOL_FIELDS:
        profile[key] = _ops_bool(payload, key, bool(current.get(key, False)))
    tech_need = _ops_text(payload.get("tech_need_type", current.get("tech_need_type", "unknown")), max_len=24).lower() or "unknown"
    tech_offer = _ops_text(payload.get("tech_offer_type", current.get("tech_offer_type", "unknown")), max_len=24).lower() or "unknown"
    profile["tech_need_type"] = tech_need if tech_need in TECH_NEED_TYPES else "unknown"
    profile["tech_offer_type"] = tech_offer if tech_offer in TECH_OFFER_TYPES else "unknown"
    try:
        score = int(payload.get("internal_score", current.get("internal_score", 0)) or 0)
    except Exception:
        score = 0
    profile["internal_score"] = max(0, min(score, 100))
    profile["updated_at"] = _now_ts()
    return profile


def _find_ops_profile_index(state: Dict[str, Any], subject_type: str, subject_id: str) -> int:
    for idx, item in enumerate(state.get("ops_profiles", [])):
        if _ops_text(item.get("subject_type", ""), max_len=16) == subject_type and _ops_text(item.get("subject_id", ""), max_len=24) == subject_id:
            return idx
    return -1


def _get_ops_profile_from_state(state: Dict[str, Any], subject_type: str, subject_id: str) -> Dict[str, Any]:
    idx = _find_ops_profile_index(state, subject_type, subject_id)
    if idx < 0:
        return _empty_ops_profile(subject_type, subject_id)
    return _normalize_ops_profile(subject_type, subject_id, {}, state["ops_profiles"][idx])


def get_ops_summary(user: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    leads = [item for item in state.get("ops_leads", []) if isinstance(item, dict)]
    memberships = [item for item in state.get("ops_activity_memberships", []) if isinstance(item, dict)]
    routing = [item for item in state.get("ops_routing_records", []) if isinstance(item, dict)]
    summary = {
        "lead_count": len(leads),
        "converted_project_count": len([item for item in leads if _ops_text(item.get("project_id", ""), max_len=24)]),
        "pending_followup_count": len([item for item in leads if _ops_text(item.get("followup_status", ""), max_len=40) not in {"done", "closed", "放弃", "已完成"}]),
        "activity_candidate_count": len([item for item in memberships if _ops_text(item.get("status", ""), max_len=40) in {"candidate", "候选", "已邀请", "已确认"}]),
        "pending_routing_count": len([item for item in routing if _ops_text(item.get("status", ""), max_len=40) in OPS_PENDING_ROUTING_STATUSES]),
    }
    return {"summary": summary}


def list_ops_leads(user: Dict[str, Any], filters: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    q = _ops_text(filters.get("q", ""), max_len=80).lower()
    city = _ops_text(filters.get("city", ""), max_len=40)
    source_channel = _ops_text(filters.get("source_channel", ""), max_len=40)
    need_tag = _ops_text(filters.get("need_tag", ""), max_len=40)
    offer_tag = _ops_text(filters.get("offer_tag", ""), max_len=40)
    followup_status = _ops_text(filters.get("followup_status", ""), max_len=40)
    leads: List[Dict[str, Any]] = []
    for raw in state.get("ops_leads", []):
        lead = _normalize_ops_lead({}, raw)
        profile = _get_ops_profile_from_state(state, "lead", lead["id"])
        haystack = f"{lead['display_name']} {lead['source_channel']} {lead['source_handle']} {lead['city']} {lead['direction']} {lead['one_liner']} {profile['core_need']} {profile['offers']}".lower()
        if q and q not in haystack:
            continue
        if city and lead["city"] != city:
            continue
        if source_channel and lead["source_channel"] != source_channel:
            continue
        if followup_status and lead["followup_status"] != followup_status:
            continue
        if need_tag and need_tag not in profile.get("need_tags", []):
            continue
        if offer_tag and offer_tag not in profile.get("offer_tags", []):
            continue
        leads.append({**lead, "ops_profile": profile})
    return {"leads": sorted(leads, key=lambda item: item.get("updated_at", ""), reverse=True)}


def create_ops_lead(user: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    lead = _normalize_ops_lead(payload)
    state.setdefault("ops_leads", []).append(lead)
    _ops_append_event(state, "lead_created", user, {"lead_id": lead["id"]})
    save_state(state)
    return {"lead": lead}


def update_ops_lead(user: Dict[str, Any], lead_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    leads = [item for item in state.get("ops_leads", []) if isinstance(item, dict)]
    idx = _ops_find_index(leads, lead_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标 lead 不存在。")
    lead = _normalize_ops_lead(payload, leads[idx])
    leads[idx] = lead
    state["ops_leads"] = leads
    _ops_append_event(state, "lead_updated", user, {"lead_id": lead["id"]})
    save_state(state)
    return {"lead": lead}


def get_ops_profile(user: Dict[str, Any], subject_type: str, subject_id: str) -> Dict[str, Any]:
    require_ops_admin(user)
    safe_type = _ops_subject_type(subject_type)
    safe_id = _ops_text(subject_id, max_len=24)
    return {"profile": _get_ops_profile_from_state(load_state(), safe_type, safe_id)}


def update_ops_profile(user: Dict[str, Any], subject_type: str, subject_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    safe_type = _ops_subject_type(subject_type)
    safe_id = _ops_text(subject_id, max_len=24)
    if not safe_id:
        raise ServiceError(400, "invalid_subject", "Ops 对象 ID 无效。")
    state = load_state()
    idx = _find_ops_profile_index(state, safe_type, safe_id)
    existing = state["ops_profiles"][idx] if idx >= 0 else None
    profile = _normalize_ops_profile(safe_type, safe_id, payload, existing)
    profiles = [item for item in state.get("ops_profiles", []) if isinstance(item, dict)]
    if idx >= 0:
        profiles[idx] = profile
    else:
        profiles.append(profile)
    state["ops_profiles"] = profiles
    _ops_append_event(state, "profile_updated", user, {"subject_type": safe_type, "subject_id": safe_id})
    save_state(state)
    return {"profile": profile}


def suggest_ops_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    text = " ".join(
        [
            _ops_text(payload.get("core_need", ""), 800),
            _ops_text(payload.get("target_people", ""), 800),
            _ops_text(payload.get("offers", ""), 800),
            _ops_text(payload.get("direction", ""), 300),
        ]
    )
    need_tags: List[str] = []
    offer_tags: List[str] = []
    rules = [
        ("技术合伙人", ["技术合伙人", "CTO", "开发", "工程师"], need_tags),
        ("技术外包", ["外包", "兼职", "顾问"], need_tags),
        ("投资", ["投资", "融资", "资金"], need_tags),
        ("客户", ["客户", "订单", "销售", "企业客户"], need_tags),
        ("内容增长", ["内容", "IP", "短视频", "漫剧", "增长"], need_tags),
        ("私域转化", ["私域", "社群", "转化"], need_tags),
        ("产业场景", ["产业", "场景", "传统业务"], need_tags),
        ("学校资源", ["学校", "高校", "产教融合", "教育"], offer_tags),
        ("园区资源", ["园区"], offer_tags),
        ("医疗资源", ["医疗", "医院"], offer_tags),
        ("技术能力", ["技术", "开发", "CTO", "工程师"], offer_tags),
        ("内容增长", ["内容", "IP", "短视频", "漫剧", "增长"], offer_tags),
    ]
    for label, keywords, bucket in rules:
        if any(keyword.lower() in text.lower() for keyword in keywords) and label not in bucket:
            bucket.append(label)
    tech_need_type = "cofounder" if "技术合伙人" in need_tags else "outsourcing" if "技术外包" in need_tags else "unknown"
    return {"need_tags": need_tags, "offer_tags": offer_tags, "tech_need_type": tech_need_type, "tech_offer_type": "unknown"}


def convert_ops_lead_to_project(user: Dict[str, Any], lead_id: str) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    leads = [item for item in state.get("ops_leads", []) if isinstance(item, dict)]
    idx = _ops_find_index(leads, lead_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标 lead 不存在。")
    lead = _normalize_ops_lead({}, leads[idx])
    if lead.get("project_id"):
        project_idx = _find_project_index(state, lead["project_id"])
        if project_idx >= 0:
            return {"lead": lead, "project": state["projects"][project_idx]}
    raw_input = lead["one_liner"] or lead["direction"]
    if not raw_input:
        raise ServiceError(400, "invalid_input", "Lead 缺少可转项目的一句话或方向。")
    title = lead["display_name"] or lead["direction"] or "Ops Lead"
    schema = sanitize_schema({**structure_project(raw_input, user_title=title), "title": title})
    normalized = _materialize_structured_project(
        state=state,
        user=user,
        schema=schema,
        merged_input=raw_input,
        has_file=False,
        cta_token="",
        source="ops_convert",
        request_id="",
        entity_type="claimed_project",
        visible_in_library=True,
        ai_path="ops",
    )
    project_id = _ops_text(normalized.get("id", ""), max_len=24)
    project_idx = _find_project_index(state, project_id)
    if project_idx >= 0:
        private_project = copy.deepcopy(state["projects"][project_idx])
        share = normalize_share_state(private_project.get("share", {}), project_id)
        share["is_public"] = False
        share["published_at"] = ""
        share["last_shared_at"] = ""
        private_project["share"] = share
        private_project["visible_in_library"] = True
        private_project = normalize_project(private_project)
        state["projects"][project_idx] = private_project
        normalized = private_project
    lead["project_id"] = project_id
    lead["updated_at"] = _now_ts()
    leads[idx] = lead
    state["ops_leads"] = leads
    lead_profile = _get_ops_profile_from_state(state, "lead", lead["id"])
    if lead_profile.get("core_need") or lead_profile.get("need_tags") or lead_profile.get("offers"):
        project_profile = _normalize_ops_profile("project", project_id, lead_profile, None)
        profiles = [item for item in state.get("ops_profiles", []) if isinstance(item, dict)]
        profiles.append(project_profile)
        state["ops_profiles"] = profiles
    _ops_append_event(state, "lead_converted_project", user, {"lead_id": lead["id"], "project_id": project_id})
    save_state(state)
    return {"lead": lead, "project": normalized}


def _normalize_ops_activity(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    activity = {
        "id": _ops_text(current.get("id", ""), max_len=24) or _ops_text(payload.get("id", ""), max_len=24) or _ops_id("act"),
        "title": _ops_text(payload.get("title", current.get("title", "")), max_len=100),
        "city": _ops_text(payload.get("city", current.get("city", "")), max_len=40),
        "format": _ops_text(payload.get("format", current.get("format", "")), max_len=40),
        "date": _ops_text(payload.get("date", current.get("date", "")), max_len=40),
        "status": _ops_text(payload.get("status", current.get("status", "planning")), max_len=40) or "planning",
        "notes": _ops_text(payload.get("notes", current.get("notes", "")), max_len=1200),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not activity["title"]:
        raise ServiceError(400, "invalid_activity", "请填写活动名称。")
    return activity


def list_ops_activities(user: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    return {
        "activities": sorted([_normalize_ops_activity({}, item) for item in state.get("ops_activities", [])], key=lambda item: item.get("updated_at", ""), reverse=True),
        "memberships": [item for item in state.get("ops_activity_memberships", []) if isinstance(item, dict)],
    }


def upsert_ops_activity(user: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    activities = [item for item in state.get("ops_activities", []) if isinstance(item, dict)]
    requested_id = _ops_text(payload.get("id", ""), max_len=24)
    idx = _ops_find_index(activities, requested_id) if requested_id else -1
    activity = _normalize_ops_activity(payload, activities[idx] if idx >= 0 else None)
    if idx >= 0:
        activities[idx] = activity
    else:
        activities.append(activity)
    state["ops_activities"] = activities
    _ops_append_event(state, "activity_upserted", user, {"activity_id": activity["id"]})
    save_state(state)
    return {"activity": activity}


def _normalize_ops_membership(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    activity_id = _ops_text(payload.get("activity_id", current.get("activity_id", "")), max_len=24)
    subject_type = _ops_subject_type(payload.get("subject_type", current.get("subject_type", "")))
    subject_id = _ops_text(payload.get("subject_id", current.get("subject_id", "")), max_len=24)
    if not activity_id or not subject_id:
        raise ServiceError(400, "invalid_membership", "活动和对象不能为空。")
    now = _now_ts()
    return {
        "id": _ops_text(current.get("id", ""), max_len=24) or _ops_text(payload.get("id", ""), max_len=24) or _ops_id("mem"),
        "activity_id": activity_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "role": _ops_text(payload.get("role", current.get("role", "")), max_len=60),
        "status": _ops_text(payload.get("status", current.get("status", "candidate")), max_len=40) or "candidate",
        "willing_one_minute_intro": _ops_bool(payload, "willing_one_minute_intro", bool(current.get("willing_one_minute_intro", False))),
        "accepts_filming": _ops_bool(payload, "accepts_filming", bool(current.get("accepts_filming", False))),
        "notes": _ops_text(payload.get("notes", current.get("notes", "")), max_len=1200),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }


def upsert_ops_activity_membership(user: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    memberships = [item for item in state.get("ops_activity_memberships", []) if isinstance(item, dict)]
    requested_id = _ops_text(payload.get("id", ""), max_len=24)
    idx = _ops_find_index(memberships, requested_id) if requested_id else -1
    membership = _normalize_ops_membership(payload, memberships[idx] if idx >= 0 else None)
    if _ops_find_index([item for item in state.get("ops_activities", []) if isinstance(item, dict)], membership["activity_id"]) < 0:
        raise ServiceError(404, "not_found", "目标活动不存在。")
    if idx >= 0:
        memberships[idx] = membership
    else:
        memberships.append(membership)
    state["ops_activity_memberships"] = memberships
    _ops_append_event(state, "activity_membership_upserted", user, {"membership_id": membership["id"]})
    save_state(state)
    return {"membership": membership}


def _normalize_ops_routing(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    subject_type = _ops_subject_type(payload.get("subject_type", current.get("subject_type", "")))
    subject_id = _ops_text(payload.get("subject_id", current.get("subject_id", "")), max_len=24)
    if not subject_id:
        raise ServiceError(400, "invalid_routing", "分发对象不能为空。")
    now = _now_ts()
    record = {
        "id": _ops_text(current.get("id", ""), max_len=24) or _ops_text(payload.get("id", ""), max_len=24) or _ops_id("route"),
        "subject_type": subject_type,
        "subject_id": subject_id,
        "target_type": _ops_text(payload.get("target_type", current.get("target_type", "")), max_len=60),
        "target_name": _ops_text(payload.get("target_name", current.get("target_name", "")), max_len=100),
        "reason": _ops_text(payload.get("reason", current.get("reason", "")), max_len=500),
        "status": _ops_text(payload.get("status", current.get("status", "想法")), max_len=40) or "想法",
        "next_action": _ops_text(payload.get("next_action", current.get("next_action", "")), max_len=500),
        "notes": _ops_text(payload.get("notes", current.get("notes", "")), max_len=1200),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not record["target_type"] and not record["target_name"]:
        raise ServiceError(400, "invalid_routing", "请填写分发目标。")
    return record


def list_ops_routing_records(user: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    return {"records": sorted([_normalize_ops_routing({}, item) for item in state.get("ops_routing_records", [])], key=lambda item: item.get("updated_at", ""), reverse=True)}


def upsert_ops_routing_record(user: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    records = [item for item in state.get("ops_routing_records", []) if isinstance(item, dict)]
    requested_id = _ops_text(payload.get("id", ""), max_len=24)
    idx = _ops_find_index(records, requested_id) if requested_id else -1
    record = _normalize_ops_routing(payload, records[idx] if idx >= 0 else None)
    if idx >= 0:
        records[idx] = record
    else:
        records.append(record)
    state["ops_routing_records"] = records
    _ops_append_event(state, "routing_record_upserted", user, {"routing_id": record["id"]})
    save_state(state)
    return {"record": record}


LOCAL_OPS_USER = {"id": "local_ops", "email": "local@onefile.local"}
OPS_CRM_COLLECTIONS = {
    "inbox": "ops_inbox_items",
    "people": "ops_people",
    "organizations": "ops_organizations",
    "projects": "ops_projects",
    "opportunities": "ops_opportunities",
    "needs": "ops_needs",
    "offers": "ops_offers",
    "interactions": "ops_interactions",
    "contents": "ops_contents",
    "next-actions": "ops_next_actions",
    "next_actions": "ops_next_actions",
}
OPS_PERSON_ROLES = {"founder", "tech_provider", "operator", "investor", "park_operator", "ai_service_provider", "educator", "media", "government_resource", "other"}
OPS_ORG_TYPES = {"OPC_park", "AI_service_provider", "compute_provider", "university", "investor", "media_partner", "government_platform", "enterprise", "other"}
OPS_RELATIONSHIP_TEMPERATURES = {"cold", "warm", "active", "trusted"}
OPS_TRUST_LEVELS = {"unknown", "low", "medium", "high"}
OPS_PROJECT_STAGES = {"idea", "prototype", "pilot", "delivery", "revenue", "scaling"}
OPS_EVIDENCE_LEVELS = {"verbal", "materials", "customer_proof", "revenue_proof"}
OPS_OWNER_TYPES = {"person", "project", "organization", "opportunity"}
OPS_NEED_CATEGORIES = {"tech", "ops", "compute", "capital", "customer", "park", "content", "hiring", "education", "other"}
OPS_OFFER_CATEGORIES = {"tech", "ops", "compute", "capital", "customer", "park", "content", "education", "other"}
OPS_INTERACTION_CHANNELS = {"wechat", "douyin", "xiaohongshu", "offline", "phone", "event", "group"}
OPS_CONTENT_PLATFORMS = {"douyin", "xiaohongshu", "video_account", "article", "other"}
OPS_INBOX_ROUTE_TARGETS = {"inbox", "person", "organization", "project", "need", "offer", "interaction", "content", "archive"}
OPS_PRIORITIES = {"high", "medium", "low"}


def get_local_ops_user() -> Dict[str, Any]:
    return dict(LOCAL_OPS_USER)


def _ops_choice(value: Any, allowed: set[str], default: str, *, max_len: int = 40) -> str:
    safe = _ops_text(value, max_len=max_len)
    return safe if safe in allowed else default


def _ops_date(value: Any) -> str:
    safe = _ops_text(value, max_len=24)
    if not safe:
        return ""
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(safe, fmt)
            return parsed.strftime("%Y-%m-%d") if fmt == "%Y-%m-%d" else parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return safe


def _ops_id_list(value: Any, max_items: int = 24) -> List[str]:
    return _ops_list(value, max_items=max_items, max_len=64)


def _ops_metrics(value: Any) -> Dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    metrics: Dict[str, int] = {}
    for key in ["views", "likes", "comments", "saves", "shares", "follows", "dms"]:
        try:
            metrics[key] = max(0, int(raw.get(key, 0) or 0))
        except Exception:
            metrics[key] = 0
    return metrics


def _normalize_ops_inbox_item(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    item = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("inbox"),
        "raw_text": _ops_text(payload.get("raw_text", current.get("raw_text", "")), max_len=12000),
        "capture_type": _ops_text(payload.get("capture_type", current.get("capture_type", "note")), max_len=40) or "note",
        "who": _ops_text(payload.get("who", current.get("who", "")), max_len=120),
        "source_channel": _ops_text(payload.get("source_channel", current.get("source_channel", "")), max_len=40),
        "source_detail": _ops_text(payload.get("source_detail", current.get("source_detail", "")), max_len=120),
        "does_what": _ops_text(payload.get("does_what", current.get("does_what", "")), max_len=500),
        "can_offer": _ops_text(payload.get("can_offer", current.get("can_offer", "")), max_len=500),
        "currently_needs": _ops_text(payload.get("currently_needs", current.get("currently_needs", "")), max_len=500),
        "status": _ops_text(payload.get("status", current.get("status", "open")), max_len=40) or "open",
        "routed_to_type": _ops_text(payload.get("routed_to_type", current.get("routed_to_type", "")), max_len=40),
        "routed_to_id": _ops_text(payload.get("routed_to_id", current.get("routed_to_id", "")), max_len=64),
        "private_notes": _ops_text(payload.get("private_notes", current.get("private_notes", "")), max_len=1200),
        "tags": _ops_list(payload.get("tags", current.get("tags", [])), max_items=16, max_len=40),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not any([item["raw_text"], item["who"], item["does_what"], item["can_offer"], item["currently_needs"]]):
        raise ServiceError(400, "invalid_inbox_item", "请至少填写一段原始内容、人物、项目方向、供给或需求。")
    return item


def _normalize_ops_person(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    raw_roles = payload.get("roles", payload.get("role_tags", current.get("roles", current.get("role_tags", []))))
    roles = [item if item in OPS_PERSON_ROLES else "other" for item in _ops_list(raw_roles, max_items=12, max_len=40)]
    role_tags = _ops_list(payload.get("role_tags", current.get("role_tags", raw_roles)), max_items=12, max_len=160)
    display_name = _ops_text(
        payload.get("display_name", payload.get("name", current.get("display_name", current.get("name", "")))),
        max_len=120,
    )
    wechat_name = _ops_text(
        payload.get("wechat_name", payload.get("alias", current.get("wechat_name", current.get("alias", "")))),
        max_len=120,
    )
    person = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("person"),
        "name": display_name,
        "alias": wechat_name,
        "display_name": display_name,
        "wechat_name": wechat_name,
        "phone": _ops_text(payload.get("phone", current.get("phone", "")), max_len=80),
        "email": _ops_text(payload.get("email", current.get("email", "")), max_len=120),
        "city": _ops_text(payload.get("city", current.get("city", "")), max_len=60),
        "roles": roles or ["other"],
        "role_tags": role_tags or roles or ["other"],
        "organization_ids": _ops_id_list(payload.get("organization_ids", current.get("organization_ids", []))),
        "associated_organizations": _ops_list(payload.get("associated_organizations", current.get("associated_organizations", [])), max_items=24, max_len=160),
        "associated_opportunities": _ops_list(payload.get("associated_opportunities", current.get("associated_opportunities", [])), max_items=24, max_len=160),
        "source_channel": _ops_text(payload.get("source_channel", current.get("source_channel", "")), max_len=60),
        "relationship_temperature": _ops_choice(payload.get("relationship_temperature", current.get("relationship_temperature", "warm")), OPS_RELATIONSHIP_TEMPERATURES, "warm", max_len=24),
        "trust_level": _ops_choice(payload.get("trust_level", current.get("trust_level", "unknown")), OPS_TRUST_LEVELS, "unknown", max_len=24),
        "can_offer_summary": _ops_text(payload.get("can_offer_summary", current.get("can_offer_summary", "")), max_len=800),
        "currently_needs_summary": _ops_text(payload.get("currently_needs_summary", current.get("currently_needs_summary", "")), max_len=800),
        "can_offer": _ops_text(payload.get("can_offer", current.get("can_offer", payload.get("can_offer_summary", current.get("can_offer_summary", "")))), max_len=1000),
        "currently_needs": _ops_text(payload.get("currently_needs", current.get("currently_needs", payload.get("currently_needs_summary", current.get("currently_needs_summary", "")))), max_len=1000),
        "decision_power": _ops_choice(payload.get("decision_power", current.get("decision_power", "unknown")), OPS_TRUST_LEVELS, "unknown", max_len=24),
        "budget_signal": _ops_choice(payload.get("budget_signal", current.get("budget_signal", "unknown")), {"unknown", "weak", "medium", "strong"}, "unknown", max_len=24),
        "trust_notes": _ops_text(payload.get("trust_notes", current.get("trust_notes", "")), max_len=1200),
        "public_notes": _ops_text(payload.get("public_notes", current.get("public_notes", "")), max_len=1200),
        "private_notes": _ops_text(payload.get("private_notes", current.get("private_notes", "")), max_len=2400),
        "last_contacted_at": _ops_date(payload.get("last_contacted_at", current.get("last_contacted_at", ""))),
        "next_action": _ops_text(payload.get("next_action", current.get("next_action", "")), max_len=500),
        "next_action_at": _ops_date(payload.get("next_action_at", current.get("next_action_at", ""))),
        "priority": _ops_choice(payload.get("priority", current.get("priority", "medium")), OPS_PRIORITIES, "medium", max_len=24),
        "tags": _ops_list(payload.get("tags", current.get("tags", [])), max_items=20, max_len=40),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not person["display_name"] and not person["wechat_name"]:
        raise ServiceError(400, "invalid_person", "请至少填写姓名或微信名。")
    return person


def _normalize_ops_organization(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    relationship = _ops_text(payload.get("relationship_status", current.get("relationship_status", current.get("relationship_temperature", "warm"))), max_len=80) or "warm"
    org = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("org"),
        "name": _ops_text(payload.get("name", current.get("name", "")), max_len=160),
        "type": _ops_choice(payload.get("type", current.get("type", "other")), OPS_ORG_TYPES, "other", max_len=40),
        "city": _ops_text(payload.get("city", current.get("city", "")), max_len=60),
        "key_people_ids": _ops_id_list(payload.get("key_people_ids", current.get("key_people_ids", []))),
        "key_people": _ops_list(payload.get("key_people", current.get("key_people", [])), max_items=24, max_len=160),
        "offers": _ops_text(payload.get("offers", current.get("offers", "")), max_len=1000),
        "needs": _ops_text(payload.get("needs", current.get("needs", "")), max_len=1000),
        "can_offer": _ops_text(payload.get("can_offer", current.get("can_offer", payload.get("offers", current.get("offers", "")))), max_len=1200),
        "currently_needs": _ops_text(payload.get("currently_needs", current.get("currently_needs", payload.get("needs", current.get("needs", "")))), max_len=1200),
        "what_they_do": _ops_text(payload.get("what_they_do", current.get("what_they_do", "")), max_len=1200),
        "potential_value_to_me": _ops_text(payload.get("potential_value_to_me", current.get("potential_value_to_me", "")), max_len=1200),
        "risks": _ops_text(payload.get("risks", current.get("risks", "")), max_len=1200),
        "suitable_project_types": _ops_list(payload.get("suitable_project_types", current.get("suitable_project_types", [])), max_items=16, max_len=60),
        "cooperation_status": _ops_text(payload.get("cooperation_status", current.get("cooperation_status", "")), max_len=80),
        "relationship_status": relationship,
        "relationship_temperature": _ops_choice(payload.get("relationship_temperature", current.get("relationship_temperature", relationship)), OPS_RELATIONSHIP_TEMPERATURES, "warm", max_len=24),
        "notes": _ops_text(payload.get("notes", current.get("notes", "")), max_len=2400),
        "next_action": _ops_text(payload.get("next_action", current.get("next_action", "")), max_len=500),
        "next_action_at": _ops_date(payload.get("next_action_at", current.get("next_action_at", ""))),
        "priority": _ops_choice(payload.get("priority", current.get("priority", "medium")), OPS_PRIORITIES, "medium", max_len=24),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not org["name"]:
        raise ServiceError(400, "invalid_organization", "请填写机构名称。")
    return org


def _normalize_ops_project(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    project = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("opj"),
        "name": _ops_text(payload.get("name", current.get("name", "")), max_len=160),
        "founder_people_ids": _ops_id_list(payload.get("founder_people_ids", current.get("founder_people_ids", []))),
        "public_project_id": _ops_text(payload.get("public_project_id", current.get("public_project_id", "")), max_len=64),
        "one_liner": _ops_text(payload.get("one_liner", current.get("one_liner", "")), max_len=500),
        "target_customer": _ops_text(payload.get("target_customer", current.get("target_customer", "")), max_len=500),
        "problem": _ops_text(payload.get("problem", current.get("problem", "")), max_len=800),
        "solution": _ops_text(payload.get("solution", current.get("solution", "")), max_len=800),
        "current_stage": _ops_choice(payload.get("current_stage", current.get("current_stage", "idea")), OPS_PROJECT_STAGES, "idea", max_len=40),
        "evidence_level": _ops_choice(payload.get("evidence_level", current.get("evidence_level", "verbal")), OPS_EVIDENCE_LEVELS, "verbal", max_len=40),
        "business_loop_summary": _ops_text(payload.get("business_loop_summary", current.get("business_loop_summary", "")), max_len=1000),
        "recommended_org_ids": _ops_id_list(payload.get("recommended_org_ids", current.get("recommended_org_ids", []))),
        "sensitive_notes": _ops_text(payload.get("sensitive_notes", current.get("sensitive_notes", "")), max_len=2400),
        "share_permission": _ops_text(payload.get("share_permission", current.get("share_permission", "private")), max_len=40) or "private",
        "next_action": _ops_text(payload.get("next_action", current.get("next_action", "")), max_len=500),
        "next_action_at": _ops_date(payload.get("next_action_at", current.get("next_action_at", ""))),
        "tags": _ops_list(payload.get("tags", current.get("tags", [])), max_items=20, max_len=40),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    for key in [
        "has_customer",
        "has_order",
        "has_revenue",
        "has_delivery",
        "needs_compute",
        "needs_private_deployment",
        "needs_tech",
        "needs_ops",
        "needs_capital",
        "suitable_for_parks",
        "suitable_for_interview",
        "suitable_for_recommendation",
    ]:
        project[key] = _ops_bool(payload, key, bool(current.get(key, False)))
    if not project["name"] and not project["one_liner"]:
        raise ServiceError(400, "invalid_project", "请至少填写项目名称或一句话介绍。")
    return project


def _normalize_ops_opportunity(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    stage = _ops_text(payload.get("stage", payload.get("current_stage", current.get("stage", current.get("current_stage", "unknown")))), max_len=80) or "unknown"
    risk_value = payload.get("risk", current.get("risk", ""))
    risks_value = payload.get("risks", current.get("risks", risk_value))
    opportunity = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("opp"),
        "opportunity_name": _ops_text(payload.get("opportunity_name", current.get("opportunity_name", "")), max_len=200),
        "source": _ops_text(payload.get("source", current.get("source", "")), max_len=160),
        "related_people": _ops_list(payload.get("related_people", current.get("related_people", [])), max_items=24, max_len=160),
        "related_organizations": _ops_list(payload.get("related_organizations", current.get("related_organizations", [])), max_items=24, max_len=160),
        "stage": stage,
        "current_stage": stage,
        "core_need": _ops_text(payload.get("core_need", current.get("core_need", "")), max_len=1200),
        "why_it_matters": _ops_text(payload.get("why_it_matters", current.get("why_it_matters", "")), max_len=1600),
        "my_possible_role": _ops_text(payload.get("my_possible_role", current.get("my_possible_role", "")), max_len=1200),
        "my_role": _ops_text(payload.get("my_role", current.get("my_role", payload.get("my_possible_role", current.get("my_possible_role", "")))), max_len=1200),
        "required_partners_or_resources": _ops_text(payload.get("required_partners_or_resources", current.get("required_partners_or_resources", "")), max_len=1200),
        "possible_revenue_model": _ops_text(payload.get("possible_revenue_model", current.get("possible_revenue_model", "")), max_len=1600),
        "budget_signal": _ops_choice(payload.get("budget_signal", current.get("budget_signal", "unknown")), {"unknown", "weak", "medium", "strong"}, "unknown", max_len=24),
        "decision_process": _ops_text(payload.get("decision_process", current.get("decision_process", "")), max_len=1000),
        "decision_power_status": _ops_text(payload.get("decision_power_status", current.get("decision_power_status", payload.get("decision_process", current.get("decision_process", "unknown")))), max_len=1000) or "unknown",
        "next_action": _ops_text(payload.get("next_action", current.get("next_action", "")), max_len=800),
        "next_action_at": _ops_date(payload.get("next_action_at", current.get("next_action_at", ""))),
        "why_now": _ops_text(payload.get("why_now", current.get("why_now", "")), max_len=1200),
        "priority": _ops_choice(payload.get("priority", current.get("priority", "medium")), OPS_PRIORITIES, "medium", max_len=24),
        "risks": _ops_text(risks_value, max_len=1600),
        "risk": _ops_text(risk_value or risks_value, max_len=1600),
        "recommended_action_this_week": _ops_text(payload.get("recommended_action_this_week", current.get("recommended_action_this_week", "")), max_len=800),
        "private_notes": _ops_text(payload.get("private_notes", current.get("private_notes", "")), max_len=2400),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not opportunity["opportunity_name"]:
        raise ServiceError(400, "invalid_opportunity", "请填写机会名称。")
    if not opportunity["next_action"]:
        raise ServiceError(400, "invalid_opportunity", "机会必须有下一步动作。")
    return opportunity


def _normalize_ops_need(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    category = payload.get("category", payload.get("need_type", current.get("category", current.get("need_type", "other"))))
    need = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("need"),
        "owner_type": _ops_choice(payload.get("owner_type", current.get("owner_type", "person")), OPS_OWNER_TYPES, "person", max_len=24),
        "owner_id": _ops_text(payload.get("owner_id", current.get("owner_id", "")), max_len=64),
        "owner": _ops_text(payload.get("owner", current.get("owner", "")), max_len=160),
        "category": _ops_choice(category, OPS_NEED_CATEGORIES, "other", max_len=40),
        "need_type": _ops_text(payload.get("need_type", current.get("need_type", category)), max_len=80),
        "description": _ops_text(payload.get("description", current.get("description", "")), max_len=1000),
        "urgency": _ops_text(payload.get("urgency", current.get("urgency", "normal")), max_len=40) or "normal",
        "status": _ops_text(payload.get("status", current.get("status", "open")), max_len=40) or "open",
        "matched_offer_ids": _ops_id_list(payload.get("matched_offer_ids", current.get("matched_offer_ids", []))),
        "possible_matches": _ops_list(payload.get("possible_matches", current.get("possible_matches", [])), max_items=24, max_len=160),
        "next_action": _ops_text(payload.get("next_action", current.get("next_action", "")), max_len=500),
        "next_action_at": _ops_date(payload.get("next_action_at", current.get("next_action_at", ""))),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not need["description"]:
        raise ServiceError(400, "invalid_need", "请填写需求描述。")
    return need


def _normalize_ops_offer(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    category = payload.get("category", payload.get("offer_type", current.get("category", current.get("offer_type", "other"))))
    offer = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("offer"),
        "owner_type": _ops_choice(payload.get("owner_type", current.get("owner_type", "person")), {"person", "organization"}, "person", max_len=24),
        "owner_id": _ops_text(payload.get("owner_id", current.get("owner_id", "")), max_len=64),
        "owner": _ops_text(payload.get("owner", current.get("owner", "")), max_len=160),
        "category": _ops_choice(category, OPS_OFFER_CATEGORIES, "other", max_len=40),
        "offer_type": _ops_text(payload.get("offer_type", current.get("offer_type", category)), max_len=80),
        "description": _ops_text(payload.get("description", current.get("description", "")), max_len=1000),
        "constraints": _ops_text(payload.get("constraints", current.get("constraints", "")), max_len=1000),
        "available_for": _ops_list(payload.get("available_for", current.get("available_for", [])), max_items=16, max_len=60),
        "matched_need_ids": _ops_id_list(payload.get("matched_need_ids", current.get("matched_need_ids", []))),
        "suitable_for": _ops_text(payload.get("suitable_for", current.get("suitable_for", "")), max_len=1200),
        "proof_or_cases": _ops_text(payload.get("proof_or_cases", current.get("proof_or_cases", "")), max_len=1200),
        "needs_verification": _ops_text(payload.get("needs_verification", current.get("needs_verification", "unknown")), max_len=80) or "unknown",
        "next_action": _ops_text(payload.get("next_action", current.get("next_action", "")), max_len=500),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not offer["description"]:
        raise ServiceError(400, "invalid_offer", "请填写供给描述。")
    return offer


def _normalize_ops_interaction(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    summary = _ops_text(payload.get("summary", current.get("summary", "")), max_len=1200)
    title = _ops_text(payload.get("title", current.get("title", "")), max_len=160)
    interaction = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("int"),
        "date": _ops_date(payload.get("date", current.get("date", ""))) or now[:10],
        "title": title,
        "channel": _ops_choice(payload.get("channel", current.get("channel", "wechat")), OPS_INTERACTION_CHANNELS, "wechat", max_len=40),
        "participants": _ops_list(payload.get("participants", current.get("participants", [])), max_items=24, max_len=160),
        "people_ids": _ops_id_list(payload.get("people_ids", current.get("people_ids", []))),
        "organization_ids": _ops_id_list(payload.get("organization_ids", current.get("organization_ids", []))),
        "project_ids": _ops_id_list(payload.get("project_ids", current.get("project_ids", []))),
        "summary": summary or title,
        "key_points": _ops_list(payload.get("key_points", current.get("key_points", [])), max_items=32, max_len=300),
        "decisions_or_consensus": _ops_list(payload.get("decisions_or_consensus", current.get("decisions_or_consensus", [])), max_items=16, max_len=300),
        "open_questions": _ops_list(payload.get("open_questions", current.get("open_questions", [])), max_items=16, max_len=300),
        "commitments": _ops_text(payload.get("commitments", current.get("commitments", "")), max_len=1000),
        "next_action": _ops_text(payload.get("next_action", current.get("next_action", "")), max_len=500),
        "next_actions": _ops_list(payload.get("next_actions", current.get("next_actions", [])), max_items=16, max_len=300),
        "next_action_at": _ops_date(payload.get("next_action_at", current.get("next_action_at", ""))),
        "confidentiality_level": _ops_text(payload.get("confidentiality_level", current.get("confidentiality_level", "private")), max_len=40) or "private",
        "raw_notes": _ops_text(payload.get("raw_notes", current.get("raw_notes", "")), max_len=12000),
        "private_notes": _ops_text(payload.get("private_notes", current.get("private_notes", "")), max_len=2400),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not interaction["summary"] and not interaction["raw_notes"]:
        raise ServiceError(400, "invalid_interaction", "请填写沟通摘要或原始记录。")
    return interaction


def _normalize_ops_content(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    title = _ops_text(payload.get("title", payload.get("content_title", current.get("title", current.get("content_title", "")))), max_len=160)
    content = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("content"),
        "platform": _ops_choice(payload.get("platform", current.get("platform", "other")), OPS_CONTENT_PLATFORMS, "other", max_len=40),
        "content_title": title,
        "title": title,
        "topic_tags": _ops_list(payload.get("topic_tags", current.get("topic_tags", [])), max_items=20, max_len=40),
        "published_at": _ops_date(payload.get("published_at", current.get("published_at", ""))),
        "related_people_ids": _ops_id_list(payload.get("related_people_ids", current.get("related_people_ids", []))),
        "related_org_ids": _ops_id_list(payload.get("related_org_ids", current.get("related_org_ids", []))),
        "related_project_ids": _ops_id_list(payload.get("related_project_ids", current.get("related_project_ids", []))),
        "related_opportunity": _ops_text(payload.get("related_opportunity", current.get("related_opportunity", "")), max_len=160),
        "metrics": _ops_metrics(payload.get("metrics", current.get("metrics", {}))),
        "content_angle": _ops_text(payload.get("content_angle", current.get("content_angle", "")), max_len=1200),
        "key_message": _ops_text(payload.get("key_message", current.get("key_message", "")), max_len=1200),
        "target_audience": _ops_text(payload.get("target_audience", current.get("target_audience", "")), max_len=500),
        "possible_followup": _ops_text(payload.get("possible_followup", current.get("possible_followup", "")), max_len=1200),
        "publish_priority": _ops_choice(payload.get("publish_priority", current.get("publish_priority", "medium")), OPS_PRIORITIES, "medium", max_len=24),
        "insights": _ops_text(payload.get("insights", current.get("insights", "")), max_len=2000),
        "followup_content_ideas": _ops_text(payload.get("followup_content_ideas", current.get("followup_content_ideas", "")), max_len=2000),
        "private_notes": _ops_text(payload.get("private_notes", current.get("private_notes", "")), max_len=2400),
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not content["title"]:
        raise ServiceError(400, "invalid_content", "请填写内容标题。")
    return content


def _normalize_ops_next_action(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    current = copy.deepcopy(existing or {})
    now = _now_ts()
    action = {
        "id": _ops_text(current.get("id", ""), max_len=64) or _ops_id("action"),
        "action": _ops_text(payload.get("action", current.get("action", "")), max_len=800),
        "related_person_or_opportunity": _ops_text(payload.get("related_person_or_opportunity", current.get("related_person_or_opportunity", "")), max_len=200),
        "related_person": _ops_text(payload.get("related_person", current.get("related_person", payload.get("related_person_or_opportunity", current.get("related_person_or_opportunity", "")))), max_len=200),
        "expected_outcome": _ops_text(payload.get("expected_outcome", current.get("expected_outcome", "")), max_len=1000),
        "deadline_or_timing": _ops_text(payload.get("deadline_or_timing", current.get("deadline_or_timing", "")), max_len=120),
        "priority": _ops_choice(payload.get("priority", current.get("priority", "medium")), OPS_PRIORITIES, "medium", max_len=24),
        "reason": _ops_text(payload.get("reason", current.get("reason", "")), max_len=1000),
        "message_needed": _ops_text(payload.get("message_needed", current.get("message_needed", "")), max_len=2400),
        "status": _ops_text(payload.get("status", current.get("status", "open")), max_len=40) or "open",
        "created_at": _ops_text(current.get("created_at", ""), max_len=24) or now,
        "updated_at": now,
    }
    if not action["action"]:
        raise ServiceError(400, "invalid_next_action", "请填写行动内容。")
    return action


OPS_CRM_NORMALIZERS = {
    "inbox": _normalize_ops_inbox_item,
    "people": _normalize_ops_person,
    "organizations": _normalize_ops_organization,
    "projects": _normalize_ops_project,
    "opportunities": _normalize_ops_opportunity,
    "needs": _normalize_ops_need,
    "offers": _normalize_ops_offer,
    "interactions": _normalize_ops_interaction,
    "contents": _normalize_ops_content,
    "next-actions": _normalize_ops_next_action,
    "next_actions": _normalize_ops_next_action,
}


def _ops_collection_name(collection: str) -> str:
    safe = _ops_text(collection, max_len=40)
    key = OPS_CRM_COLLECTIONS.get(safe)
    if not key:
        raise ServiceError(404, "not_found", "Ops 集合不存在。")
    return key


def _ops_normalize_collection_item(collection: str, payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    normalizer = OPS_CRM_NORMALIZERS.get(collection)
    if not normalizer:
        raise ServiceError(404, "not_found", "Ops 集合不存在。")
    return normalizer(payload, existing)


def _ops_filter_items(collection: str, items: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = _ops_text(filters.get("q", ""), max_len=120).lower()
    status = _ops_text(filters.get("status", ""), max_len=40)
    city = _ops_text(filters.get("city", ""), max_len=60)
    category = _ops_text(filters.get("category", ""), max_len=40)
    owner_id = _ops_text(filters.get("owner_id", ""), max_len=64)
    out: List[Dict[str, Any]] = []
    for item in items:
        haystack = " ".join(str(value) for value in item.values() if isinstance(value, (str, int, float, bool, list))).lower()
        if q and q not in haystack:
            continue
        if status and _ops_text(item.get("status", ""), max_len=40) != status:
            continue
        if city and _ops_text(item.get("city", ""), max_len=60) != city:
            continue
        if category and _ops_text(item.get("category", ""), max_len=40) != category:
            continue
        if owner_id and _ops_text(item.get("owner_id", ""), max_len=64) != owner_id:
            continue
        if collection == "inbox" and not status and _ops_text(item.get("status", ""), max_len=40) == "archived":
            continue
        out.append(item)
    return out


def list_ops_items(user: Dict[str, Any], collection: str, filters: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    key = _ops_collection_name(collection)
    items = [_ops_normalize_collection_item(collection, {}, item) for item in state.get(key, []) if isinstance(item, dict)]
    items = _ops_filter_items(collection, items, filters)
    return {"items": sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)}


def create_ops_item(user: Dict[str, Any], collection: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    key = _ops_collection_name(collection)
    item = _ops_normalize_collection_item(collection, payload)
    state.setdefault(key, []).append(item)
    _ops_append_event(state, f"{collection}_created", user, {"id": item["id"]})
    save_state(state)
    return {"item": item}


def update_ops_item(user: Dict[str, Any], collection: str, item_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    key = _ops_collection_name(collection)
    items = [item for item in state.get(key, []) if isinstance(item, dict)]
    idx = _ops_find_index(items, item_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标记录不存在。")
    item = _ops_normalize_collection_item(collection, payload, items[idx])
    items[idx] = item
    state[key] = items
    _ops_append_event(state, f"{collection}_updated", user, {"id": item["id"]})
    save_state(state)
    return {"item": item}


def _payload_from_inbox(target_type: str, inbox_item: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    base = dict(payload)
    if target_type == "person":
        base.setdefault("display_name", inbox_item.get("who", ""))
        base.setdefault("source_channel", inbox_item.get("source_channel", ""))
        base.setdefault("can_offer_summary", inbox_item.get("can_offer", ""))
        base.setdefault("currently_needs_summary", inbox_item.get("currently_needs", ""))
        base.setdefault("public_notes", inbox_item.get("does_what", ""))
        base.setdefault("private_notes", inbox_item.get("raw_text", ""))
        base.setdefault("tags", inbox_item.get("tags", []))
    elif target_type == "organization":
        base.setdefault("name", inbox_item.get("who", ""))
        base.setdefault("offers", inbox_item.get("can_offer", ""))
        base.setdefault("needs", inbox_item.get("currently_needs", ""))
        base.setdefault("notes", inbox_item.get("raw_text", ""))
    elif target_type == "project":
        base.setdefault("name", inbox_item.get("who", ""))
        base.setdefault("one_liner", inbox_item.get("does_what") or inbox_item.get("raw_text", ""))
        base.setdefault("problem", inbox_item.get("currently_needs", ""))
        base.setdefault("business_loop_summary", inbox_item.get("can_offer", ""))
        base.setdefault("tags", inbox_item.get("tags", []))
    elif target_type == "need":
        base.setdefault("description", inbox_item.get("currently_needs") or inbox_item.get("raw_text", ""))
    elif target_type == "offer":
        base.setdefault("description", inbox_item.get("can_offer") or inbox_item.get("raw_text", ""))
    elif target_type == "interaction":
        base.setdefault("summary", inbox_item.get("does_what") or inbox_item.get("raw_text", ""))
        base.setdefault("raw_notes", inbox_item.get("raw_text", ""))
    elif target_type == "content":
        base.setdefault("title", inbox_item.get("does_what") or inbox_item.get("who", "内容线索"))
        base.setdefault("insights", inbox_item.get("raw_text", ""))
    return base


def route_ops_inbox_item(user: Dict[str, Any], inbox_id: str, target_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    safe_target = _ops_text(target_type, max_len=40)
    if safe_target not in OPS_INBOX_ROUTE_TARGETS:
        raise ServiceError(400, "invalid_route_target", "Inbox 分流目标无效。")
    state = load_state()
    inbox_items = [item for item in state.get("ops_inbox_items", []) if isinstance(item, dict)]
    idx = _ops_find_index(inbox_items, inbox_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "目标 Inbox 记录不存在。")
    inbox_item = _normalize_ops_inbox_item({}, inbox_items[idx])
    routed_item: Dict[str, Any] = {}
    if safe_target != "archive":
        collection = {
            "person": "people",
            "organization": "organizations",
            "project": "projects",
            "need": "needs",
            "offer": "offers",
            "interaction": "interactions",
            "content": "contents",
            "inbox": "inbox",
        }[safe_target]
        key = _ops_collection_name(collection)
        routed_payload = _payload_from_inbox(safe_target, inbox_item, payload)
        routed_item = _ops_normalize_collection_item(collection, routed_payload)
        state.setdefault(key, []).append(routed_item)
        inbox_item["routed_to_type"] = safe_target
        inbox_item["routed_to_id"] = routed_item["id"]
        inbox_item["status"] = "routed"
    else:
        inbox_item["status"] = "archived"
        inbox_item["routed_to_type"] = "archive"
        inbox_item["routed_to_id"] = ""
    inbox_item["updated_at"] = _now_ts()
    inbox_items[idx] = inbox_item
    state["ops_inbox_items"] = inbox_items
    _ops_append_event(state, "inbox_routed", user, {"inbox_id": inbox_item["id"], "target_type": safe_target, "target_id": routed_item.get("id", "")})
    save_state(state)
    return {"inbox_item": inbox_item, "item": routed_item}


def get_ops_summary(user: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    followups = _collect_ops_followups(state)
    open_inbox = [item for item in state.get("ops_inbox_items", []) if isinstance(item, dict) and _ops_text(item.get("status", ""), max_len=40) in {"", "open"}]
    opportunities = [item for item in state.get("ops_opportunities", []) if isinstance(item, dict)]
    next_actions = [item for item in state.get("ops_next_actions", []) if isinstance(item, dict) and _ops_text(item.get("status", "open"), max_len=40) not in {"done", "closed", "archived"}]
    summary = {
        "inbox_count": len(open_inbox),
        "people_count": len([item for item in state.get("ops_people", []) if isinstance(item, dict)]),
        "organization_count": len([item for item in state.get("ops_organizations", []) if isinstance(item, dict)]),
        "project_count": len([item for item in state.get("ops_projects", []) if isinstance(item, dict)]),
        "opportunity_count": len(opportunities),
        "high_priority_opportunity_count": len([item for item in opportunities if _ops_text(item.get("priority", ""), max_len=24) == "high"]),
        "need_count": len([item for item in state.get("ops_needs", []) if isinstance(item, dict) and _ops_text(item.get("status", ""), max_len=40) not in {"closed", "done", "archived"}]),
        "offer_count": len([item for item in state.get("ops_offers", []) if isinstance(item, dict)]),
        "interaction_count": len([item for item in state.get("ops_interactions", []) if isinstance(item, dict)]),
        "content_count": len([item for item in state.get("ops_contents", []) if isinstance(item, dict)]),
        "next_action_count": len(next_actions),
        "high_priority_next_action_count": len([item for item in next_actions if _ops_text(item.get("priority", ""), max_len=24) == "high"]),
        "followup_count": len(followups["all"]),
        "overdue_followup_count": len(followups["overdue"]),
        "today_followup_count": len(followups["today"]),
        "this_week_followup_count": len(followups["this_week"]),
    }
    return {"summary": summary}


def _entity_label(state: Dict[str, Any], entity_type: str, entity_id: str) -> str:
    collection = {"person": "people", "organization": "organizations", "project": "projects", "need": "needs", "interaction": "interactions"}.get(entity_type)
    if not collection:
        return entity_id
    key = OPS_CRM_COLLECTIONS[collection]
    for item in state.get(key, []):
        if not isinstance(item, dict) or _ops_text(item.get("id", ""), max_len=64) != entity_id:
            continue
        return _ops_text(item.get("display_name") or item.get("wechat_name") or item.get("name") or item.get("description") or item.get("summary") or entity_id, max_len=160)
    return entity_id


def _followup_bucket(next_at: str, today: datetime) -> str:
    if not next_at:
        return "unscheduled"
    parsed = _parse_updated_at(next_at)
    if parsed == datetime.min:
        return "unscheduled"
    today_start = datetime(today.year, today.month, today.day)
    tomorrow_start = today_start + timedelta(days=1)
    week_end = today_start + timedelta(days=7)
    if parsed < today_start:
        return "overdue"
    if parsed < tomorrow_start:
        return "today"
    if parsed < week_end:
        return "this_week"
    return "later"


def _collect_ops_followups(state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    today = _now_datetime()
    buckets: Dict[str, List[Dict[str, Any]]] = {"overdue": [], "today": [], "this_week": [], "later": [], "unscheduled": [], "all": []}
    sources = [
        ("person", "people", "ops_people"),
        ("organization", "organizations", "ops_organizations"),
        ("project", "projects", "ops_projects"),
        ("need", "needs", "ops_needs"),
        ("interaction", "interactions", "ops_interactions"),
    ]
    for entity_type, collection, key in sources:
        for raw in state.get(key, []):
            if not isinstance(raw, dict):
                continue
            item = _ops_normalize_collection_item(collection, {}, raw)
            action = _ops_text(item.get("next_action", ""), max_len=500)
            next_at = _ops_date(item.get("next_action_at", ""))
            if not action and not next_at:
                continue
            followup = {
                "id": f"{entity_type}:{item['id']}",
                "entity_type": entity_type,
                "entity_id": item["id"],
                "label": _entity_label(state, entity_type, item["id"]),
                "next_action": action,
                "next_action_at": next_at,
                "bucket": _followup_bucket(next_at, today),
                "updated_at": item.get("updated_at", ""),
            }
            buckets[followup["bucket"]].append(followup)
            buckets["all"].append(followup)
    for key in buckets:
        buckets[key] = sorted(buckets[key], key=lambda item: (item.get("next_action_at") or "9999-99-99", item.get("updated_at", "")))
    return buckets


def get_ops_followups(user: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    return {"followups": _collect_ops_followups(load_state())}


def get_ops_relationship_map(user: Dict[str, Any], entity_type: str, entity_id: str) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    safe_type = _ops_text(entity_type, max_len=24)
    safe_id = _ops_text(entity_id, max_len=64)
    if safe_type not in {"person", "organization", "project"} or not safe_id:
        raise ServiceError(400, "invalid_entity", "关系视图对象无效。")
    related: Dict[str, List[Dict[str, Any]]] = {
        "people": [],
        "organizations": [],
        "projects": [],
        "needs": [],
        "offers": [],
        "interactions": [],
        "contents": [],
    }
    projects = [_normalize_ops_project({}, item) for item in state.get("ops_projects", []) if isinstance(item, dict)]
    active_project = next((project for project in projects if project["id"] == safe_id), None) if safe_type == "project" else None
    for person in [_normalize_ops_person({}, item) for item in state.get("ops_people", []) if isinstance(item, dict)]:
        if (
            (safe_type == "person" and person["id"] == safe_id)
            or (safe_type == "organization" and safe_id in person.get("organization_ids", []))
            or (safe_type == "project" and active_project and person["id"] in active_project.get("founder_people_ids", []))
        ):
            related["people"].append(person)
    for org in [_normalize_ops_organization({}, item) for item in state.get("ops_organizations", []) if isinstance(item, dict)]:
        if (
            (safe_type == "organization" and org["id"] == safe_id)
            or (safe_type == "person" and safe_id in org.get("key_people_ids", []))
            or (safe_type == "project" and active_project and org["id"] in active_project.get("recommended_org_ids", []))
        ):
            related["organizations"].append(org)
    for project in projects:
        if safe_type == "project" and project["id"] == safe_id:
            related["projects"].append(project)
        if safe_type == "person" and safe_id in project.get("founder_people_ids", []):
            related["projects"].append(project)
        if safe_type == "organization" and safe_id in project.get("recommended_org_ids", []):
            related["projects"].append(project)
    for need in [_normalize_ops_need({}, item) for item in state.get("ops_needs", []) if isinstance(item, dict)]:
        if need.get("owner_type") == safe_type and need.get("owner_id") == safe_id:
            related["needs"].append(need)
    for offer in [_normalize_ops_offer({}, item) for item in state.get("ops_offers", []) if isinstance(item, dict)]:
        if offer.get("owner_type") == safe_type and offer.get("owner_id") == safe_id:
            related["offers"].append(offer)
    for interaction in [_normalize_ops_interaction({}, item) for item in state.get("ops_interactions", []) if isinstance(item, dict)]:
        if (safe_type == "person" and safe_id in interaction.get("people_ids", [])) or (safe_type == "organization" and safe_id in interaction.get("organization_ids", [])) or (safe_type == "project" and safe_id in interaction.get("project_ids", [])):
            related["interactions"].append(interaction)
    for content in [_normalize_ops_content({}, item) for item in state.get("ops_contents", []) if isinstance(item, dict)]:
        if (safe_type == "person" and safe_id in content.get("related_people_ids", [])) or (safe_type == "organization" and safe_id in content.get("related_org_ids", [])) or (safe_type == "project" and safe_id in content.get("related_project_ids", [])):
            related["contents"].append(content)
    return {"entity": {"type": safe_type, "id": safe_id, "label": _entity_label(state, safe_type, safe_id)}, "related": related}


def export_ops_crm(user: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    return {
        "exported_at": _now_ts(),
        "schema_version": int(state.get("schema_version", 4)),
        "ops": {key: [item for item in state.get(key, []) if isinstance(item, dict)] for key in OPS_CRM_COLLECTIONS.values()},
    }


def import_ops_crm(user: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    ops_payload = payload.get("ops", payload)
    if not isinstance(ops_payload, dict):
        raise ServiceError(400, "invalid_import", "导入文件格式无效。")
    state = load_state()
    imported_counts: Dict[str, int] = {}
    for collection, key in OPS_CRM_COLLECTIONS.items():
        raw_items = ops_payload.get(key, [])
        if not isinstance(raw_items, list):
            continue
        normalized = []
        for raw in raw_items:
            if isinstance(raw, dict):
                normalized.append(_ops_normalize_collection_item(collection, {}, raw))
        state[key] = normalized
        imported_counts[key] = len(normalized)
    _ops_append_event(state, "ops_imported", user, imported_counts)
    save_state(state)
    return {"ok": True, "imported": imported_counts}


BP_STAGE_OPTIONS = {"idea", "prototype", "pilot", "delivery", "revenue", "scaling", "unknown"}
BP_SERVICE_TYPES = {"project_diagnosis", "manual_refinement", "bp_restructure", "resource_path"}
BP_SERVICE_STATUSES = {"new", "contacted", "quoted", "in_progress", "completed", "paused"}
BP_INTERNAL_STATUSES = {"submitted", "new_service_request", "to_contact", "contacted", "to_quote", "quoted", "refining", "delivered", "paused", "abandoned"}
BP_PRIORITIES = {"high", "medium", "low"}
BP_PAGE_BLUEPRINTS = [
    ("项目封面", "说明项目名称、一句话定位、核心价值和当前阶段。"),
    ("项目逻辑", "说明项目在行业链条中的位置，以及它补的是哪一个具体缺口。"),
    ("行业痛点", "说明供给侧、需求侧或产业链中真实存在的问题。"),
    ("市场切口", "说明项目真正切入的具体交易、人群、场景或供给问题。"),
    ("现有方案缺口", "说明现有解决方案分别解决了什么，又留下了什么问题。"),
    ("当前进展 / 业务基础", "说明项目已有客户、订单、收入、Demo、产品、合作资源或其他验证结果。"),
    ("为什么现在", "说明政策、技术、供给、用户行为或团队积累发生了什么变化。"),
    ("产品闭环", "说明供给、需求、匹配、交易、交付和收入如何形成闭环。"),
    ("产品 / 系统结构", "说明 C 端、B 端、后台、中台、AI 模块或数据模块之间的关系。"),
    ("商业模式", "说明谁付费、按什么收费，以及哪些收入已经验证。"),
    ("竞争定位", "说明项目与现有方案、竞品或替代路径的差异。"),
    ("核心壁垒", "说明长期价值来自供给、数据、流程、资源、场景、技术还是运营能力。"),
    ("增长计划", "说明未来 3-12 个月的推进节奏、关键指标和阶段目标。"),
    ("团队与资源诉求", "说明团队基础、当前短板，以及希望外部提供什么资源。"),
]
BP_RESOURCE_PATHS = [
    ("园区 / 政策", ["园区", "政策", "opc", "入驻"], "适合先补场景、政策匹配和落地诉求。"),
    ("活动 / 路演", ["活动", "路演", "闭门会", "分享", "介绍"], "适合先压缩项目表达和一分钟介绍口径。"),
    ("客户 / 订单", ["客户", "订单", "销售", "收入", "试点"], "适合先补客户画像、成交证据和交付闭环。"),
    ("技术合作", ["技术", "开发", "agent", "rag", "系统", "团队"], "适合先明确技术缺口、合作方式和交付边界。"),
    ("融资沟通", ["融资", "投资", "资本", "股权"], "适合先补业务证据、增长计划和资金用途。"),
    ("算力 / 私有化部署", ["算力", "私有化", "部署", "服务器", "本地"], "适合先补部署场景、数据安全和成本约束。"),
    ("内容曝光", ["内容", "曝光", "媒体", "访谈", "视频"], "适合先补传播角度、案例边界和公开授权。"),
    ("合作伙伴", ["合作", "伙伴", "资源", "渠道", "生态"], "适合先明确希望谁参与、对方能得到什么。"),
]


def _bp_list(value: Any, max_items: int = 12, max_len: int = 80) -> List[str]:
    if isinstance(value, list):
        return _ops_list(value, max_items=max_items, max_len=max_len)
    safe = _ops_text(value, max_len=max_len * max_items)
    if not safe:
        return []
    parts = re.split(r"[，,、/；;|]+", safe)
    return [item for item in [_ops_text(part, max_len=max_len) for part in parts] if item][:max_items]


def _bp_now_version(project_id: str, version_name: str, change_summary: str) -> Dict[str, Any]:
    now = _now_ts()
    return {
        "id": _ops_id("bpv"),
        "project_id": project_id,
        "version_name": _ops_text(version_name, max_len=120),
        "change_summary": _ops_text(change_summary, max_len=800),
        "created_at": now,
    }


def _find_bp_project_by_token(state: Dict[str, Any], token: str) -> Optional[Dict[str, Any]]:
    safe_token = _ops_text(token, max_len=120)
    if not safe_token:
        return None
    return next(
        (
            item
            for item in state.get("bp_projects", [])
            if isinstance(item, dict) and _ops_text(item.get("user_visible_token", ""), max_len=120) == safe_token
        ),
        None,
    )


def _find_bp_project_by_id(state: Dict[str, Any], project_id: str) -> Optional[Dict[str, Any]]:
    safe_id = _ops_text(project_id, max_len=64)
    return next((item for item in state.get("bp_projects", []) if isinstance(item, dict) and _ops_text(item.get("id", ""), max_len=64) == safe_id), None)


def _replace_bp_project(state: Dict[str, Any], project: Dict[str, Any]) -> None:
    items = [item for item in state.get("bp_projects", []) if isinstance(item, dict)]
    idx = _ops_find_index(items, _ops_text(project.get("id", ""), max_len=64))
    if idx >= 0:
        items[idx] = project
    else:
        items.append(project)
    state["bp_projects"] = items


def _bp_project_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_ts()
    name = _ops_text(payload.get("name", ""), max_len=160)
    tagline = _ops_text(payload.get("tagline", payload.get("one_liner", "")), max_len=500)
    raw_material = _ops_text(payload.get("raw_material", payload.get("rawMaterial", "")), max_len=20000)
    if not name or not raw_material:
        raise ServiceError(400, "invalid_bp_project", "请至少填写项目名称和原始材料。")
    stage = _ops_choice(payload.get("stage", "unknown"), BP_STAGE_OPTIONS, "unknown", max_len=40)
    resources = _bp_list(payload.get("current_resource_need", payload.get("current_resource_needs", [])), max_items=10, max_len=80)
    visibility = _ops_choice(payload.get("visibility", "private"), {"private", "share_card", "anonymous_case"}, "private", max_len=40)
    return {
        "id": _ops_id("bp"),
        "name": name,
        "founder_name": _ops_text(payload.get("founder_name", payload.get("founderName", "")), max_len=120),
        "tagline": tagline,
        "industry": _ops_text(payload.get("industry", ""), max_len=120),
        "stage": stage,
        "target_customer": _ops_text(payload.get("target_customer", payload.get("targetCustomer", "")), max_len=500),
        "current_resource_need": resources,
        "visibility": visibility,
        "contact_wechat": _ops_text(payload.get("contact_wechat", payload.get("contactWechat", "")), max_len=120),
        "contact_phone": _ops_text(payload.get("contact_phone", payload.get("contactPhone", "")), max_len=80),
        "contact_email": _ops_text(payload.get("contact_email", payload.get("contactEmail", "")), max_len=160),
        "share_card_requested": visibility in {"share_card", "anonymous_case"},
        "readiness_score": 0,
        "recommended_path": "",
        "submission_source": _ops_text(payload.get("submission_source", "diagnose_form"), max_len=80) or "diagnose_form",
        "user_visible_token": f"bpt_{secrets.token_urlsafe(18).replace('-', '').replace('_', '')[:24]}",
        "internal_status": "submitted",
        "priority": "medium",
        "budget_signal": "unknown",
        "decision_power": "unknown",
        "service_quote": "",
        "internal_notes": "",
        "private_feedback": "",
        "next_action": "",
        "next_action_at": "",
        "created_at": now,
        "updated_at": now,
    }


def _bp_raw_material(project_id: str, payload: Dict[str, Any], *, default_title: str) -> Dict[str, Any]:
    content = _ops_text(payload.get("content", payload.get("raw_material", payload.get("rawMaterial", ""))), max_len=20000)
    if not content:
        raise ServiceError(400, "invalid_raw_material", "请填写材料内容。")
    return {
        "id": _ops_id("bpr"),
        "project_id": project_id,
        "type": _ops_text(payload.get("type", "text"), max_len=40) or "text",
        "title": _ops_text(payload.get("title", default_title), max_len=160) or default_title,
        "content": content,
        "related_page_number": int(payload.get("related_page_number", 0) or 0),
        "created_at": _now_ts(),
    }


def _bp_materials_text(materials: List[Dict[str, Any]]) -> str:
    return "\n".join(_ops_text(item.get("content", ""), max_len=20000) for item in materials if isinstance(item, dict))


def _bp_has_any(text: str, keywords: List[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _bp_pick_sentence(text: str, keywords: List[str], fallback: str) -> str:
    sentences = [item.strip() for item in re.split(r"[。！？\n]", text) if item.strip()]
    for sentence in sentences:
        if _bp_has_any(sentence, keywords):
            return _ops_text(sentence, max_len=500)
    return fallback


def _bp_recommended_path(project: Dict[str, Any], material_text: str) -> str:
    needs = " ".join(project.get("current_resource_need", []))
    if _bp_has_any(f"{needs} {material_text}", ["园区", "政策", "opc"]):
        return "适合先做园区 / 政策资源沟通材料"
    if _bp_has_any(f"{needs} {material_text}", ["技术", "开发", "agent", "rag", "系统"]):
        return "适合先做技术伙伴 / 交付团队沟通材料"
    if _bp_has_any(f"{needs} {material_text}", ["客户", "订单", "销售", "收入"]):
        return "适合先做客户 / 订单验证材料"
    if _bp_has_any(f"{needs} {material_text}", ["融资", "投资", "资本"]):
        return "适合先补业务证据后再进入融资沟通"
    return "适合先完成项目表达诊断和材料缺口补齐"


def _bp_readiness(project: Dict[str, Any], material_text: str) -> int:
    score = 25
    if project.get("tagline"):
        score += 10
    if project.get("target_customer") or _bp_has_any(material_text, ["客户", "用户", "企业", "老人", "园区", "医院"]):
        score += 10
    if _bp_has_any(material_text, ["demo", "原型", "开发", "上线", "软著", "已做", "已经"]):
        score += 12
    if _bp_has_any(material_text, ["客户", "订单", "收入", "盈利", "交付", "案例"]):
        score += 15
    if _bp_has_any(material_text, ["ai", "agent", "rag", "大模型", "智能体", "自动化"]):
        score += 10
    if _bp_has_any(material_text, ["收费", "付费", "商业模式", "预算", "变现"]):
        score += 10
    if project.get("current_resource_need"):
        score += 8
    return max(20, min(92, score))


def _bp_score_breakdown(project: Dict[str, Any], material_text: str) -> Dict[str, int]:
    return {
        "clarity": 78 if project.get("tagline") else 42,
        "evidence": 75 if _bp_has_any(material_text, ["客户", "订单", "收入", "案例", "试点", "软著"]) else 38,
        "product": 78 if _bp_has_any(material_text, ["demo", "原型", "产品", "上线", "系统", "web"]) else 40,
        "business_model": 72 if _bp_has_any(material_text, ["收费", "付费", "收入", "订单", "预算", "商业模式"]) else 35,
        "ai_relevance": 76 if _bp_has_any(material_text, ["ai", "agent", "rag", "大模型", "智能体", "自动化"]) else 36,
        "team": 72 if project.get("founder_name") or _bp_has_any(material_text, ["团队", "创始人", "背景", "资质", "经验"]) else 34,
        "resource_ask": 80 if project.get("current_resource_need") else 35,
        "material_completeness": _bp_readiness(project, material_text),
    }


def _bp_level(score: int) -> str:
    if score >= 70:
        return "高"
    if score >= 45:
        return "中"
    return "低"


def _bp_resource_readiness(project: Dict[str, Any], insight: Dict[str, Any], material_text: str) -> List[Dict[str, str]]:
    selected = " ".join(project.get("current_resource_need", []))
    result: List[Dict[str, str]] = []
    for path, keywords, default_next in BP_RESOURCE_PATHS:
        keyword_hit = _bp_has_any(f"{selected} {material_text}", keywords)
        evidence_hit = _bp_has_any(material_text, ["客户", "订单", "收入", "demo", "原型", "试点", "交付", "软著"])
        score = 35 + (25 if keyword_hit else 0) + (20 if evidence_hit else 0) + (10 if project.get("tagline") else 0)
        level = _bp_level(score)
        missing = "需要补充可被资源方验证的证据材料。"
        if path == "园区 / 政策":
            missing = "需要补充落地城市、产业方向、入驻诉求和场景承接能力。"
        elif path == "活动 / 路演":
            missing = "需要补充一分钟介绍、项目亮点和可公开表达边界。"
        elif path == "客户 / 订单":
            missing = "需要补充目标客户、试点案例、成交路径或订单证明。"
        elif path == "技术合作":
            missing = "需要补充技术缺口、现有系统状态和合作方式。"
        elif path == "融资沟通":
            missing = "需要补充业务数据、增长计划、资金用途和团队能力。"
        elif path == "算力 / 私有化部署":
            missing = "需要补充部署场景、数据规模、安全要求和预算边界。"
        elif path == "内容曝光":
            missing = "需要补充可公开案例、故事角度和不方便公开的信息。"
        elif path == "合作伙伴":
            missing = "需要补充想找的伙伴类型、合作方式和双方收益。"
        reason = "材料里已经出现相关资源诉求和初步项目基础。" if level == "高" else "材料里有部分线索，但资源方还需要更多证据。" if level == "中" else "当前材料还不足以支撑这一路径的外部沟通。"
        result.append({"path": path, "level": level, "reason": reason, "missing": missing, "next_step": default_next})
    return result


def _bp_likely_questions(project: Dict[str, Any], insight: Dict[str, Any], material_text: str) -> List[str]:
    questions = [
        "现在是否已经有真实客户、试用用户、订单或交付案例？",
        "AI 在项目里是核心能力，还是提高效率的工具？具体进入哪个流程？",
        "项目收入来自哪里，谁付费，按什么方式收费？",
        "团队里谁负责产品、技术、交付和商务？",
        "你最希望资源方现在具体帮什么？",
        "为什么现在适合推进这个项目？",
        "与现有方案或替代路径相比，你的差异是什么？",
        "下一步 30 天最关键的推进动作是什么？",
    ]
    if _bp_has_any(material_text, ["医疗", "医院", "药", "患者", "医保"]):
        questions.insert(1, "医疗健康相关内容有哪些合规边界和可公开表达限制？")
    if _bp_has_any(material_text, ["园区", "政策", "opc"]):
        questions.insert(1, "你希望园区提供空间、政策、场景、客户还是后续融资资源？")
    return questions[:8]


def _bp_next_actions(project: Dict[str, Any], insight: Dict[str, Any], material_text: str) -> List[str]:
    actions = ["把资源诉求从“找资源”改成一个具体对象、具体场景或具体合作方式。"]
    if not _bp_has_any(material_text, ["客户", "订单", "收入", "案例", "试点"]):
        actions.insert(0, "补充一个真实客户、试点、订单、使用场景或交付案例。")
    if not project.get("tagline"):
        actions.append("先重写一句话定位，让资源方 10 秒内理解项目在做什么。")
    if not _bp_has_any(material_text, ["团队", "创始人", "资质", "经验"]):
        actions.append("补充团队背景、分工和当前最短板能力。")
    actions.append("整理一版可分享项目卡，再决定是否进入完整 BP 或路演材料重构。")
    return actions[:3]


def _bp_structure_preview(pages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    preview: List[Dict[str, str]] = []
    for page in pages:
        missing = [item for item in page.get("missing_materials", []) if isinstance(item, str)]
        enough = bool(missing) and all("已有初步材料" in item for item in missing)
        preview.append(
            {
                "module": _ops_text(page.get("title", ""), max_len=120),
                "question_to_answer": _ops_text(page.get("question", ""), max_len=240),
                "current_status": "已有初步材料，仍建议人工精修。" if enough else "需要补充材料。",
                "missing_material": _ops_text("；".join(missing[:2]), max_len=240) or "待补充",
            }
        )
    return preview


def _generate_bp_insight(project: Dict[str, Any], materials: List[Dict[str, Any]]) -> Dict[str, Any]:
    text = _bp_materials_text(materials)
    now = _now_ts()
    problem = _bp_pick_sentence(text, ["痛点", "困难", "缺", "问题", "吃力", "安全"], "原始材料还没有充分说明项目要解决的核心问题。")
    solution = project.get("tagline") or _bp_pick_sentence(text, ["提供", "开发", "系统", "agent", "平台", "助手"], "原始材料还没有充分说明解决方案。")
    traction = _bp_pick_sentence(text, ["已", "已经", "demo", "原型", "软著", "客户", "订单", "收入"], "当前进展材料不足，需要补充产品、客户、订单或交付证明。")
    business_model = _bp_pick_sentence(text, ["收费", "付费", "收入", "盈利", "订单", "预算", "变现"], "商业模式尚不清楚，需要补充谁付费、按什么收费、是否已验证。")
    ai_relevance = _bp_pick_sentence(text, ["ai", "agent", "rag", "大模型", "智能体", "自动化"], "AI 相关性需要补充说明：AI 具体进入哪个流程、替代什么成本或提升什么效率。")
    key_data = _bp_pick_sentence(text, ["万", "%", "个", "家", "人", "订单", "收入", "客户"], "关键数据不足，需要补充客户数量、订单、收入、使用数据或交付结果。")
    resource_needs = "、".join(project.get("current_resource_need", [])) or _bp_pick_sentence(text, ["需要", "缺", "寻找", "对接", "希望"], "当前资源诉求还需要具体化。")
    recommended_path = _bp_recommended_path(project, text)
    readiness = _bp_readiness(project, text)
    project["readiness_score"] = readiness
    project["recommended_path"] = recommended_path
    score_breakdown = _bp_score_breakdown(project, text)
    return {
        "id": _ops_id("bpi"),
        "project_id": project["id"],
        "problem": problem,
        "solution": solution,
        "business_model": business_model,
        "ai_relevance": ai_relevance,
        "traction": traction,
        "key_data": key_data,
        "resource_needs": resource_needs,
        "material_gaps": [],
        "recommended_path": recommended_path,
        "readiness_score": readiness,
        "score_breakdown": score_breakdown,
        "resource_readiness": [],
        "likely_questions": _bp_likely_questions(project, {}, text),
        "next_actions": _bp_next_actions(project, {}, text),
        "bp_structure_preview": [],
        "share_card": {
            "title": project.get("name", ""),
            "one_line": project.get("tagline") or solution,
            "stage": project.get("stage", "unknown"),
            "target_customer": project.get("target_customer", "") or "待补充",
            "resource_ask": resource_needs,
            "recommended_path": recommended_path,
            "highlights": [solution, traction, ai_relevance],
            "gaps": [],
        },
        "created_at": now,
        "updated_at": now,
    }


def _bp_missing_for_page(page_number: int, project: Dict[str, Any], insight: Dict[str, Any], material_text: str) -> List[str]:
    missing: List[str] = []
    if page_number in {3, 4} and not _bp_has_any(material_text, ["客户", "用户", "需求", "场景", "交易"]):
        missing.append("需要补充目标客户、真实场景或具体交易切口。")
    if page_number == 6 and not _bp_has_any(material_text, ["客户", "订单", "收入", "交付", "demo", "软著"]):
        missing.append("需要补充 Demo、客户、订单、收入、交付或其他验证结果。")
    if page_number == 8 and not _bp_has_any(material_text, ["供给", "需求", "匹配", "交付", "收入", "闭环"]):
        missing.append("需要说明供给、需求、交付和收入如何形成闭环。")
    if page_number == 9 and not _bp_has_any(material_text, ["系统", "模块", "后台", "agent", "rag", "数据", "模型"]):
        missing.append("需要补充产品 / 系统结构或 AI 模块关系。")
    if page_number == 10 and "尚不清楚" in insight.get("business_model", ""):
        missing.append("需要补充谁付费、按什么收费、是否已有收入验证。")
    if page_number == 11 and not _bp_has_any(material_text, ["竞品", "替代", "差异", "现有方案"]):
        missing.append("需要补充与现有方案或替代路径的差异。")
    if page_number == 12 and not _bp_has_any(material_text, ["壁垒", "数据", "资源", "流程", "资质", "渠道"]):
        missing.append("需要说明长期壁垒来自资源、数据、流程、场景还是技术。")
    if page_number == 13 and not _bp_has_any(material_text, ["计划", "目标", "个月", "下一步", "指标"]):
        missing.append("需要补充未来 3-12 个月的计划和关键指标。")
    if page_number == 14 and not project.get("founder_name") and not _bp_has_any(material_text, ["团队", "创始人", "背景", "资质"]):
        missing.append("需要补充团队背景、当前短板和明确资源诉求。")
    return missing


def _generate_bp_pages(project: Dict[str, Any], insight: Dict[str, Any], materials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    text = _bp_materials_text(materials)
    now = _now_ts()
    pages: List[Dict[str, Any]] = []
    for idx, (title, answer) in enumerate(BP_PAGE_BLUEPRINTS, start=1):
        missing = _bp_missing_for_page(idx, project, insight, text)
        existing = []
        if idx == 1:
            existing.append(project.get("tagline") or "已有项目名称，定位仍需进一步压缩。")
        elif idx == 6:
            existing.append(insight.get("traction", "当前进展待补充。"))
        elif idx == 10:
            existing.append(insight.get("business_model", "商业模式待补充。"))
        elif idx == 14:
            existing.append(insight.get("resource_needs", "资源诉求待补充。"))
        else:
            existing.append(_bp_pick_sentence(text, [title[:2], "AI", "客户", "需求", "项目"], "已有材料可作为本页初步线索，但仍需人工确认。"))
        pages.append(
            {
                "id": f"bpp_{project['id']}_{idx:02d}",
                "project_id": project["id"],
                "page_number": idx,
                "title": title,
                "question": answer,
                "core_judgement": f"{project.get('name', '该项目')} 需要在本页讲清：{answer}",
                "suggested_content": answer,
                "existing_materials": existing,
                "missing_materials": missing or ["本页已有初步材料，建议人工精修表达。"],
                "draft_copy": f"{project.get('name', '项目')}：{project.get('tagline') or insight.get('solution', '')}。当前阶段为 {project.get('stage', 'unknown')}，本页重点是{answer}",
                "likely_questions": [
                    "资源方会如何判断这部分是否真实？",
                    "是否有可脱敏的客户、数据、截图或访谈摘录作为证据？",
                ],
                "is_delivery_ready": False,
                "internal_notes": "",
                "created_at": now,
                "updated_at": now,
            }
        )
    return pages


def _generate_bp_gap_report(project: Dict[str, Any], pages: List[Dict[str, Any]]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for page in pages:
        for missing in page.get("missing_materials", []):
            missing_text = _ops_text(missing, max_len=500)
            if not missing_text or "已有初步材料" in missing_text:
                continue
            severity = "必须补" if page.get("page_number") in {6, 8, 10, 14} else "建议补"
            items.append(
                {
                    "gap_name": missing_text[:80],
                    "severity": severity,
                    "why_it_matters": "这会影响资源方是否愿意继续沟通和判断项目是否已经具备推进基础。",
                    "recommended_fix": missing_text,
                    "page_number": page.get("page_number", 0),
                    "page_title": page.get("title", ""),
                }
            )
    if not items:
        items.append(
            {
                "gap_name": "需要人工精修表达",
                "severity": "可后补",
                "why_it_matters": "当前材料已有初步结构，但对外沟通仍需要压缩重点和补证据。",
                "recommended_fix": "补充证据摘录、客户反馈、业务数据和资源诉求边界。",
                "page_number": 0,
                "page_title": "整体",
            }
        )
    return {
        "id": f"bpg_{project['id']}",
        "project_id": project["id"],
        "summary": "以下缺口会影响园区、投资人、技术方或合作方的初步判断。",
        "items": items,
        "updated_at": _now_ts(),
    }


def _generate_bp_assets_local(project: Dict[str, Any], materials: List[Dict[str, Any]]) -> Dict[str, Any]:
    insight = _generate_bp_insight(project, materials)
    text = _bp_materials_text(materials)
    insight["resource_readiness"] = _bp_resource_readiness(project, insight, text)
    insight["likely_questions"] = _bp_likely_questions(project, insight, text)
    insight["next_actions"] = _bp_next_actions(project, insight, text)
    pages = _generate_bp_pages(project, insight, materials)
    insight["bp_structure_preview"] = _bp_structure_preview(pages)
    gap_report = _generate_bp_gap_report(project, pages)
    insight["share_card"]["gaps"] = [item.get("gap_name", "") for item in gap_report.get("items", [])[:3]]
    return {"insight": insight, "pages": pages, "gap_report": gap_report}


def _bp_ai_fallback_reason(error: Exception) -> str:
    message = sanitize_text_strict(str(error), allow_empty=True, max_len=240).lower()
    if not message:
        return "ai_generation_failed"
    if "api key" in message or "未检测到 api key" in message:
        return "missing_api_key"
    if "401" in message or "403" in message or "unauthorized" in message:
        return "auth_failed"
    if "429" in message or "rate" in message or "quota" in message:
        return "rate_limited"
    if "timeout" in message or "timed out" in message:
        return "upstream_timeout"
    if "connect" in message or "connection" in message or "network" in message or "dns" in message:
        return "upstream_network"
    return "upstream_error"


def _merge_bp_ai_insight(ai_insight: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(fallback)
    text_fields = [
        ("problem", 800),
        ("solution", 800),
        ("business_model", 800),
        ("ai_relevance", 800),
        ("traction", 800),
        ("key_data", 800),
        ("resource_needs", 800),
        ("recommended_path", 240),
    ]
    for key, max_len in text_fields:
        value = sanitize_text_strict(ai_insight.get(key, ""), allow_empty=True, max_len=max_len)
        if value:
            merged[key] = value
    gaps = _bp_list(ai_insight.get("material_gaps", []), max_items=12, max_len=160)
    if gaps:
        merged["material_gaps"] = gaps
    try:
        score = int(ai_insight.get("readiness_score", merged.get("readiness_score", 0)) or 0)
        merged["readiness_score"] = max(20, min(95, score))
    except Exception:
        pass
    if isinstance(ai_insight.get("score_breakdown"), dict):
        score_breakdown = copy.deepcopy(merged.get("score_breakdown", {}))
        for key in ["clarity", "evidence", "product", "business_model", "ai_relevance", "team", "resource_ask", "material_completeness"]:
            try:
                score_breakdown[key] = max(0, min(100, int(ai_insight["score_breakdown"].get(key, score_breakdown.get(key, 0)) or 0)))
            except Exception:
                continue
        merged["score_breakdown"] = score_breakdown
    if isinstance(ai_insight.get("resource_readiness"), list):
        items: List[Dict[str, str]] = []
        for raw in ai_insight["resource_readiness"][:8]:
            if not isinstance(raw, dict):
                continue
            path = _ops_text(raw.get("path", ""), max_len=80)
            if not path:
                continue
            items.append(
                {
                    "path": path,
                    "level": _ops_choice(raw.get("level", "中"), {"高", "中", "低"}, "中", max_len=10),
                    "reason": _ops_text(raw.get("reason", ""), max_len=240),
                    "missing": _ops_text(raw.get("missing", ""), max_len=240),
                    "next_step": _ops_text(raw.get("next_step", raw.get("nextStep", "")), max_len=240),
                }
            )
        if items:
            merged["resource_readiness"] = items
    questions = _bp_list(ai_insight.get("likely_questions", ai_insight.get("likelyQuestions", [])), max_items=8, max_len=160)
    if questions:
        merged["likely_questions"] = questions
    next_actions = _bp_list(ai_insight.get("next_actions", ai_insight.get("nextActions", [])), max_items=5, max_len=180)
    if next_actions:
        merged["next_actions"] = next_actions
    merged["updated_at"] = _now_ts()
    return merged


def _merge_bp_ai_pages(ai_pages: List[Any], fallback_pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pages = [copy.deepcopy(item) for item in fallback_pages]
    by_number = {int(item.get("page_number", 0) or 0): item for item in pages}
    for raw_page in ai_pages:
        if not isinstance(raw_page, dict):
            continue
        try:
            page_number = int(raw_page.get("page_number", 0) or 0)
        except Exception:
            page_number = 0
        page = by_number.get(page_number)
        if not page:
            continue
        for key, max_len in [
            ("core_judgement", 800),
            ("suggested_content", 1000),
            ("draft_copy", 1600),
        ]:
            value = sanitize_text_strict(raw_page.get(key, ""), allow_empty=True, max_len=max_len)
            if value:
                page[key] = value
        for key in ["existing_materials", "missing_materials", "likely_questions"]:
            values = _bp_list(raw_page.get(key, []), max_items=8, max_len=200)
            if values:
                page[key] = values
        page["updated_at"] = _now_ts()
    return sorted(pages, key=lambda item: int(item.get("page_number", 0) or 0))


def _merge_bp_ai_gap_report(ai_gap_report: Dict[str, Any], fallback: Dict[str, Any], project_id: str) -> Dict[str, Any]:
    merged = copy.deepcopy(fallback)
    summary = sanitize_text_strict(ai_gap_report.get("summary", ""), allow_empty=True, max_len=800)
    if summary:
        merged["summary"] = summary
    items: List[Dict[str, Any]] = []
    raw_items = ai_gap_report.get("items", [])
    if isinstance(raw_items, list):
        for raw_item in raw_items[:20]:
            if not isinstance(raw_item, dict):
                continue
            gap_name = sanitize_text_strict(raw_item.get("gap_name", ""), allow_empty=True, max_len=160)
            recommended_fix = sanitize_text_strict(raw_item.get("recommended_fix", ""), allow_empty=True, max_len=500)
            if not gap_name and not recommended_fix:
                continue
            try:
                page_number = int(raw_item.get("page_number", 0) or 0)
            except Exception:
                page_number = 0
            items.append(
                {
                    "gap_name": gap_name or recommended_fix[:80],
                    "severity": sanitize_text_strict(raw_item.get("severity", "建议补"), allow_empty=True, max_len=40) or "建议补",
                    "why_it_matters": sanitize_text_strict(raw_item.get("why_it_matters", ""), allow_empty=True, max_len=500)
                    or "这会影响资源方是否愿意继续沟通。",
                    "recommended_fix": recommended_fix or gap_name,
                    "page_number": page_number,
                    "page_title": sanitize_text_strict(raw_item.get("page_title", ""), allow_empty=True, max_len=120),
                }
            )
    if items:
        merged["items"] = items
    merged["id"] = f"bpg_{project_id}"
    merged["project_id"] = project_id
    merged["updated_at"] = _now_ts()
    return merged


def generate_bp_assets_with_ai(project: Dict[str, Any], materials: List[Dict[str, Any]], fallback_assets: Dict[str, Any]) -> Dict[str, Any]:
    client = get_client()
    model = get_model_name()
    material_text = _bp_materials_text(materials)
    schema_hint = {
        "insight": {
            "problem": "120字以内",
            "solution": "120字以内",
            "business_model": "120字以内",
            "ai_relevance": "120字以内",
            "traction": "120字以内",
            "key_data": "120字以内",
            "resource_needs": "120字以内",
            "material_gaps": ["最多5条，每条60字以内"],
            "recommended_path": "80字以内",
            "readiness_score": 0,
            "score_breakdown": {
                "clarity": 0,
                "evidence": 0,
                "product": 0,
                "business_model": 0,
                "ai_relevance": 0,
                "team": 0,
                "resource_ask": 0,
                "material_completeness": 0,
            },
            "resource_readiness": [
                {"path": "园区 / 政策", "level": "高 / 中 / 低", "reason": "80字以内", "missing": "80字以内", "next_step": "80字以内"}
            ],
            "likely_questions": ["最多8条，每条60字以内"],
            "next_actions": ["最多3条，每条80字以内"],
        }
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是 OnePitch 的项目诊断与标准 BP 清单生成引擎。"
                "只输出 JSON，不要 markdown，不要解释。"
                "不要编造客户、收入、融资、资质或政策背书；材料没有出现时必须写成缺失材料。"
                "输出必须极简，避免长段落。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请基于项目资料生成项目理解草稿。"
                "本地系统会根据你的诊断结果生成14页标准BP清单，不需要你输出BP页面。\n"
                f"项目：{json.dumps(project, ensure_ascii=False)}\n"
                f"原始材料：\n{material_text[:4000]}\n\n"
                "输出必须符合这个 JSON 结构：\n"
                f"{json.dumps(schema_hint, ensure_ascii=False)}"
            ),
        },
    ]
    resp = create_chat_completion(client, model=model, temperature=0.2, messages=messages, max_tokens=900)
    parsed = extract_json_object((resp.choices[0].message.content or "{}").strip())
    insight = _merge_bp_ai_insight(parsed.get("insight", {}) if isinstance(parsed.get("insight", {}), dict) else {}, fallback_assets["insight"])
    text = _bp_materials_text(materials)
    if not insight.get("resource_readiness"):
        insight["resource_readiness"] = _bp_resource_readiness(project, insight, text)
    if not insight.get("likely_questions"):
        insight["likely_questions"] = _bp_likely_questions(project, insight, text)
    if not insight.get("next_actions"):
        insight["next_actions"] = _bp_next_actions(project, insight, text)
    pages = _generate_bp_pages(project, insight, materials)
    insight["bp_structure_preview"] = _bp_structure_preview(pages)
    gap_report = _generate_bp_gap_report(project, pages)
    share_card = insight.get("share_card", {}) if isinstance(insight.get("share_card", {}), dict) else {}
    insight["share_card"] = {
        "title": _ops_text(share_card.get("title", project.get("name", "")), max_len=160),
        "one_line": _ops_text(share_card.get("one_line", share_card.get("oneLine", project.get("tagline", insight.get("solution", "")))), max_len=240),
        "stage": _ops_text(share_card.get("stage", project.get("stage", "unknown")), max_len=60),
        "target_customer": _ops_text(share_card.get("target_customer", share_card.get("targetCustomer", project.get("target_customer", ""))), max_len=240) or "待补充",
        "resource_ask": _ops_text(share_card.get("resource_ask", share_card.get("resourceAsk", insight.get("resource_needs", ""))), max_len=240),
        "recommended_path": _ops_text(share_card.get("recommended_path", share_card.get("recommendedPath", insight.get("recommended_path", ""))), max_len=240),
        "highlights": _bp_list(share_card.get("highlights", [insight.get("solution", ""), insight.get("traction", ""), insight.get("ai_relevance", "")]), max_items=3, max_len=120),
        "gaps": [item.get("gap_name", "") for item in gap_report.get("items", [])[:3]],
    }
    project["readiness_score"] = int(insight.get("readiness_score", project.get("readiness_score", 0)) or 0)
    project["recommended_path"] = sanitize_text_strict(insight.get("recommended_path", project.get("recommended_path", "")), allow_empty=True, max_len=240)
    return {"insight": insight, "pages": pages, "gap_report": gap_report}


def _bp_public_project(project: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "id",
        "name",
        "founder_name",
        "tagline",
        "industry",
        "stage",
        "target_customer",
        "current_resource_need",
        "visibility",
        "share_card_requested",
        "readiness_score",
        "recommended_path",
        "submission_source",
        "user_visible_token",
        "created_at",
        "updated_at",
    ]
    return {key: copy.deepcopy(project.get(key)) for key in keys if key in project}


def _bp_public_page(page: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": page.get("id", ""),
        "project_id": page.get("project_id", ""),
        "page_number": page.get("page_number", 0),
        "title": page.get("title", ""),
        "question": page.get("question", ""),
        "missing_materials": copy.deepcopy(page.get("missing_materials", [])),
        "is_locked": True,
        "core_judgement": "",
        "suggested_content": "",
        "existing_materials": [],
        "draft_copy": "",
        "likely_questions": [],
        "created_at": page.get("created_at", ""),
        "updated_at": page.get("updated_at", ""),
    }


def _bp_public_service_request(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": item.get("id", ""),
        "project_id": item.get("project_id", ""),
        "service_type": item.get("service_type", ""),
        "user_message": item.get("user_message", ""),
        "urgent_problem": item.get("urgent_problem", ""),
        "status": item.get("status", ""),
        "created_at": item.get("created_at", ""),
    }


def _bp_bundle(state: Dict[str, Any], project: Dict[str, Any], *, public: bool) -> Dict[str, Any]:
    project_id = _ops_text(project.get("id", ""), max_len=64)
    raw_materials = [item for item in state.get("bp_raw_materials", []) if isinstance(item, dict) and item.get("project_id") == project_id]
    insight = next((item for item in state.get("bp_project_insights", []) if isinstance(item, dict) and item.get("project_id") == project_id), {})
    pages = sorted(
        [item for item in state.get("bp_pages", []) if isinstance(item, dict) and item.get("project_id") == project_id],
        key=lambda item: int(item.get("page_number", 0) or 0),
    )
    gap_report = next((item for item in state.get("bp_gap_reports", []) if isinstance(item, dict) and item.get("project_id") == project_id), {})
    service_requests = [item for item in state.get("bp_service_requests", []) if isinstance(item, dict) and item.get("project_id") == project_id]
    versions = [item for item in state.get("bp_versions", []) if isinstance(item, dict) and item.get("project_id") == project_id]
    next_actions = [item for item in state.get("bp_next_actions", []) if isinstance(item, dict) and item.get("project_id") == project_id]
    return {
        "project": _bp_public_project(project) if public else copy.deepcopy(project),
        "raw_materials": copy.deepcopy(raw_materials),
        "insight": copy.deepcopy(insight),
        "pages": [_bp_public_page(item) for item in pages] if public else copy.deepcopy(pages),
        "gap_report": copy.deepcopy(gap_report),
        "service_requests": [_bp_public_service_request(item) for item in service_requests] if public else copy.deepcopy(service_requests),
        "next_actions": [] if public else copy.deepcopy(next_actions),
        "versions": copy.deepcopy(versions),
        "used_ai": bool(project.get("ai_generation_used", False)),
        "ai_provider": sanitize_text_strict(project.get("ai_provider", ""), allow_empty=True, max_len=40),
        "fallback_reason": sanitize_text_strict(project.get("ai_fallback_reason", ""), allow_empty=True, max_len=80),
    }


def _regenerate_bp_assets(state: Dict[str, Any], project: Dict[str, Any], materials: List[Dict[str, Any]]) -> Dict[str, Any]:
    fallback_assets = _generate_bp_assets_local(project, materials)
    try:
        assets = generate_bp_assets_with_ai(project, materials, fallback_assets)
        project["ai_generation_used"] = True
        project["ai_provider"] = get_ai_provider()
        project["ai_fallback_reason"] = ""
    except Exception as exc:
        assets = fallback_assets
        project["ai_generation_used"] = False
        project["ai_provider"] = get_ai_provider()
        project["ai_fallback_reason"] = _bp_ai_fallback_reason(exc)
    insight = assets["insight"]
    pages = assets["pages"]
    gap_report = assets["gap_report"]
    project["updated_at"] = _now_ts()
    _replace_bp_project(state, project)
    project_id = project["id"]
    state["bp_project_insights"] = [item for item in state.get("bp_project_insights", []) if not (isinstance(item, dict) and item.get("project_id") == project_id)]
    state["bp_project_insights"].append(insight)
    state["bp_pages"] = [item for item in state.get("bp_pages", []) if not (isinstance(item, dict) and item.get("project_id") == project_id)]
    state["bp_pages"].extend(pages)
    state["bp_gap_reports"] = [item for item in state.get("bp_gap_reports", []) if not (isinstance(item, dict) and item.get("project_id") == project_id)]
    state["bp_gap_reports"].append(gap_report)
    return {"insight": insight, "pages": pages, "gap_report": gap_report}


def create_bp_diagnosis(payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    project = _bp_project_from_payload(payload)
    raw = _bp_raw_material(project["id"], {"raw_material": payload.get("raw_material", payload.get("rawMaterial", "")), "title": "首次提交材料"}, default_title="首次提交材料")
    state.setdefault("bp_projects", []).append(project)
    state.setdefault("bp_raw_materials", []).append(raw)
    _regenerate_bp_assets(state, project, [raw])
    state.setdefault("bp_versions", []).append(_bp_now_version(project["id"], "首次诊断", "创建项目诊断并生成项目理解草稿与 14 页 BP 清单预览。"))
    save_state(state)
    return _bp_bundle(state, project, public=True)


def get_bp_diagnosis(token: str) -> Dict[str, Any]:
    state = load_state()
    project = _find_bp_project_by_token(state, token)
    if not project:
        raise ServiceError(404, "not_found", "没有找到这份诊断报告。")
    return _bp_bundle(state, project, public=True)


def supplement_bp_diagnosis(token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    project = _find_bp_project_by_token(state, token)
    if not project:
        raise ServiceError(404, "not_found", "没有找到这份诊断报告。")
    raw = _bp_raw_material(project["id"], payload, default_title="补充材料")
    state.setdefault("bp_raw_materials", []).append(raw)
    materials = [item for item in state.get("bp_raw_materials", []) if isinstance(item, dict) and item.get("project_id") == project["id"]]
    _regenerate_bp_assets(state, project, materials)
    state.setdefault("bp_versions", []).append(_bp_now_version(project["id"], "补充材料并重新生成", "用户补充材料后重新生成诊断报告、BP 清单和缺口报告。"))
    save_state(state)
    return _bp_bundle(state, project, public=True)


def create_bp_service_request(token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state()
    project = _find_bp_project_by_token(state, token)
    if not project:
        raise ServiceError(404, "not_found", "没有找到这份诊断报告。")
    contact_name = _ops_text(payload.get("contact_name", payload.get("contactName", "")), max_len=120)
    contact_wechat = _ops_text(payload.get("contact_wechat", payload.get("contactWechat", "")), max_len=120)
    contact_phone = _ops_text(payload.get("contact_phone", payload.get("contactPhone", "")), max_len=80)
    contact_email = _ops_text(payload.get("contact_email", payload.get("contactEmail", "")), max_len=160)
    if not contact_name or not any([contact_wechat, contact_phone, contact_email]):
        raise ServiceError(400, "invalid_service_request", "请填写称呼和至少一种联系方式。")
    now = _now_ts()
    service_type = _ops_choice(payload.get("service_type", payload.get("serviceType", "project_diagnosis")), BP_SERVICE_TYPES, "project_diagnosis", max_len=40)
    service_request = {
        "id": _ops_id("bps"),
        "project_id": project["id"],
        "service_type": service_type,
        "contact_name": contact_name,
        "contact_wechat": contact_wechat,
        "contact_phone": contact_phone,
        "contact_email": contact_email,
        "contact_preference": _ops_text(payload.get("contact_preference", payload.get("contactPreference", "")), max_len=120),
        "urgent_problem": _ops_text(payload.get("urgent_problem", payload.get("urgentProblem", "")), max_len=1000),
        "budget_signal": _ops_choice(payload.get("budget_signal", payload.get("budgetSignal", "unknown")), {"unknown", "weak", "medium", "strong"}, "unknown", max_len=24),
        "user_message": _ops_text(payload.get("user_message", payload.get("userMessage", "")), max_len=2000),
        "authorized_material_review": bool(payload.get("authorized_material_review", payload.get("authorizedMaterialReview", False))),
        "status": "new",
        "internal_notes": "",
        "service_quote": "",
        "created_at": now,
        "updated_at": now,
    }
    next_action = {
        "id": _ops_id("bpa"),
        "project_id": project["id"],
        "action": f"联系 {contact_name}，确认服务诉求和下一步沟通方式。",
        "owner": "OnePitch",
        "due_date": "",
        "status": "open",
        "priority": "high",
        "created_at": now,
        "updated_at": now,
    }
    project["internal_status"] = "new_service_request"
    project["next_action"] = next_action["action"]
    project["updated_at"] = now
    _replace_bp_project(state, project)
    state.setdefault("bp_service_requests", []).append(service_request)
    state.setdefault("bp_next_actions", []).append(next_action)
    state.setdefault("bp_versions", []).append(_bp_now_version(project["id"], "提交服务申请", f"用户提交 {service_type} 服务申请。"))
    save_state(state)
    return {"service_request": _bp_public_service_request(service_request), "next_action": next_action}


def list_ops_bp_projects(user: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    projects = [item for item in state.get("bp_projects", []) if isinstance(item, dict)]
    projects = sorted(projects, key=lambda item: item.get("updated_at", ""), reverse=True)
    return {"projects": projects}


def get_ops_bp_project(user: Dict[str, Any], project_id: str) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    project = _find_bp_project_by_id(state, project_id)
    if not project:
        raise ServiceError(404, "not_found", "BP 项目不存在。")
    return _bp_bundle(state, project, public=False)


def update_ops_bp_project(user: Dict[str, Any], project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    project = _find_bp_project_by_id(state, project_id)
    if not project:
        raise ServiceError(404, "not_found", "BP 项目不存在。")
    for key, max_len in [
        ("internal_status", 40),
        ("priority", 24),
        ("budget_signal", 24),
        ("decision_power", 24),
        ("service_quote", 800),
        ("internal_notes", 2400),
        ("private_feedback", 2400),
        ("next_action", 800),
        ("next_action_at", 40),
    ]:
        if key not in payload:
            continue
        if key == "internal_status":
            project[key] = _ops_choice(payload.get(key), BP_INTERNAL_STATUSES, project.get(key, "submitted"), max_len=max_len)
        elif key == "priority":
            project[key] = _ops_choice(payload.get(key), BP_PRIORITIES, project.get(key, "medium"), max_len=max_len)
        elif key == "budget_signal":
            project[key] = _ops_choice(payload.get(key), {"unknown", "weak", "medium", "strong"}, project.get(key, "unknown"), max_len=max_len)
        else:
            project[key] = _ops_text(payload.get(key), max_len=max_len)
    project["updated_at"] = _now_ts()
    _replace_bp_project(state, project)
    save_state(state)
    return {"project": project}


def update_ops_bp_page(user: Dict[str, Any], page_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    pages = [item for item in state.get("bp_pages", []) if isinstance(item, dict)]
    idx = _ops_find_index(pages, page_id)
    if idx < 0:
        raise ServiceError(404, "not_found", "BP 页面不存在。")
    page = copy.deepcopy(pages[idx])
    for key in ["core_judgement", "suggested_content", "draft_copy", "internal_notes"]:
        if key in payload:
            page[key] = _ops_text(payload.get(key), max_len=4000)
    for key in ["existing_materials", "missing_materials", "likely_questions"]:
        if key in payload:
            page[key] = _ops_list(payload.get(key), max_items=12, max_len=600)
    if "is_delivery_ready" in payload:
        page["is_delivery_ready"] = bool(payload.get("is_delivery_ready"))
    page["updated_at"] = _now_ts()
    pages[idx] = page
    state["bp_pages"] = pages
    save_state(state)
    return {"page": page}


def get_ops_bp_followups(user: Dict[str, Any]) -> Dict[str, Any]:
    require_ops_admin(user)
    state = load_state()
    actions = [item for item in state.get("bp_next_actions", []) if isinstance(item, dict) and _ops_text(item.get("status", "open"), max_len=40) not in {"done", "closed", "archived"}]
    return {"next_actions": sorted(actions, key=lambda item: (item.get("due_date") or "9999-99-99", item.get("updated_at", "")))}
