import copy
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ai_service import build_update_input, get_last_structuring_meta, structure_project, structure_project_object
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

    return {
        "schema_version": int(store.get("schema_version", 2)),
        "users": [item for item in users if isinstance(item, dict)],
        "projects": _sort_projects(sanitized_projects),
        "events": events,
        "auth_challenges": auth_challenges,
        "auth_sessions": auth_sessions,
    }


def save_state(state: Dict[str, Any]) -> None:
    payload = {
        "schema_version": int(state.get("schema_version", 2)),
        "users": [item for item in state.get("users", []) if isinstance(item, dict)],
        "projects": _sort_projects([item for item in state.get("projects", []) if isinstance(item, dict)]),
        "events": [item for item in state.get("events", []) if isinstance(item, dict)],
        "auth_challenges": [item for item in state.get("auth_challenges", []) if isinstance(item, dict)],
        "auth_sessions": [item for item in state.get("auth_sessions", []) if isinstance(item, dict)],
    }
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
