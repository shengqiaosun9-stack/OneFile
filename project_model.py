import copy
import re
import uuid
from datetime import datetime, timedelta
from html import unescape
from typing import Any, Dict, List, Optional

from text_cleaning import (
    SAFE_TEXT_PATTERN,
    clean_list,
    clean_text,
    has_markup_contamination,
    is_timeline_leak_text,
    normalize_stage_metric_text,
    normalize_team_text,
    sanitize_text_strict,
)

EXPORT_KEYS = [
    "title",
    "tech_stack",
    "users",
    "model",
    "stage",
    "version_footprint",
    "summary",
]

SCHEMA_TEMPLATE: Dict[str, Any] = {
    "title": "",
    "desc": "",
    "tech_stack": [],
    "users": "",
    "use_cases": "",
    "problem_statement": "",
    "solution_approach": "",
    "model": "",
    "model_desc": "",
    "business_model_type": "UNKNOWN",
    "model_type": "UNKNOWN",
    "pricing_strategy": "",
    "form_type": "OTHER",
    "stage": "",
    "version_footprint": "",
    "latest_update": "",
    "summary": "",
    "owner_user_id": "",
    "entity_type": "claimed_project",
    "claim_status": "claimed",
    "visible_in_library": True,
    "claimed_by_user_id": "",
    "share": {},
    "updates": [],
    "current_state": "",
    "current_tension": "",
    "next_action": {},
    "system_confidence": 0.62,
    "decision_quality_score": 0.55,
    "last_intervention_effectiveness": "unknown",
    "progress_eval": {},
    "intervention": {},
    "ops_signals": {},
}

CN_NUM_MAP = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "俩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

TITLE_MAX_LEN = 42
TITLE_DEFAULT = "未命名项目"
TITLE_VERB_HINTS = [
    "是一个",
    "是一款",
    "我们做",
    "用于",
    "帮助",
    "通过",
    "提供",
    "实现",
    "支持",
    "面向",
]
VERSION_EVENT_FALLBACK = "版本记录已更新"
LATEST_UPDATE_FALLBACK = "暂无最新进展"

STAGE_VALUES = ["IDEA", "BUILDING", "MVP", "VALIDATION", "EARLY_REVENUE", "SCALING", "MATURE"]
FORM_TYPE_VALUES = ["AI_NATIVE_APP", "SAAS", "API_SERVICE", "AGENT", "MARKETPLACE", "DATA_TOOL", "INFRASTRUCTURE", "OTHER"]
MODEL_TYPE_VALUES = [
    "B2B_SUBSCRIPTION",
    "B2C_SUBSCRIPTION",
    "USAGE_BASED",
    "COMMISSION",
    "ONE_TIME",
    "OUTSOURCING",
    "ADS",
    "MARKETPLACE",
    "HYBRID",
    "UNKNOWN",
]
BUSINESS_MODEL_VALUES = ["TOB", "TOC", "B2B2C", "B2G", "C2C", "UNKNOWN"]
PRICING_STRATEGY_VALUES = ["FREEMIUM", "FREE_TRIAL", "ENTERPRISE_ONLY", "SELF_SERVE"]

STAGE_LABELS = {
    "IDEA": "构思阶段",
    "BUILDING": "开发中",
    "MVP": "MVP",
    "VALIDATION": "验证阶段",
    "EARLY_REVENUE": "早期收入",
    "SCALING": "规模增长",
    "MATURE": "成熟阶段",
}
FORM_TYPE_LABELS = {
    "AI_NATIVE_APP": "AI 原生应用",
    "SAAS": "SaaS",
    "API_SERVICE": "API 服务",
    "AGENT": "智能体",
    "MARKETPLACE": "交易市场",
    "DATA_TOOL": "数据工具",
    "INFRASTRUCTURE": "基础设施",
    "OTHER": "其他",
}
MODEL_TYPE_LABELS = {
    "B2B_SUBSCRIPTION": "B2B 订阅",
    "B2C_SUBSCRIPTION": "B2C 订阅",
    "USAGE_BASED": "按量计费",
    "COMMISSION": "交易抽佣",
    "ONE_TIME": "一次性付费",
    "OUTSOURCING": "外包/服务",
    "ADS": "广告变现",
    "MARKETPLACE": "平台撮合",
    "HYBRID": "混合模式",
    "UNKNOWN": "未知模式",
}
BUSINESS_MODEL_LABELS = {
    "TOB": "ToB",
    "TOC": "ToC",
    "B2B2C": "B2B2C",
    "B2G": "B2G",
    "C2C": "C2C",
    "UNKNOWN": "未知",
}

UPDATE_SOURCE_VALUES = {"create", "overlay_update", "direct_edit", "system_migration"}
UPDATE_KIND_VALUES = {"hypothesis", "action", "result", "note"}
NEXT_ACTION_STATUS_VALUES = {"open", "completed", "stale"}
PROGRESS_STATUS_VALUES = {"advancing", "stalled", "uncertain"}
INTERVENTION_TYPE_VALUES = {"none", "nudge", "stuck_replan"}
INTERVENTION_STATUS_VALUES = {"idle", "active", "resolved"}
INTERVENTION_EFFECTIVENESS_VALUES = {"unknown", "positive", "neutral", "negative"}

STAGE_STATE_LABELS = {
    "IDEA": "探索假设",
    "BUILDING": "构建验证",
    "MVP": "MVP验证",
    "VALIDATION": "证据沉淀",
    "EARLY_REVENUE": "收入爬坡",
    "SCALING": "规模增长",
    "MATURE": "稳定运营",
}


def get_now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def stage_label(stage: Any) -> str:
    key = str(stage or "").strip().upper()
    return STAGE_LABELS.get(key, STAGE_LABELS["BUILDING"])


def form_type_label(form_type: Any) -> str:
    key = str(form_type or "").strip().upper()
    return FORM_TYPE_LABELS.get(key, FORM_TYPE_LABELS["OTHER"])


def model_type_label(model_type: Any) -> str:
    key = str(model_type or "").strip().upper()
    return MODEL_TYPE_LABELS.get(key, MODEL_TYPE_LABELS["UNKNOWN"])


def business_model_label(business_model_type: Any) -> str:
    key = str(business_model_type or "").strip().upper()
    return BUSINESS_MODEL_LABELS.get(key, BUSINESS_MODEL_LABELS["UNKNOWN"])


def next_action_status_label(status: Any) -> str:
    key = sanitize_text_strict(status, allow_empty=True, max_len=20).lower()
    if key == "completed":
        return "已完成"
    if key == "stale":
        return "待重启"
    return "待推进"


def sanitize_version_event(value: Any, allow_fallback: bool = True) -> str:
    raw = unescape(str(value or ""))
    if "<" in raw or ">" in raw:
        return VERSION_EVENT_FALLBACK if allow_fallback else ""
    if has_markup_contamination(raw) or is_timeline_leak_text(raw):
        cleaned = sanitize_text_strict(raw, allow_empty=True, max_len=120)
    else:
        cleaned = sanitize_text_strict(raw, allow_empty=True, max_len=120)
    if has_markup_contamination(cleaned) or is_timeline_leak_text(cleaned):
        cleaned = ""
    if "<" in cleaned or ">" in cleaned:
        cleaned = ""
    cleaned = clean_text(cleaned, 120, aggressive=True)
    if not cleaned and allow_fallback:
        return VERSION_EVENT_FALLBACK
    return cleaned


def sanitize_version_date(value: Any) -> str:
    date = clean_text(value, 24, aggressive=True)
    if not date:
        date = get_now_str()
    return date


def _sanitize_owner_user_id(value: Any) -> str:
    return clean_text(value, 40, aggressive=True)


def normalize_share_state(value: Any, project_id: str) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    slug_seed = clean_text(raw.get("slug", f"onefile-{project_id}"), 60, aggressive=True) or f"onefile-{project_id}"
    is_public = bool(raw.get("is_public", False))
    published_at = sanitize_version_date(raw.get("published_at", "")) if is_public else ""
    last_shared_at = sanitize_version_date(raw.get("last_shared_at", "")) if is_public else ""
    return {
        "is_public": is_public,
        "slug": slug_seed,
        "published_at": published_at,
        "last_shared_at": last_shared_at,
    }


def normalize_input_meta(value: Any, merged_chars_fallback: int = 0) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    merged_chars = raw.get("merged_chars", merged_chars_fallback)
    try:
        merged_int = int(merged_chars)
    except Exception:
        merged_int = int(merged_chars_fallback or 0)
    if merged_int < 0:
        merged_int = 0
    return {
        "has_text": bool(raw.get("has_text", merged_int > 0)),
        "has_file": bool(raw.get("has_file", False)),
        "merged_chars": merged_int,
    }


def _clamp01(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(0.0, min(parsed, 1.0))


def _clamp_score(value: Any, default: int = 0) -> int:
    try:
        parsed = int(round(float(value)))
    except Exception:
        parsed = default
    return max(0, min(parsed, 100))


def _parse_dt(value: Any) -> Optional[datetime]:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=24)
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    return None


def _days_since(value: Any, now_value: str) -> Optional[int]:
    now_dt = _parse_dt(now_value)
    target_dt = _parse_dt(value)
    if not now_dt or not target_dt:
        return None
    return max((now_dt.date() - target_dt.date()).days, 0)


def _safe_reason_codes(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        code = sanitize_text_strict(item, allow_empty=True, max_len=40)
        if code:
            result.append(code)
    return result[:8]


def normalize_progress_eval_state(value: Any, fallback_timestamp: str) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    status = sanitize_text_strict(raw.get("status", ""), allow_empty=True, max_len=16).lower()
    if status not in PROGRESS_STATUS_VALUES:
        status = "uncertain"
    return {
        "status": status,
        "score": _clamp_score(raw.get("score", 50), default=50),
        "reason_codes": _safe_reason_codes(raw.get("reason_codes", [])),
        "evaluated_at": sanitize_version_date(raw.get("evaluated_at", fallback_timestamp)),
    }


def normalize_intervention_state(value: Any, fallback_timestamp: str) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    intervention_type = sanitize_text_strict(raw.get("type", ""), allow_empty=True, max_len=24).lower()
    if intervention_type not in INTERVENTION_TYPE_VALUES:
        intervention_type = "none"
    status = sanitize_text_strict(raw.get("status", ""), allow_empty=True, max_len=20).lower()
    if status not in INTERVENTION_STATUS_VALUES:
        status = "idle" if intervention_type == "none" else "active"
    return {
        "type": intervention_type,
        "message": sanitize_text_strict(raw.get("message", ""), allow_empty=True, max_len=180),
        "recommended_next_action": sanitize_text_strict(raw.get("recommended_next_action", ""), allow_empty=True, max_len=140),
        "triggered_at": sanitize_version_date(raw.get("triggered_at", fallback_timestamp)),
        "status": status,
    }


def normalize_ops_signals_state(value: Any, fallback_timestamp: str) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    return {
        "updates_7d": max(int(raw.get("updates_7d", 0) or 0), 0),
        "completed_actions_14d": max(int(raw.get("completed_actions_14d", 0) or 0), 0),
        "intervention_trigger_rate_14d": round(_clamp01(raw.get("intervention_trigger_rate_14d", 0.0), default=0.0), 2),
        "share_views_14d": max(int(raw.get("share_views_14d", 0) or 0), 0),
        "share_cta_clicks_14d": max(int(raw.get("share_cta_clicks_14d", 0) or 0), 0),
        "share_create_conversions_14d": max(int(raw.get("share_create_conversions_14d", 0) or 0), 0),
        "share_update_conversions_14d": max(int(raw.get("share_update_conversions_14d", 0) or 0), 0),
        "last_activity_at": sanitize_version_date(raw.get("last_activity_at", fallback_timestamp)),
    }


def derive_ops_signals(project_id: Any, events: Any, now_ts: str = "") -> Dict[str, Any]:
    pid = sanitize_text_strict(project_id, allow_empty=True, max_len=24)
    safe_now = sanitize_version_date(now_ts or get_now_str())
    now_dt = _parse_dt(safe_now) or datetime.now()
    if not pid or not isinstance(events, list):
        return normalize_ops_signals_state({}, safe_now)

    updates_7d = 0
    completed_actions_14d = 0
    intervention_triggered_14d = 0
    project_updates_14d = 0
    share_views_14d = 0
    share_cta_clicks_14d = 0
    share_create_conversions_14d = 0
    share_update_conversions_14d = 0
    last_activity_at = ""

    for event in events:
        if not isinstance(event, dict):
            continue
        event_pid = sanitize_text_strict(event.get("project_id", ""), allow_empty=True, max_len=24)
        if event_pid != pid:
            continue
        event_ts = sanitize_version_date(event.get("ts", ""))
        event_dt = _parse_dt(event_ts)
        if event_dt is None:
            continue
        if not last_activity_at or event_dt > (_parse_dt(last_activity_at) or datetime.min):
            last_activity_at = event_ts

        age_days = max((now_dt.date() - event_dt.date()).days, 0)
        event_type = sanitize_text_strict(event.get("event_type", ""), allow_empty=True, max_len=32).lower()
        if event_type == "project_updated":
            if age_days <= 7:
                updates_7d += 1
            if age_days <= 14:
                project_updates_14d += 1
        if event_type == "next_action_completed" and age_days <= 14:
            completed_actions_14d += 1
        if event_type == "intervention_triggered" and age_days <= 14:
            intervention_triggered_14d += 1
        if event_type == "share_viewed" and age_days <= 14:
            share_views_14d += 1
        if event_type == "share_cta_clicked" and age_days <= 14:
            share_cta_clicks_14d += 1
        if event_type == "share_conversion_attributed" and age_days <= 14:
            payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
            conversion_kind = sanitize_text_strict(payload.get("conversion_kind", ""), allow_empty=True, max_len=16).lower()
            if conversion_kind == "create":
                share_create_conversions_14d += 1
            elif conversion_kind == "update":
                share_update_conversions_14d += 1

    denom = max(project_updates_14d, 1)
    intervention_rate = intervention_triggered_14d / denom
    return normalize_ops_signals_state(
        {
            "updates_7d": updates_7d,
            "completed_actions_14d": completed_actions_14d,
            "intervention_trigger_rate_14d": intervention_rate,
            "share_views_14d": share_views_14d,
            "share_cta_clicks_14d": share_cta_clicks_14d,
            "share_create_conversions_14d": share_create_conversions_14d,
            "share_update_conversions_14d": share_update_conversions_14d,
            "last_activity_at": last_activity_at or safe_now,
        },
        safe_now,
    )


def infer_update_kind(text: Any) -> str:
    content = sanitize_text_strict(text, allow_empty=True, max_len=160).lower()
    if not content:
        return "note"
    result_hits = ["完成", "上线", "发布", "签约", "新增", "达成", "提升", "增长", "收到", "交付", "实现"]
    action_hits = ["执行", "推进", "开展", "接入", "改造", "优化", "测试", "联调", "部署", "修复"]
    hypothesis_hits = ["假设", "预计", "计划", "打算", "准备", "尝试", "可能", "待验证"]
    if any(hit in content for hit in result_hits):
        return "result"
    if any(hit in content for hit in action_hits):
        return "action"
    if any(hit in content for hit in hypothesis_hits):
        return "hypothesis"
    return "note"


def build_update_signals(content: Any, kind: str, next_action_text: Any = "") -> Dict[str, Any]:
    safe_content = sanitize_text_strict(content, allow_empty=True, max_len=180)
    normalized_kind = sanitize_text_strict(kind, allow_empty=True, max_len=16).lower()
    if normalized_kind not in UPDATE_KIND_VALUES:
        normalized_kind = infer_update_kind(safe_content)
    completion_signal = evaluate_next_action_completion(next_action_text, safe_content, normalized_kind)

    evidence = 0.38
    if normalized_kind == "result":
        evidence = 0.82
    elif normalized_kind == "action":
        evidence = 0.66
    elif normalized_kind == "hypothesis":
        evidence = 0.34
    elif normalized_kind == "note":
        evidence = 0.22
    if completion_signal:
        evidence = max(evidence, 0.84)

    has_metric = bool(re.search(r"\d", safe_content))
    if has_metric:
        evidence = min(1.0, evidence + 0.08)
    confused_pattern = any(token in safe_content for token in ["不知道", "随便", "先这样", "再说", "哈哈", "嗯嗯", "可能"])
    if confused_pattern:
        evidence = min(evidence, 0.26)

    action_tokens = _action_tokens(next_action_text)
    lower_text = safe_content.lower()
    alignment = 0.22
    if action_tokens:
        token_hits = sum(1 for token in action_tokens if token and token in lower_text)
        alignment = min(1.0, 0.2 + 0.18 * token_hits)
    if completion_signal:
        alignment = max(alignment, 0.75)
    if normalized_kind in {"note", "hypothesis"} and not completion_signal:
        alignment = min(alignment, 0.35)
    if confused_pattern:
        alignment = min(alignment, 0.22)
    alignment = _clamp01(alignment, default=0.22)
    return {
        "evidence_score": round(_clamp01(evidence, default=0.3), 2),
        "action_alignment": round(alignment, 2),
        "completion_signal": bool(completion_signal),
    }


def _normalize_update_signals(value: Any, content: Any, kind: str, next_action_text: Any = "") -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    generated = build_update_signals(content=content, kind=kind, next_action_text=next_action_text)
    return {
        "evidence_score": round(_clamp01(raw.get("evidence_score", generated["evidence_score"]), default=generated["evidence_score"]), 2),
        "action_alignment": round(_clamp01(raw.get("action_alignment", generated["action_alignment"]), default=generated["action_alignment"]), 2),
        "completion_signal": bool(raw.get("completion_signal", generated["completion_signal"])),
    }


def _build_evidence_snapshot(project: Dict[str, Any], safe_ts: str, recent_updates: List[Dict[str, Any]]) -> Dict[str, Any]:
    raw_ops = project.get("ops_signals", {})
    ops_missing = not isinstance(raw_ops, dict) or not raw_ops
    ops = normalize_ops_signals_state(raw_ops if isinstance(raw_ops, dict) else {}, safe_ts)

    fallback_updates_7d = 0
    fallback_completed_14d = 0
    fallback_last_activity = ""
    now_dt = _parse_dt(safe_ts) or datetime.now()
    for item in recent_updates:
        if not isinstance(item, dict):
            continue
        created_at = sanitize_version_date(item.get("created_at", ""))
        created_dt = _parse_dt(created_at)
        if created_dt is None:
            continue
        age_days = max((now_dt.date() - created_dt.date()).days, 0)
        if age_days <= 7:
            fallback_updates_7d += 1
        if age_days <= 14 and bool(item.get("completion_signal", False)):
            fallback_completed_14d += 1
        if not fallback_last_activity or created_dt > (_parse_dt(fallback_last_activity) or datetime.min):
            fallback_last_activity = created_at

    if ops_missing:
        updates_7d = fallback_updates_7d
        completed_actions_14d = fallback_completed_14d
        last_activity_at = fallback_last_activity or sanitize_version_date(project.get("updated_at", safe_ts))
    else:
        updates_7d = max(int(ops.get("updates_7d", 0) or 0), 0)
        completed_actions_14d = max(int(ops.get("completed_actions_14d", 0) or 0), 0)
        last_activity_at = sanitize_version_date(ops.get("last_activity_at", project.get("updated_at", safe_ts)))

    intervention_rate_14d = _clamp01(ops.get("intervention_trigger_rate_14d", 0.0), default=0.0)
    share_views_14d = max(int(ops.get("share_views_14d", 0) or 0), 0)
    return {
        "ops_missing": ops_missing,
        "updates_7d": updates_7d,
        "completed_actions_14d": completed_actions_14d,
        "last_activity_at": last_activity_at,
        "days_since_last_activity": _days_since(last_activity_at, safe_ts),
        "intervention_trigger_rate_14d": round(intervention_rate_14d, 2),
        "share_views_14d": share_views_14d,
    }


def evaluate_progress_state(project: Dict[str, Any], timestamp: str, window: int = 5) -> Dict[str, Any]:
    safe_ts = sanitize_version_date(timestamp or project.get("updated_at", get_now_str()))
    updates = project.get("updates", [])
    if not isinstance(updates, list):
        updates = []
    recent: List[Dict[str, Any]] = [item for item in updates if isinstance(item, dict)][: max(window, 1)]

    next_action = project.get("next_action", {}) if isinstance(project.get("next_action", {}), dict) else {}
    next_action_text = sanitize_text_strict(next_action.get("text", ""), allow_empty=True, max_len=120)
    next_action_status = sanitize_text_strict(next_action.get("status", ""), allow_empty=True, max_len=16).lower()
    evidence_snapshot = _build_evidence_snapshot(project, safe_ts, recent)
    updates_7d = evidence_snapshot["updates_7d"]
    completed_14d = evidence_snapshot["completed_actions_14d"]
    days_since_last = evidence_snapshot["days_since_last_activity"]

    evidence_values: List[float] = []
    alignment_values: List[float] = []
    completion_hits = 0
    note_like = 0
    confused_hits = 0
    reason_codes: List[str] = []

    for item in recent:
        content = sanitize_text_strict(item.get("content", ""), allow_empty=True, max_len=180)
        kind = sanitize_text_strict(item.get("kind", ""), allow_empty=True, max_len=16).lower()
        if kind not in UPDATE_KIND_VALUES:
            kind = infer_update_kind(content)
        signals = _normalize_update_signals(item, content=content, kind=kind, next_action_text=next_action_text)

        evidence = signals["evidence_score"]
        alignment = signals["action_alignment"]
        completion = bool(signals["completion_signal"])

        evidence_values.append(evidence)
        alignment_values.append(alignment)

        if completion:
            completion_hits += 1
        if kind in {"note", "hypothesis"}:
            note_like += 1
        if any(token in content for token in ["不知道", "随便", "先这样", "再说", "哈哈", "嗯嗯", "可能"]):
            confused_hits += 1

    total = max(len(recent), 1)
    evidence_avg = (sum(evidence_values) / len(evidence_values)) if evidence_values else 0.0
    alignment_avg = (sum(alignment_values) / len(alignment_values)) if alignment_values else 0.0
    note_ratio = note_like / total

    # Primary evidence contribution (~70%)
    updates_component = (min(updates_7d, 4) / 4.0) * 20
    completion_component = (min(completed_14d, 3) / 3.0) * 34
    if days_since_last is None:
        activity_component = 6
    elif days_since_last <= 1:
        activity_component = 16
    elif days_since_last <= 3:
        activity_component = 12
    elif days_since_last <= 6:
        activity_component = 8
    elif days_since_last <= 10:
        activity_component = 3
    else:
        activity_component = 0
    primary_score = updates_component + completion_component + activity_component

    # Secondary inferred contribution (~30%)
    secondary_score = (
        evidence_avg * 12
        + alignment_avg * 10
        + (min(completion_hits, 2) / 2.0) * 8
    )

    score = primary_score + secondary_score
    if completed_14d > 0 and updates_7d > 0:
        score += 8
        if days_since_last is not None and days_since_last <= 3:
            score += 4
    if next_action_status == "stale":
        score -= 6
        reason_codes.append("ev_next_action_stale")
    if note_ratio >= 0.6:
        score -= 4
        reason_codes.append("inf_low_evidence_updates")
    if confused_hits >= max(1, total // 2):
        score -= 5
        reason_codes.append("inf_confused_inputs")

    if updates_7d == 0:
        reason_codes.append("ev_updates_zero")
    elif updates_7d <= 1:
        reason_codes.append("ev_updates_low")
    else:
        reason_codes.append("ev_updates_positive")

    if completed_14d == 0:
        reason_codes.append("ev_completion_zero")
    else:
        reason_codes.append("ev_completion_positive")

    if days_since_last is not None:
        if days_since_last >= 7:
            reason_codes.append("ev_inactive_7d")
        elif days_since_last >= 3:
            reason_codes.append("ev_inactive_3d")
        else:
            reason_codes.append("ev_recent_activity")

    if updates_7d >= 2 and completed_14d == 0:
        reason_codes.append("ev_update_without_completion")
    if completion_hits > 0:
        reason_codes.append("inf_completion_signal")
    if evidence_snapshot["ops_missing"]:
        reason_codes.append("ev_ops_fallback_updates")

    score_int = _clamp_score(score, default=38)
    if score_int >= 66 and completed_14d > 0:
        status = "advancing"
    elif score_int < 45 or (updates_7d >= 2 and completed_14d == 0) or (days_since_last is not None and days_since_last >= 7):
        status = "stalled"
    else:
        status = "uncertain"
    if status == "stalled" and "inf_confused_inputs" in reason_codes and completed_14d > 0:
        status = "uncertain"
    if status == "advancing":
        reason_codes.append("ev_progress_advancing")
    elif status == "stalled":
        reason_codes.append("ev_progress_stalled")

    confidence = 0.46
    if not evidence_snapshot["ops_missing"]:
        confidence += 0.20
    if updates_7d > 0:
        confidence += 0.10
    if completed_14d > 0:
        confidence += 0.12
    if days_since_last is not None:
        if days_since_last <= 3:
            confidence += 0.08
        elif days_since_last >= 7:
            confidence -= 0.08
    if note_ratio > 0.7:
        confidence -= 0.04
    if confused_hits >= max(1, total // 2):
        confidence -= 0.03
    if total >= 3:
        confidence += 0.05
    confidence = round(_clamp01(confidence, default=0.55), 2)

    return {
        "progress_eval": {
            "status": status,
            "score": score_int,
            "reason_codes": sorted(set(reason_codes)),
            "evaluated_at": safe_ts,
        },
        "system_confidence": confidence,
    }


def _compress_next_action_text(text: Any, conservative: bool) -> str:
    safe = sanitize_text_strict(text, allow_empty=True, max_len=140)
    if not safe:
        safe = "完成一个可验证动作并记录结果证据。"
    if not conservative:
        return safe
    while safe.startswith("48小时内完成："):
        safe = sanitize_text_strict(safe[len("48小时内完成：") :], allow_empty=True, max_len=140)
    safe = safe.replace("；并记录1条可验证结果。", "").strip()
    head = re.split(r"[。；;]", safe)[0].strip()
    if not head:
        head = safe
    compact = sanitize_text_strict(head, allow_empty=True, max_len=60)
    return f"48小时内完成：{compact}；并记录1条可验证结果。"


def derive_intervention_state(project: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
    safe_ts = sanitize_version_date(timestamp or project.get("updated_at", get_now_str()))
    progress = normalize_progress_eval_state(project.get("progress_eval", {}), safe_ts)
    previous = normalize_intervention_state(project.get("intervention", {}), safe_ts)
    next_action = project.get("next_action", {}) if isinstance(project.get("next_action", {}), dict) else {}
    updates = project.get("updates", [])
    if not isinstance(updates, list):
        updates = []
    recent_updates = [item for item in updates if isinstance(item, dict)][:5]
    evidence_snapshot = _build_evidence_snapshot(project, safe_ts, recent_updates)

    score = _clamp_score(progress.get("score", 50), default=50)
    status = sanitize_text_strict(progress.get("status", ""), allow_empty=True, max_len=16).lower()
    reason_codes = set(_safe_reason_codes(progress.get("reason_codes", [])))
    next_action_status = sanitize_text_strict(next_action.get("status", ""), allow_empty=True, max_len=16).lower()
    has_open_action = next_action_status in {"open", "stale"}
    updates_7d = evidence_snapshot["updates_7d"]
    completed_14d = evidence_snapshot["completed_actions_14d"]
    days_since_last = evidence_snapshot["days_since_last_activity"]
    intervention_rate = evidence_snapshot["intervention_trigger_rate_14d"]

    pattern_inactive = has_open_action and days_since_last is not None and days_since_last >= 7
    pattern_updates_without_completion = has_open_action and updates_7d >= 2 and completed_14d == 0
    pattern_repeat_trigger = has_open_action and intervention_rate >= 0.6 and updates_7d >= 1
    pattern_low_evidence = has_open_action and updates_7d >= 1 and completed_14d == 0 and (
        "inf_low_evidence_updates" in reason_codes
        or "inf_confused_inputs" in reason_codes
        or "ev_update_without_completion" in reason_codes
    )
    pattern_recovered = completed_14d > 0 and status == "advancing" and score >= 65

    if pattern_inactive or pattern_updates_without_completion or pattern_repeat_trigger:
        base_action = sanitize_text_strict(next_action.get("text", ""), allow_empty=True, max_len=140)
        recommended = _compress_next_action_text(base_action, conservative=True)
        if pattern_inactive:
            message = "超过7天未出现有效推进，请先完成一个48小时内可验证动作。"
        elif pattern_repeat_trigger:
            message = "近期多次触发介入仍缺少完成证据，请将动作拆小并在48小时内拿到结果。"
        else:
            message = "近期有更新但没有完成证据，请先完成当前动作并记录结果。"
        triggered_at = previous.get("triggered_at", safe_ts) if previous.get("status") == "active" else safe_ts
        return {
            "type": "stuck_replan",
            "message": message,
            "recommended_next_action": recommended,
            "triggered_at": triggered_at,
            "status": "active",
        }

    if pattern_low_evidence or (has_open_action and status in {"uncertain", "stalled"} and score < 60 and updates_7d > 0):
        base_action = sanitize_text_strict(next_action.get("text", ""), allow_empty=True, max_len=140)
        recommended = _compress_next_action_text(base_action, conservative=True)
        message = "最近更新偏记录性，请补充一条可验证结果或明确完成信号。"
        if "inf_confused_inputs" in reason_codes:
            message = "最近输入较模糊，请先定义一个可执行且可验证的具体动作。"
        triggered_at = previous.get("triggered_at", safe_ts) if previous.get("status") == "active" else safe_ts
        return {
            "type": "nudge",
            "message": message,
            "recommended_next_action": recommended,
            "triggered_at": triggered_at,
            "status": "active",
        }

    if previous.get("status") == "active":
        if pattern_recovered or not has_open_action:
            previous["status"] = "resolved"
            previous["message"] = "最近进展已恢复，继续按下一动作推进。"
        else:
            previous["status"] = "idle"
            previous["type"] = "none"
            previous["message"] = ""
            previous["recommended_next_action"] = ""
    elif previous.get("type") == "none":
        previous["status"] = "idle"
    return previous


def assess_intervention_effectiveness(
    previous_intervention: Dict[str, Any],
    previous_progress: Dict[str, Any],
    current_progress: Dict[str, Any],
    latest_update_signals: Optional[Dict[str, Any]],
) -> str:
    prev_status = sanitize_text_strict(previous_intervention.get("status", ""), allow_empty=True, max_len=20).lower()
    prev_type = sanitize_text_strict(previous_intervention.get("type", ""), allow_empty=True, max_len=24).lower()
    if prev_status != "active" or prev_type == "none":
        return "unknown"

    previous_score = _clamp_score(previous_progress.get("score", 50), default=50)
    current_score = _clamp_score(current_progress.get("score", 50), default=50)
    score_delta = current_score - previous_score
    completion_signal = bool((latest_update_signals or {}).get("completion_signal", False))
    evidence_score = _clamp01((latest_update_signals or {}).get("evidence_score", 0.0))
    current_status = sanitize_text_strict(current_progress.get("status", ""), allow_empty=True, max_len=16).lower()

    if completion_signal or score_delta >= 12 or (current_status == "advancing" and evidence_score >= 0.6):
        return "positive"
    if current_status == "stalled" and score_delta <= 2 and evidence_score < 0.45:
        return "negative"
    return "neutral"


def update_decision_quality_score(previous_score: Any, effectiveness: str, current_progress_score: Any) -> float:
    prev = _clamp01(previous_score, default=0.55)
    current_score = _clamp_score(current_progress_score, default=50)
    effect = sanitize_text_strict(effectiveness, allow_empty=True, max_len=16).lower()
    target_map = {
        "positive": 0.82,
        "neutral": 0.60,
        "negative": 0.35,
        "unknown": max(0.38, min(0.88, 0.36 + current_score / 130)),
    }
    target = target_map.get(effect, target_map["unknown"])
    blended = prev * 0.72 + target * 0.28
    return round(_clamp01(blended, default=0.55), 2)


def _sanitize_next_action_status(value: Any) -> str:
    status = sanitize_text_strict(value, allow_empty=True, max_len=20).lower()
    if status in NEXT_ACTION_STATUS_VALUES:
        return status
    return "open"


def infer_current_state(stage: Any) -> str:
    normalized_stage = normalize_stage_value(stage)
    return STAGE_STATE_LABELS.get(normalized_stage, STAGE_STATE_LABELS["BUILDING"])


def infer_current_tension(stage: Any, latest_update: Any) -> str:
    normalized_stage = normalize_stage_value(stage)
    latest = sanitize_latest_update(latest_update, fallback="")
    defaults = {
        "IDEA": "尚未形成可验证的用户价值证据",
        "BUILDING": "原型尚未获得稳定的用户反馈",
        "MVP": "MVP已成型，但核心价值尚未被持续验证",
        "VALIDATION": "有验证动作，但缺少可复用的结果证据",
        "EARLY_REVENUE": "已有收入信号，但转化与复购还不稳定",
        "SCALING": "增长正在发生，但扩张质量仍需验证",
        "MATURE": "业务趋于稳定，仍需持续识别新增长点",
    }
    if latest and ("卡住" in latest or "阻塞" in latest or "风险" in latest or "不稳定" in latest):
        return sanitize_text_strict(latest, allow_empty=True, max_len=90)
    return defaults.get(normalized_stage, defaults["BUILDING"])


def suggest_next_action_text(stage: Any, latest_update: Any, current_tension: Any, conservative: bool = False) -> str:
    normalized_stage = normalize_stage_value(stage)
    latest = sanitize_text_strict(latest_update, allow_empty=True, max_len=120)
    tension = sanitize_text_strict(current_tension, allow_empty=True, max_len=120)
    if "客户" in latest or "签约" in latest or "试点" in latest:
        return _compress_next_action_text("将新增客户转化为稳定复购，并记录一条可复用的签约路径。", conservative)
    if "上线" in latest or "发布" in latest:
        return _compress_next_action_text("跟踪上线后7天核心指标，并产出一条基于数据的优化动作。", conservative)
    if "营收" in latest or "收入" in latest or "mrr" in latest.lower():
        return _compress_next_action_text("拆解收入来源并执行一次提效实验，验证可复制的增长动作。", conservative)
    if normalized_stage in {"IDEA", "BUILDING"}:
        return _compress_next_action_text("在7天内完成一次真实用户验证，并记录关键反馈结论。", conservative)
    if normalized_stage in {"MVP", "VALIDATION"}:
        return _compress_next_action_text("完成1-2个目标用户场景的闭环验证，沉淀可量化结果。", conservative)
    if normalized_stage == "EARLY_REVENUE":
        return _compress_next_action_text("围绕转化或复购执行一次改进实验，并记录前后数据变化。", conservative)
    if normalized_stage in {"SCALING", "MATURE"}:
        return _compress_next_action_text("围绕当前增长瓶颈执行本周行动，并输出结果复盘。", conservative)
    if tension:
        return _compress_next_action_text(f"针对当前张力推进：{tension}", conservative)
    return _compress_next_action_text("明确下一步可验证动作，并在本周内完成一次反馈闭环。", conservative)


def normalize_next_action_state(value: Any, stage: Any, latest_update: Any) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    text = sanitize_text_strict(raw.get("text", ""), allow_empty=True, max_len=120)
    generated_at = sanitize_version_date(raw.get("generated_at", ""))
    status = _sanitize_next_action_status(raw.get("status", "open"))
    completed_at = sanitize_version_date(raw.get("completed_at", "")) if status == "completed" else ""
    confidence_raw = raw.get("confidence", 0.62)
    try:
        confidence = float(confidence_raw)
    except Exception:
        confidence = 0.62
    confidence = max(0.0, min(confidence, 1.0))
    if not text:
        text = suggest_next_action_text(stage, latest_update, "")
    return {
        "text": text,
        "status": status,
        "generated_at": generated_at or get_now_str(),
        "completed_at": completed_at,
        "confidence": round(confidence, 2),
    }


def _action_tokens(text: str) -> List[str]:
    safe = sanitize_text_strict(text, allow_empty=True, max_len=120).lower()
    safe = re.sub(r"[，。；;,.!?！？\s]+", " ", safe).strip()
    tokens = [tok for tok in safe.split(" ") if len(tok) >= 2]
    if not tokens and safe:
        tokens = [safe]
    return tokens[:8]


def evaluate_next_action_completion(next_action_text: Any, update_text: Any, update_kind: str) -> bool:
    action_text = sanitize_text_strict(next_action_text, allow_empty=True, max_len=120)
    update = sanitize_text_strict(update_text, allow_empty=True, max_len=160)
    if not action_text or not update:
        return False
    update_lower = update.lower()
    if "已完成下一步" in update or "完成下一动作" in update or "动作已完成" in update:
        return True
    if "未完成" in update or "还没" in update or "进行中" in update or "继续" in update:
        return False
    completion_keywords = ["完成", "已", "上线", "发布", "达成", "签约", "交付", "验证通过", "落地"]
    has_completion_signal = any(k in update for k in completion_keywords) or update_kind == "result"
    if not has_completion_signal:
        return False

    action_tokens = _action_tokens(action_text)
    if any(tok and tok in update_lower for tok in action_tokens):
        return True

    semantic_pairs = [
        ("上线", ["上线", "发布", "可用", "正式"]),
        ("客户", ["客户", "签约", "试点"]),
        ("收入", ["营收", "收入", "mrr", "回款", "收费"]),
        ("验证", ["验证", "测试", "试点"]),
        ("转化", ["转化", "付费", "复购"]),
    ]
    for needle, haystack in semantic_pairs:
        if needle in action_text and any(hit in update_lower for hit in haystack):
            return True
    return False


def evolve_action_loop(project: Dict[str, Any], latest_update: Any, timestamp: str = "") -> Dict[str, Any]:
    evolved = copy.deepcopy(project)
    ts = sanitize_version_date(timestamp or evolved.get("updated_at", get_now_str()))
    stage_value = normalize_stage_value(evolved.get("stage", ""))
    update_kind = infer_update_kind(latest_update)
    previous_progress = normalize_progress_eval_state(evolved.get("progress_eval", {}), ts)
    previous_intervention = normalize_intervention_state(evolved.get("intervention", {}), ts)
    previous_quality = _clamp01(evolved.get("decision_quality_score", 0.55), default=0.55)
    previous_confidence = _clamp01(evolved.get("system_confidence", 0.62), default=0.62)
    conservative_mode = previous_quality < 0.45 or previous_confidence < 0.5

    current_tension = sanitize_text_strict(evolved.get("current_tension", ""), allow_empty=True, max_len=120)
    current_state = sanitize_text_strict(evolved.get("current_state", ""), allow_empty=True, max_len=40) or infer_current_state(stage_value)
    next_action = normalize_next_action_state(evolved.get("next_action", {}), stage_value, latest_update)
    newest_update_signals = build_update_signals(latest_update, update_kind, next_action.get("text", ""))

    action_completed = False
    if next_action.get("status") == "open":
        action_completed = newest_update_signals["completion_signal"] or evaluate_next_action_completion(
            next_action.get("text", ""),
            latest_update,
            update_kind,
        )

    if action_completed:
        next_action["status"] = "completed"
        next_action["completed_at"] = ts
        current_state = f"{infer_current_state(stage_value)} · 已完成上一动作"
        base_tension = infer_current_tension(stage_value, latest_update)
        current_tension = sanitize_text_strict(base_tension, allow_empty=True, max_len=120)
        next_action = normalize_next_action_state(
            {
                "text": suggest_next_action_text(stage_value, latest_update, current_tension, conservative=conservative_mode),
                "status": "open",
                "generated_at": ts,
                "confidence": 0.66 if not conservative_mode else 0.58,
            },
            stage_value,
            latest_update,
        )
    else:
        if next_action.get("status") == "completed":
            # 防止异常状态回流
            next_action["status"] = "open"
            next_action["completed_at"] = ""
        if update_kind in {"note", "hypothesis"} and next_action.get("status") == "open":
            next_action["status"] = "stale"
        if next_action.get("status") == "stale":
            next_action["text"] = suggest_next_action_text(stage_value, latest_update, current_tension, conservative=True)
            next_action["generated_at"] = ts
            next_action["confidence"] = 0.52
        if not current_tension:
            current_tension = infer_current_tension(stage_value, latest_update)

    if next_action.get("status") in {"open", "stale"}:
        current_tension = sanitize_text_strict(
            current_tension or f"待解决：{next_action.get('text', '')}",
            allow_empty=True,
            max_len=120,
        )
    if not current_tension:
        current_tension = infer_current_tension(stage_value, latest_update)

    evolved["current_state"] = current_state
    evolved["current_tension"] = current_tension
    evolved["next_action"] = next_action
    updates = evolved.get("updates", [])
    if isinstance(updates, list) and updates:
        normalized_updates: List[Dict[str, Any]] = []
        for idx, item in enumerate(updates):
            if not isinstance(item, dict):
                continue
            item_copy = copy.deepcopy(item)
            content = sanitize_text_strict(item_copy.get("content", ""), allow_empty=True, max_len=180)
            item_kind = sanitize_text_strict(item_copy.get("kind", ""), allow_empty=True, max_len=16).lower()
            if item_kind not in UPDATE_KIND_VALUES:
                item_kind = infer_update_kind(content)
            signal = _normalize_update_signals(
                {
                    "evidence_score": item_copy.get("evidence_score"),
                    "action_alignment": item_copy.get("action_alignment"),
                    "completion_signal": item_copy.get("completion_signal"),
                },
                content=content,
                kind=item_kind,
                next_action_text=next_action.get("text", ""),
            )
            item_copy["kind"] = item_kind
            item_copy["evidence_score"] = signal["evidence_score"]
            item_copy["action_alignment"] = signal["action_alignment"]
            item_copy["completion_signal"] = signal["completion_signal"]
            normalized_updates.append(item_copy)
            if idx == 0:
                newest_update_signals = signal
        evolved["updates"] = normalized_updates

    evaluation = evaluate_progress_state(evolved, ts, window=5)
    evolved["progress_eval"] = evaluation["progress_eval"]
    evolved["system_confidence"] = evaluation["system_confidence"]

    intervention = derive_intervention_state(evolved, ts)
    if intervention.get("status") == "active" and intervention.get("recommended_next_action"):
        next_action["text"] = _compress_next_action_text(intervention["recommended_next_action"], conservative=True)
        next_action["status"] = "open"
        next_action["generated_at"] = ts
        next_action["confidence"] = 0.54 if intervention.get("type") == "stuck_replan" else 0.60
        evolved["next_action"] = next_action
    evolved["intervention"] = intervention

    current_progress = normalize_progress_eval_state(evolved.get("progress_eval", {}), ts)
    effectiveness = assess_intervention_effectiveness(
        previous_intervention=previous_intervention,
        previous_progress=previous_progress,
        current_progress=current_progress,
        latest_update_signals=newest_update_signals,
    )
    evolved["last_intervention_effectiveness"] = effectiveness
    evolved["decision_quality_score"] = update_decision_quality_score(
        previous_score=previous_quality,
        effectiveness=effectiveness,
        current_progress_score=current_progress.get("score", 50),
    )
    evolved["loop_has_open_action"] = next_action.get("status") in {"open", "stale"}
    return evolved


def ensure_action_loop_defaults(project: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(project)
    stage_value = normalize_stage_value(normalized.get("stage", ""))
    latest = sanitize_latest_update(
        normalized.get("latest_update", normalized.get("version_footprint", "")),
        fallback=normalized.get("version_footprint", ""),
    )
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quality = _clamp01(normalized.get("decision_quality_score", 0.55), default=0.55)
    confidence = _clamp01(normalized.get("system_confidence", 0.62), default=0.62)
    conservative_mode = quality < 0.45 or confidence < 0.5
    state = sanitize_text_strict(normalized.get("current_state", ""), allow_empty=True, max_len=40) or infer_current_state(stage_value)
    tension = sanitize_text_strict(normalized.get("current_tension", ""), allow_empty=True, max_len=120)
    next_action = normalize_next_action_state(normalized.get("next_action", {}), stage_value, latest)
    if conservative_mode:
        next_action["text"] = _compress_next_action_text(next_action.get("text", ""), conservative=True)
    if next_action.get("status") in {"open", "stale"} and not tension:
        tension = infer_current_tension(stage_value, latest)
    if not tension:
        tension = infer_current_tension(stage_value, latest)
    updates = normalized.get("updates", [])
    if isinstance(updates, list):
        normalized_updates: List[Dict[str, Any]] = []
        for item in updates:
            if not isinstance(item, dict):
                continue
            item_copy = copy.deepcopy(item)
            content = sanitize_text_strict(item_copy.get("content", ""), allow_empty=True, max_len=180)
            item_kind = sanitize_text_strict(item_copy.get("kind", ""), allow_empty=True, max_len=16).lower()
            if item_kind not in UPDATE_KIND_VALUES:
                item_kind = infer_update_kind(content)
            signal = _normalize_update_signals(
                {
                    "evidence_score": item_copy.get("evidence_score"),
                    "action_alignment": item_copy.get("action_alignment"),
                    "completion_signal": item_copy.get("completion_signal"),
                },
                content=content,
                kind=item_kind,
                next_action_text=next_action.get("text", ""),
            )
            item_copy["kind"] = item_kind
            item_copy["evidence_score"] = signal["evidence_score"]
            item_copy["action_alignment"] = signal["action_alignment"]
            item_copy["completion_signal"] = signal["completion_signal"]
            normalized_updates.append(item_copy)
        normalized["updates"] = normalized_updates
    normalized["current_state"] = state
    normalized["current_tension"] = tension
    normalized["next_action"] = next_action
    evaluation = evaluate_progress_state(normalized, ts, window=5)
    normalized["progress_eval"] = evaluation["progress_eval"]
    normalized["system_confidence"] = evaluation["system_confidence"]
    effect = sanitize_text_strict(normalized.get("last_intervention_effectiveness", "unknown"), allow_empty=True, max_len=16).lower()
    if effect not in INTERVENTION_EFFECTIVENESS_VALUES:
        effect = "unknown"
    normalized["last_intervention_effectiveness"] = effect
    normalized["decision_quality_score"] = update_decision_quality_score(
        previous_score=normalized.get("decision_quality_score", 0.55),
        effectiveness=effect,
        current_progress_score=normalized["progress_eval"].get("score", 50),
    )
    intervention = derive_intervention_state(normalized, ts)
    if intervention.get("status") == "active" and intervention.get("recommended_next_action"):
        next_action["text"] = _compress_next_action_text(intervention["recommended_next_action"], conservative=True)
        next_action["status"] = "open"
        normalized["next_action"] = next_action
    normalized["intervention"] = intervention
    normalized["loop_has_open_action"] = next_action.get("status") in {"open", "stale"}
    return normalized


def build_update_entry(
    project_id: str,
    author_user_id: str,
    content: Any,
    source: str,
    created_at: str = "",
    input_meta: Optional[Dict[str, Any]] = None,
    kind: str = "",
    next_action_text: Any = "",
    signals: Optional[Dict[str, Any]] = None,
    entry_id: Any = "",
) -> Dict[str, Any]:
    safe_content = sanitize_version_event(content, allow_fallback=True)
    safe_created_at = sanitize_version_date(created_at or get_now_str())
    safe_source = source if source in UPDATE_SOURCE_VALUES else "overlay_update"
    safe_kind = sanitize_text_strict(kind, allow_empty=True, max_len=16).lower()
    if safe_kind not in UPDATE_KIND_VALUES:
        safe_kind = infer_update_kind(safe_content)
    safe_signals = _normalize_update_signals(
        signals or {},
        content=safe_content,
        kind=safe_kind,
        next_action_text=next_action_text,
    )
    merged_chars = len(safe_content)
    safe_entry_id = clean_text(entry_id, 20, aggressive=True)
    if not safe_entry_id:
        safe_entry_id = clean_text(str(uuid.uuid4())[:12], 20, aggressive=True)
    return {
        "id": safe_entry_id,
        "project_id": clean_text(project_id, 20, aggressive=True),
        "author_user_id": _sanitize_owner_user_id(author_user_id),
        "content": safe_content,
        "created_at": safe_created_at,
        "source": safe_source,
        "kind": safe_kind,
        "evidence_score": safe_signals["evidence_score"],
        "action_alignment": safe_signals["action_alignment"],
        "completion_signal": safe_signals["completion_signal"],
        "input_meta": normalize_input_meta(input_meta or {}, merged_chars_fallback=merged_chars),
    }


def _update_sort_key(item: Dict[str, Any]) -> str:
    return sanitize_version_date(item.get("created_at", ""))


def normalize_updates_state(project: Dict[str, Any], project_id: str, owner_user_id: str) -> List[Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
    next_action_text = ""
    if isinstance(project.get("next_action", {}), dict):
        next_action_text = sanitize_text_strict(project.get("next_action", {}).get("text", ""), allow_empty=True, max_len=120)
    raw_updates = project.get("updates", [])
    if isinstance(raw_updates, list):
        for item in raw_updates:
            if not isinstance(item, dict):
                continue
            entry = build_update_entry(
                project_id=project_id,
                author_user_id=item.get("author_user_id", owner_user_id),
                content=item.get("content", item.get("event", item.get("update_text", ""))),
                source=clean_text(item.get("source", "overlay_update"), 24, aggressive=True),
                created_at=item.get("created_at", item.get("date", item.get("timestamp", get_now_str()))),
                input_meta=item.get("input_meta", {}),
                kind=item.get("kind", ""),
                next_action_text=next_action_text,
                entry_id=item.get("id", ""),
                signals={
                    "evidence_score": item.get("evidence_score"),
                    "action_alignment": item.get("action_alignment"),
                    "completion_signal": item.get("completion_signal"),
                },
            )
            updates.append(entry)

    if not updates:
        # migrate from historical version fields
        versions = project.get("versions", [])
        if isinstance(versions, list):
            for item in versions:
                if not isinstance(item, dict):
                    continue
                event = sanitize_version_event(
                    item.get("event", item.get("update_text", item.get("version_text", ""))),
                    allow_fallback=False,
                )
                if not event:
                    continue
                updates.append(
                    build_update_entry(
                        project_id=project_id,
                        author_user_id=owner_user_id,
                        content=event,
                        source="system_migration",
                        created_at=item.get("date", item.get("timestamp", get_now_str())),
                        input_meta={"has_text": True, "has_file": False, "merged_chars": len(event)},
                        kind="result",
                        next_action_text=next_action_text,
                    )
                )

    if not updates:
        fallback = sanitize_latest_update(
            project.get("latest_update", project.get("version_footprint", "")),
            fallback=LATEST_UPDATE_FALLBACK,
        )
        updates = [
            build_update_entry(
                project_id=project_id,
                author_user_id=owner_user_id,
                content=fallback,
                source="system_migration",
                created_at=project.get("updated_at", get_now_str()),
                input_meta={"has_text": True, "has_file": False, "merged_chars": len(fallback)},
                kind="note",
                next_action_text=next_action_text,
            )
        ]

    updates = sorted(updates, key=_update_sort_key, reverse=True)
    return updates[:50]


def normalize_stage_value(value: Any) -> str:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=36)
    if not raw:
        return "BUILDING"
    upper = raw.upper().strip()
    if upper in STAGE_VALUES:
        return upper
    lowered = raw.lower()
    if any(x in lowered for x in ["idea", "想法", "构思"]):
        return "IDEA"
    if any(x in lowered for x in ["mvp", "最小可行"]):
        return "MVP"
    if any(x in lowered for x in ["验证", "内测", "公测", "beta", "试点", "pilot", "poc"]):
        return "VALIDATION"
    if any(x in lowered for x in ["融资", "seed", "pre-a", "pre a", "募资"]):
        return "VALIDATION"
    if any(x in lowered for x in ["收入", "营收", "mrr", "gmv", "付费", "变现"]):
        return "EARLY_REVENUE"
    if any(x in lowered for x in ["scaling", "scale", "增长", "扩张"]):
        return "SCALING"
    if any(x in lowered for x in ["mature", "成熟", "稳定运营", "龙头"]):
        return "MATURE"
    if any(x in lowered for x in ["上线", "launch", "production", "ga"]):
        return "EARLY_REVENUE"
    if any(x in lowered for x in ["开发", "搭建", "building", "研发"]):
        return "BUILDING"
    return "BUILDING"


def normalize_form_type(value: Any, context: str = "") -> str:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=36)
    upper = raw.upper().strip()
    if upper in FORM_TYPE_VALUES:
        return upper
    probe = f"{raw} {context}".lower()
    if any(x in probe for x in ["agent", "智能体", "助手", "copilot"]):
        return "AGENT"
    if any(x in probe for x in ["api", "sdk", "接口", "openapi"]):
        return "API_SERVICE"
    if any(x in probe for x in ["marketplace", "交易市场", "撮合", "market"]):
        return "MARKETPLACE"
    if any(x in probe for x in ["数据", "data", "bi", "分析", "dashboard"]):
        return "DATA_TOOL"
    if any(x in probe for x in ["infra", "基础设施", "中间件", "cloud native", "platform"]):
        return "INFRASTRUCTURE"
    if any(x in probe for x in ["saas"]):
        return "SAAS"
    if any(x in probe for x in ["ai", "llm", "生成式"]):
        return "AI_NATIVE_APP"
    return "OTHER"


def normalize_model_type(value: Any, model_desc: str = "") -> str:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=36)
    upper = raw.upper().strip()
    if upper in MODEL_TYPE_VALUES:
        return upper
    probe = f"{raw} {model_desc}".lower()
    if "hybrid" in probe or "混合" in probe or "+" in model_desc:
        return "HYBRID"
    if any(x in probe for x in ["b2b", "企业订阅", "企业版订阅"]):
        return "B2B_SUBSCRIPTION"
    if any(x in probe for x in ["b2c", "个人订阅", "会员"]):
        return "B2C_SUBSCRIPTION"
    if any(x in probe for x in ["按量", "usage", "token", "调用量"]):
        return "USAGE_BASED"
    if any(x in probe for x in ["抽佣", "佣金", "commission"]):
        return "COMMISSION"
    if any(x in probe for x in ["买断", "一次性", "one-time", "one time"]):
        return "ONE_TIME"
    if any(x in probe for x in ["外包", "定制", "服务费", "outsourcing", "consulting"]):
        return "OUTSOURCING"
    if any(x in probe for x in ["广告", "ads", "ad "]):
        return "ADS"
    if any(x in probe for x in ["marketplace", "平台撮合", "交易平台"]):
        return "MARKETPLACE"
    if any(x in probe for x in ["订阅", "subscription"]):
        return "B2B_SUBSCRIPTION"
    return "UNKNOWN"


def normalize_business_model_type(value: Any, context: str = "") -> str:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=36)
    upper = raw.upper().strip()
    if upper in BUSINESS_MODEL_VALUES:
        return upper

    probe = f"{raw} {context}".lower()
    if "b2b2c" in probe:
        return "B2B2C"
    if any(x in probe for x in ["b2g", "政府", "政务", "公共部门", "事业单位"]):
        return "B2G"
    if any(x in probe for x in ["c2c", "个人对个人", "创作者对创作者"]):
        return "C2C"
    if any(x in probe for x in ["tob", "b2b", "企业", "公司", "机构", "商家", "团队"]):
        return "TOB"
    if any(x in probe for x in ["toc", "b2c", "消费者", "个人用户", "c端", "用户端"]):
        return "TOC"
    return "UNKNOWN"


def normalize_pricing_strategy(value: Any, model_desc: str = "") -> str:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=24).upper().strip()
    if raw in PRICING_STRATEGY_VALUES:
        return raw
    probe = f"{value} {model_desc}".lower()
    if any(x in probe for x in ["freemium", "免费增值"]):
        return "FREEMIUM"
    if any(x in probe for x in ["free trial", "试用", "试用期"]):
        return "FREE_TRIAL"
    if any(x in probe for x in ["enterprise", "企业版", "仅企业"]):
        return "ENTERPRISE_ONLY"
    if any(x in probe for x in ["self-serve", "自助", "在线开通"]):
        return "SELF_SERVE"
    return ""


def sanitize_latest_update(value: Any, fallback: str = "") -> str:
    text = sanitize_text_strict(value, allow_empty=True, max_len=110)
    if not text:
        text = sanitize_text_strict(fallback, allow_empty=True, max_len=110)
    if has_markup_contamination(text) or is_timeline_leak_text(text) or "<" in text or ">" in text:
        text = ""
    text = clean_text(text, 110, aggressive=True)
    return text or LATEST_UPDATE_FALLBACK


def _sanitize_title_candidate(value: Any) -> str:
    text = sanitize_text_strict(value, allow_empty=True, max_len=TITLE_MAX_LEN)
    if not text:
        return ""
    text = clean_text(text, TITLE_MAX_LEN, aggressive=True)
    text = re.sub(r"^[\"'“”‘’《》\[\]()（）\s]+|[\"'“”‘’《》\[\]()（）\s]+$", "", text).strip()
    return text


def validate_title_candidate(title: Any) -> bool:
    text = _sanitize_title_candidate(title)
    if not text:
        return False
    if has_markup_contamination(text) or is_timeline_leak_text(text):
        return False
    if len(text) > TITLE_MAX_LEN:
        return False
    if re.search(r"[。！？!?；;，,]", text) and len(text) > 14:
        return False
    lowered = text.lower()
    if any(token in lowered for token in ["\n", "```", "<", ">", "class=", "timeline-"]):
        return False
    if any(hint in text for hint in TITLE_VERB_HINTS):
        return False
    return True


def extract_title_from_text(raw_text: Any) -> str:
    raw = unescape(str(raw_text or ""))
    if not raw.strip():
        return ""
    compact = raw.replace("\r\n", "\n")
    patterns = [
        r"我们(?:项目)?叫\s*[：: ]?\s*([^\n。；;,，]{1,30})",
        r"项目名称(?:是|叫)\s*[：: ]?\s*([^\n。；;,，]{1,30})",
        r"我们是\s*([^\n。；;,，]{1,30})",
        r"([A-Za-z0-9\u4e00-\u9fff·\-\s]{2,24})\s*是一个",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = _sanitize_title_candidate(match.group(1))
        if validate_title_candidate(candidate):
            return candidate
    first_line = sanitize_text_strict(compact.split("\n")[0] if compact.split("\n") else "", allow_empty=True, max_len=TITLE_MAX_LEN)
    first_line = _sanitize_title_candidate(first_line)
    if validate_title_candidate(first_line):
        return first_line
    return ""


def resolve_title(user_title: Any, raw_input: Any, ai_title: Any, default: str = TITLE_DEFAULT) -> str:
    manual = _sanitize_title_candidate(user_title)
    if validate_title_candidate(manual):
        return manual

    rule_based = extract_title_from_text(raw_input)
    if validate_title_candidate(rule_based):
        return rule_based

    ai_based = _sanitize_title_candidate(ai_title)
    if validate_title_candidate(ai_based):
        return ai_based

    fallback = _sanitize_title_candidate(default)
    if fallback:
        return fallback
    if str(default) == "":
        return ""
    fallback = TITLE_DEFAULT
    return fallback


def detect_rename_signal(update_text: Any) -> str:
    text = sanitize_text_strict(update_text, allow_empty=True, max_len=280)
    if not text:
        return ""
    patterns = [
        r"我们(?:项目)?改名为\s*([^\n。；;,，]{1,30})",
        r"项目(?:现在|目前)?叫\s*([^\n。；;,，]{1,30})",
        r"(?:更名为|改名成)\s*([^\n。；;,，]{1,30})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = _sanitize_title_candidate(match.group(1))
        if validate_title_candidate(candidate):
            return candidate
    return ""


def sanitize_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    clean = dict(SCHEMA_TEMPLATE)

    resolved = _sanitize_title_candidate(data.get("title", ""))
    clean["title"] = resolved if validate_title_candidate(resolved) else TITLE_DEFAULT
    clean["desc"] = sanitize_text_strict(data.get("desc", ""), allow_empty=True, max_len=4000)
    clean["tech_stack"] = clean_list(data.get("tech_stack", []), max_items=4)
    clean["users"] = clean_text(data.get("users", "待补充"), max_len=44) or "待补充"
    clean["use_cases"] = sanitize_text_strict(data.get("use_cases", ""), allow_empty=True, max_len=120)
    clean["problem_statement"] = sanitize_text_strict(data.get("problem_statement", ""), allow_empty=True, max_len=180)
    clean["solution_approach"] = sanitize_text_strict(data.get("solution_approach", ""), allow_empty=True, max_len=180)
    model_desc = clean_text(data.get("model_desc", data.get("model", "待补充")), max_len=50) or "待补充"
    clean["model"] = model_desc
    clean["model_desc"] = model_desc
    stage_source = data.get("stage", data.get("status_tag", ""))
    clean["stage"] = normalize_stage_value(stage_source)
    context_for_form = " ".join(
        [
            clean["title"],
            model_desc,
            clean.get("users", ""),
            " ".join(clean.get("tech_stack", [])),
            clean_text(data.get("summary", ""), max_len=80),
            clean_text(data.get("shape", ""), max_len=40),
        ]
    )
    clean["form_type"] = normalize_form_type(data.get("form_type", data.get("shape", "")), context=context_for_form)
    clean["business_model_type"] = normalize_business_model_type(
        data.get("business_model_type", data.get("business_model", "")),
        context=f"{clean.get('users', '')} {clean.get('use_cases', '')} {clean.get('summary', '')}",
    )
    clean["model_type"] = normalize_model_type(data.get("model_type", ""), model_desc=model_desc)
    clean["pricing_strategy"] = normalize_pricing_strategy(data.get("pricing_strategy", ""), model_desc=model_desc)
    latest_from_input = sanitize_latest_update(
        data.get("latest_update", data.get("version_footprint", "")),
        fallback="",
    )
    clean["version_footprint"] = sanitize_version_event(
        data.get("version_footprint", latest_from_input or "版本记录已更新"),
        allow_fallback=True,
    )
    clean["summary"] = sanitize_text_strict(data.get("summary", "暂无亮点摘要"), allow_empty=False, max_len=78)
    clean["latest_update"] = sanitize_latest_update(
        data.get("latest_update", clean["version_footprint"]),
        fallback=clean["version_footprint"],
    )
    if not clean["problem_statement"] and clean["desc"]:
        clean["problem_statement"] = sanitize_text_strict(clean["desc"], allow_empty=True, max_len=120)
    if not clean["solution_approach"] and clean["summary"]:
        clean["solution_approach"] = sanitize_text_strict(clean["summary"], allow_empty=True, max_len=120)
    if not clean["use_cases"] and clean["users"]:
        clean["use_cases"] = f"{clean['users']}的典型使用场景待补充"
    team_text = normalize_team_text(data.get("team_text", data.get("team_size", "")))
    stage_metric = normalize_stage_metric_text(data.get("stage_metric", data.get("stage_progress", "")))
    if team_text:
        clean["team_text"] = team_text
    if stage_metric:
        clean["stage_metric"] = stage_metric
    clean["current_state"] = sanitize_text_strict(data.get("current_state", ""), allow_empty=True, max_len=40)
    clean["current_tension"] = sanitize_text_strict(data.get("current_tension", ""), allow_empty=True, max_len=120)
    clean["next_action"] = normalize_next_action_state(
        data.get("next_action", {}),
        clean.get("stage", ""),
        clean.get("latest_update", clean.get("version_footprint", "")),
    )
    clean["system_confidence"] = round(_clamp01(data.get("system_confidence", 0.62), default=0.62), 2)
    clean["decision_quality_score"] = round(_clamp01(data.get("decision_quality_score", 0.55), default=0.55), 2)
    effectiveness = sanitize_text_strict(data.get("last_intervention_effectiveness", "unknown"), allow_empty=True, max_len=16).lower()
    if effectiveness not in INTERVENTION_EFFECTIVENESS_VALUES:
        effectiveness = "unknown"
    clean["last_intervention_effectiveness"] = effectiveness
    clean["progress_eval"] = normalize_progress_eval_state(
        data.get("progress_eval", {}),
        fallback_timestamp=data.get("updated_at", get_now_str()),
    )
    clean["intervention"] = normalize_intervention_state(
        data.get("intervention", {}),
        fallback_timestamp=data.get("updated_at", get_now_str()),
    )
    clean["ops_signals"] = normalize_ops_signals_state(
        data.get("ops_signals", {}),
        fallback_timestamp=data.get("updated_at", get_now_str()),
    )

    return clean


def infer_status_tag(stage: str) -> str:
    normalized = normalize_stage_value(stage)
    if normalized == "MVP":
        return "MVP 已上线"
    if normalized == "VALIDATION":
        return "验证中"
    if normalized == "EARLY_REVENUE":
        return "已上线 / 早期收入"
    if normalized == "SCALING":
        return "规模增长"
    if normalized == "MATURE":
        return "成熟阶段"
    if normalized == "IDEA":
        return "构思阶段"
    return "开发中"


def infer_metrics(schema: Dict[str, Any]) -> Dict[str, str]:
    m = schema.get("model_desc", schema.get("model", ""))
    stg = normalize_stage_value(schema.get("stage", ""))
    sig = "订阅收入验证中" if ("订阅" in m or "付费" in m) else "产品价值验证中"
    prog = "规模化推进" if stg in ("SCALING", "MATURE") else ("收入验证" if stg == "EARLY_REVENUE" else ("小范围验证" if stg == "VALIDATION" else "方向打磨"))
    team_hint = normalize_team_text(schema.get("team_text", schema.get("team_size", "")))
    progress_hint = normalize_stage_metric_text(schema.get("stage_metric", schema.get("stage_progress", "")))
    return {
        "team_size": team_hint or "核心团队：1人",
        "progress": progress_hint or f"当前阶段：{prog}",
        "business_signal": sig,
    }


def build_footprints(version_footprint: str) -> List[Dict[str, str]]:
    parts = [
        sanitize_text_strict(x, allow_empty=True, max_len=42)
        for x in re.split(r"[；;。\n]", str(version_footprint or ""))
        if sanitize_text_strict(x, allow_empty=True, max_len=42)
    ]
    if not parts:
        parts = ["v1.0 完成首版结构定义"]
    lines = parts[:3]
    today = get_now_str()
    out: List[Dict[str, str]] = []
    for i, item in enumerate(lines):
        out.append({"date": today if i == 0 else "-", "note": item})
    return out


def to_ui_project(schema: Dict[str, Any], generated: bool) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4())[:8],
        "status_tag": infer_status_tag(schema.get("stage", "")),
        "updated_at": get_now_str(),
        "latest_update": sanitize_latest_update(
            schema.get("latest_update", schema.get("version_footprint", "")),
            fallback=schema.get("version_footprint", ""),
        ),
        "metrics": infer_metrics(schema),
        "generated": generated,
        "stage_label": stage_label(schema.get("stage", "")),
        "form_type_label": form_type_label(schema.get("form_type", "")),
        "business_model_type_label": business_model_label(schema.get("business_model_type", "")),
        "model_type_label": model_type_label(schema.get("model_type", "")),
        **schema,
    }


def get_export_payload(project: Dict[str, Any]) -> Dict[str, Any]:
    return {k: project.get(k) for k in EXPORT_KEYS}


def get_status_theme(status: str) -> str:
    if "融资中" in status:
        return "amber"
    if "规模增长" in status or "成熟阶段" in status:
        return "green"
    if "已上线" in status or "MVP" in status or "验证中" in status:
        return "blue"
    if "构思阶段" in status:
        return "purple"
    return "slate"


def infer_shape(schema: Dict[str, Any]) -> str:
    return form_type_label(schema.get("form_type", "OTHER"))


def build_versions_from_schema(schema: Dict[str, Any]) -> List[Dict[str, str]]:
    date = get_now_str()
    event = sanitize_version_event(
        schema.get("latest_update", schema.get("version_footprint", "初始版本")),
        allow_fallback=True,
    )
    return [{"event": event, "date": date}]


def build_generated_timeline(schema: Dict[str, Any]) -> List[Dict[str, str]]:
    today = datetime.now()
    version_chunks = [
        sanitize_text_strict(x, allow_empty=True, max_len=42)
        for x in re.split(r"[；;。\n]", str(schema.get("version_footprint", "")))
        if sanitize_text_strict(x, allow_empty=True, max_len=42)
    ]
    primary_note = version_chunks[0] if version_chunks else "完成结构化项目档案创建"
    return [
        {
            "title": "v1.0.0 - AI 结构化项目档案创建",
            "date": today.strftime("%Y-%m-%d"),
            "desc": primary_note,
            "current": True,
        },
        {
            "title": "v0.9.0 - 项目首次归档",
            "date": (today - timedelta(days=18)).strftime("%Y-%m-%d"),
            "desc": "已完成核心字段整理并建立统一表达。",
            "current": False,
        },
    ]


def normalize_project(project: Dict[str, Any]) -> Dict[str, Any]:
    schema = sanitize_schema(project)
    ui = to_ui_project(schema, generated=bool(project.get("generated", False)))
    ui["id"] = clean_text(project.get("id", ui["id"]), 16)
    ui["updated_at"] = clean_text(project.get("updated_at", ui["updated_at"]), 24)
    ui["status_tag"] = clean_text(project.get("status_tag", ui["status_tag"]), 28)
    ui["status_theme"] = clean_text(project.get("status_theme", get_status_theme(ui["status_tag"])), 16)
    ui["form_type"] = normalize_form_type(project.get("form_type", schema.get("form_type", "")), context=" ".join([schema.get("title", ""), schema.get("summary", ""), schema.get("model_desc", "")]))
    ui["shape"] = clean_text(project.get("shape", infer_shape({"form_type": ui["form_type"]})), 28)
    ui["form_type_label"] = form_type_label(ui["form_type"])
    ui["business_model_type"] = normalize_business_model_type(
        project.get("business_model_type", schema.get("business_model_type", "")),
        context=f"{schema.get('users', '')} {schema.get('summary', '')}",
    )
    ui["business_model_type_label"] = business_model_label(ui["business_model_type"])
    ui["model_type"] = normalize_model_type(project.get("model_type", schema.get("model_type", "")), model_desc=schema.get("model_desc", schema.get("model", "")))
    ui["model_type_label"] = model_type_label(ui["model_type"])
    ui["pricing_strategy"] = normalize_pricing_strategy(project.get("pricing_strategy", schema.get("pricing_strategy", "")), model_desc=schema.get("model_desc", ""))
    ui["model_desc"] = clean_text(project.get("model_desc", schema.get("model_desc", schema.get("model", ""))), 50) or "待补充"
    ui["model"] = ui["model_desc"]
    ui["team_text"] = clean_text(project.get("team_text", ui["metrics"]["team_size"]), 28)
    ui["stage_metric"] = clean_text(project.get("stage_metric", ui["metrics"]["progress"]), 44)
    ui["share_slug"] = clean_text(project.get("share_slug", f"onefile-{ui['id']}"), 40)
    ui["summary"] = sanitize_text_strict(project.get("summary", ui["summary"]), allow_empty=False, max_len=78)
    ui["owner_user_id"] = _sanitize_owner_user_id(project.get("owner_user_id", ""))
    entity_type = sanitize_text_strict(project.get("entity_type", ""), allow_empty=True, max_len=24).lower()
    if entity_type not in {"temporary_card", "claimed_project"}:
        entity_type = "claimed_project"
    claim_status = sanitize_text_strict(project.get("claim_status", ""), allow_empty=True, max_len=24).lower()
    if claim_status not in {"unclaimed", "claimed"}:
        claim_status = "claimed" if entity_type == "claimed_project" else "unclaimed"
    ui["entity_type"] = entity_type
    ui["claim_status"] = claim_status
    ui["visible_in_library"] = bool(project.get("visible_in_library", entity_type != "temporary_card"))
    ui["claimed_by_user_id"] = _sanitize_owner_user_id(project.get("claimed_by_user_id", ui["owner_user_id"]))
    updates = normalize_updates_state(project, project_id=ui["id"], owner_user_id=ui["owner_user_id"])
    ui["updates"] = updates
    ui["share"] = normalize_share_state(project.get("share", {}), ui["id"])
    ui["share_slug"] = ui["share"]["slug"]

    latest_update_entry = updates[0]
    latest_event = sanitize_version_event(latest_update_entry.get("content", ""), allow_fallback=True)
    latest_date = sanitize_version_date(latest_update_entry.get("created_at", get_now_str()))
    ui["versions"] = [{"event": latest_event, "date": latest_date}]
    ui["version_footprint"] = latest_event
    ui["latest_update"] = sanitize_latest_update(
        project.get("latest_update", latest_event),
        fallback=latest_event,
    )
    ui["stage"] = normalize_stage_value(ui.get("stage", ""))
    ui["stage_label"] = stage_label(ui["stage"])
    ui["status_tag"] = infer_status_tag(ui["stage"])
    ui["status_theme"] = get_status_theme(ui["status_tag"])
    ui = ensure_action_loop_defaults(ui)
    return ui


def sanitize_versions_for_render(project: Dict[str, Any]) -> List[Dict[str, str]]:
    cleaned_versions: List[Dict[str, str]] = []
    versions = project.get("versions", [])
    if not isinstance(versions, list):
        versions = []

    for item in versions:
        if not isinstance(item, dict):
            continue
        safe_text = sanitize_version_event(
            item.get("event", item.get("update_text", item.get("version_text", ""))),
            allow_fallback=False,
        )
        safe_date = sanitize_version_date(item.get("date", item.get("timestamp", get_now_str())))
        if not safe_text or not SAFE_TEXT_PATTERN.match(safe_text):
            continue
        cleaned_versions.append({"event": safe_text, "date": safe_date})

    if not cleaned_versions:
        fallback = sanitize_version_event(project.get("version_footprint", ""), allow_fallback=True)
        fallback_date = sanitize_version_date(project.get("updated_at", get_now_str()))
        cleaned_versions = [{"event": fallback, "date": fallback_date}]

    return cleaned_versions[:1]


def prepare_project_for_render(project: Dict[str, Any]) -> Dict[str, Any]:
    render_project = normalize_project(project)
    render_versions = sanitize_versions_for_render(render_project)
    render_project["versions"] = render_versions
    render_project["version_footprint"] = render_versions[0]["event"]
    render_project["latest_update"] = sanitize_latest_update(
        render_project.get("latest_update", render_versions[0]["event"]),
        fallback=render_versions[0]["event"],
    )
    return render_project


def hard_scrub_project_for_state(project: Dict[str, Any]) -> Dict[str, Any]:
    scrubbed = normalize_project(project)
    scrubbed_versions = sanitize_versions_for_render(scrubbed)
    scrubbed["versions"] = scrubbed_versions
    scrubbed["version_footprint"] = scrubbed_versions[0]["event"]
    scrubbed["latest_update"] = sanitize_latest_update(
        scrubbed.get("latest_update", scrubbed_versions[0]["event"]),
        fallback=scrubbed_versions[0]["event"],
    )
    scrubbed["summary"] = sanitize_text_strict(scrubbed.get("summary", ""), allow_empty=False, max_len=78)
    return scrubbed


def migrate_project_for_hygiene(project: Dict[str, Any]) -> Dict[str, Any]:
    migrated = copy.deepcopy(project)
    cleaned_versions: List[Dict[str, str]] = []
    versions = migrated.get("versions")
    if isinstance(versions, list):
        for item in versions:
            if not isinstance(item, dict):
                continue
            event = sanitize_version_event(
                item.get("event", item.get("update_text", item.get("version_text", ""))),
                allow_fallback=False,
            )
            date = sanitize_version_date(item.get("date", item.get("timestamp", get_now_str())))
            if not event:
                continue
            cleaned_versions.append({"event": event, "date": date})
    if not cleaned_versions:
        fallback = sanitize_version_event(
            migrated.get("version_footprint", migrated.get("summary", "")),
            allow_fallback=True,
        )
        cleaned_versions = [{"event": fallback, "date": sanitize_version_date(migrated.get("updated_at", get_now_str()))}]
    migrated["versions"] = cleaned_versions[:20]
    return migrated


def parse_count_token(token: str) -> Optional[int]:
    value = (token or "").strip().lower()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value in CN_NUM_MAP:
        return CN_NUM_MAP[value]
    if value == "十":
        return 10
    match = re.match(r"^([一二两三四五六七八九])?十([一二三四五六七八九])?$", value)
    if match:
        tens = CN_NUM_MAP.get(match.group(1), 1)
        ones = CN_NUM_MAP.get(match.group(2), 0)
        return tens * 10 + ones
    return None


def extract_team_size(project: Dict[str, Any]) -> Optional[int]:
    for source in [project.get("team_text", ""), project.get("stage_metric", "")]:
        match = re.search(r"([0-9一二两三四五六七八九十俩]+)\s*人", str(source))
        if match:
            parsed = parse_count_token(match.group(1))
            if parsed is not None:
                return parsed
    return None


def parse_update_signals(update_text: str, project: Dict[str, Any]) -> Dict[str, Any]:
    del project
    text = sanitize_text_strict(update_text, allow_empty=False, max_len=280)
    lowered = text.lower()
    signals: Dict[str, Any] = {
        "team_delta": 0,
        "customer_delta": 0,
        "pilot_delta": 0,
        "new_user_delta": 0,
        "revenue_signal": "",
        "mrr_signal": "",
        "gmv_signal": "",
        "stage_override": "",
        "status_tag_override": "",
        "status_theme_override": "",
        "hits": [],
    }

    team_patterns = [
        r"(?:团队|成员|人手)[^0-9一二两三四五六七八九十俩]{0,6}(?:新增|增加|扩招|扩充|招募|招了)?\s*([0-9一二两三四五六七八九十俩]{1,3})\s*人",
        r"(?:新增|增加|扩招|扩充|招募|招了)\s*([0-9一二两三四五六七八九十俩]{1,3})\s*人",
    ]
    for pattern in team_patterns:
        match = re.search(pattern, text)
        if match:
            parsed = parse_count_token(match.group(1))
            if parsed:
                signals["team_delta"] = parsed
                signals["hits"].append(f"团队新增{parsed}人")
                break

    customer_patterns = [
        r"(?:新增|增加|签约|新增了)\s*([0-9一二两三四五六七八九十俩]{1,3})\s*(?:个|家)?(?:客户|企业|试点)",
        r"(?:新增|签约)\s*([0-9一二两三四五六七八九十俩]{1,3})\s*家",
    ]
    for pattern in customer_patterns:
        match = re.search(pattern, text)
        if match:
            parsed = parse_count_token(match.group(1))
            if parsed:
                signals["customer_delta"] = parsed
                signals["hits"].append(f"新增{parsed}个客户")
                break

    pilot_patterns = [
        r"(?:新增|增加|签约)\s*([0-9一二两三四五六七八九十俩]{1,3})\s*(?:个|家)?(?:试点|pilot)",
        r"(?:试点)\s*(?:客户|企业)?\s*([0-9一二两三四五六七八九十俩]{1,3})\s*(?:个|家)?",
    ]
    for pattern in pilot_patterns:
        match = re.search(pattern, lowered)
        if match:
            parsed = parse_count_token(match.group(1))
            if parsed:
                signals["pilot_delta"] = parsed
                signals["hits"].append(f"新增{parsed}个试点")
                break

    user_patterns = [
        r"(?:新增|增加|增长)\s*([0-9一二两三四五六七八九十俩]{1,4})\s*(?:个|名|位)?(?:用户|使用者)",
    ]
    for pattern in user_patterns:
        match = re.search(pattern, text)
        if match:
            parsed = parse_count_token(match.group(1))
            if parsed:
                signals["new_user_delta"] = parsed
                signals["hits"].append(f"新增{parsed}个用户")
                break

    rev_match = re.search(r"(?:月收入|营收|收入)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(万|w|W|千|k|K|元)?", text)
    if rev_match:
        num = rev_match.group(1)
        unit = (rev_match.group(2) or "").lower()
        if unit in ("万", "w"):
            amount = f"{num}万元"
        elif unit in ("千", "k"):
            amount = f"{num}千元"
        else:
            amount = f"{num}元"
        signals["revenue_signal"] = f"月收入达到{amount}"
        signals["hits"].append(signals["revenue_signal"])

    mrr_match = re.search(r"(?:mrr)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(万|w|W|千|k|K|元)?", lowered)
    if mrr_match:
        num = mrr_match.group(1)
        unit = (mrr_match.group(2) or "").lower()
        if unit in ("万", "w"):
            amount = f"{num}万元"
        elif unit in ("千", "k"):
            amount = f"{num}千元"
        else:
            amount = f"{num}元"
        signals["mrr_signal"] = f"MRR {amount}"
        signals["hits"].append(signals["mrr_signal"])

    gmv_match = re.search(r"(?:gmv|交易额)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(万|w|W|千|k|K|元)?", lowered)
    if gmv_match:
        num = gmv_match.group(1)
        unit = (gmv_match.group(2) or "").lower()
        if unit in ("万", "w"):
            amount = f"{num}万元"
        elif unit in ("千", "k"):
            amount = f"{num}千元"
        else:
            amount = f"{num}元"
        signals["gmv_signal"] = f"GMV {amount}"
        signals["hits"].append(signals["gmv_signal"])

    stage_keywords = [
        (["产品已上线", "正式上线", "已上线", "上线了"], "EARLY_REVENUE"),
        (["public beta", "公开测试", "公测"], "VALIDATION"),
        (["internal beta", "内部测试", "内测"], "VALIDATION"),
        (["mvp"], "MVP"),
        (["增长", "规模化"], "SCALING"),
        (["成熟", "稳定运营"], "MATURE"),
    ]
    for keywords, stage in stage_keywords:
        if any(keyword in lowered for keyword in keywords):
            signals["stage_override"] = stage
            signals["hits"].append(stage)
            break

    fundraising_keywords = [
        (["seed", "种子"], "融资中"),
        (["pre-a", "pre a", "prea"], "融资中"),
        (["融资", "募资", "fundraising", "raising"], "融资中"),
    ]
    for keywords, tag in fundraising_keywords:
        if any(keyword in lowered for keyword in keywords):
            signals["status_tag_override"] = tag
            signals["status_theme_override"] = get_status_theme(tag)
            signals["hits"].append(tag)
            if not signals["stage_override"]:
                signals["stage_override"] = tag
            break

    return signals


def apply_rule_overrides(project: Dict[str, Any], signals: Dict[str, Any]) -> Dict[str, Any]:
    next_project = copy.deepcopy(project)
    team_delta = int(signals.get("team_delta") or 0)
    customer_delta = int(signals.get("customer_delta") or 0)
    pilot_delta = int(signals.get("pilot_delta") or 0)
    user_delta = int(signals.get("new_user_delta") or 0)
    revenue_signal = sanitize_text_strict(signals.get("revenue_signal", ""), allow_empty=True, max_len=42)
    mrr_signal = sanitize_text_strict(signals.get("mrr_signal", ""), allow_empty=True, max_len=30)
    gmv_signal = sanitize_text_strict(signals.get("gmv_signal", ""), allow_empty=True, max_len=30)
    stage_override = clean_text(signals.get("stage_override", ""), 24, aggressive=True)
    status_tag_override = clean_text(signals.get("status_tag_override", ""), 30, aggressive=True)
    status_theme_override = clean_text(signals.get("status_theme_override", ""), 16, aggressive=True)

    if team_delta > 0:
        base_size = extract_team_size(next_project) or 1
        next_project["team_text"] = f"核心团队：{max(base_size + team_delta, 1)}人"

    metric_parts: List[str] = []
    if customer_delta > 0:
        metric_parts.append(f"新增{customer_delta}个客户")
    if pilot_delta > 0:
        metric_parts.append(f"新增{pilot_delta}个试点")
    if user_delta > 0:
        metric_parts.append(f"新增{user_delta}个用户")
    if revenue_signal:
        metric_parts.append(revenue_signal)
    if mrr_signal:
        metric_parts.append(mrr_signal)
    if gmv_signal:
        metric_parts.append(gmv_signal)
    if metric_parts:
        next_project["stage_metric"] = f"当前阶段：{'；'.join(metric_parts[:3])}"

    if stage_override:
        normalized_stage = normalize_stage_value(stage_override)
        next_project["stage"] = normalized_stage
        next_project["status_tag"] = infer_status_tag(normalized_stage)

    if status_tag_override:
        next_project["status_tag"] = status_tag_override

    final_status = next_project.get("status_tag", "")
    if final_status:
        next_project["status_theme"] = status_theme_override or get_status_theme(final_status)

    return next_project


def build_rule_summary(signals: Dict[str, Any]) -> str:
    hits = [sanitize_text_strict(hit, allow_empty=True, max_len=30) for hit in signals.get("hits", [])]
    hits = [hit for hit in hits if hit]
    return "；".join(hits[:3])


def apply_schema_to_project(
    project: Dict[str, Any], schema: Dict[str, Any], update_text: str, timestamp: str, signals: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    next_project = copy.deepcopy(project)
    next_project["desc"] = sanitize_text_strict(
        schema.get("desc", next_project.get("desc", "")),
        allow_empty=False,
        max_len=6000,
    )
    next_project["summary"] = sanitize_text_strict(
        schema.get("summary", next_project.get("summary", "")),
        allow_empty=False,
        max_len=78,
    )
    next_project["users"] = sanitize_text_strict(
        schema.get("users", next_project.get("users", "")),
        allow_empty=False,
        max_len=44,
    ) or "待补充"
    next_project["use_cases"] = sanitize_text_strict(
        schema.get("use_cases", next_project.get("use_cases", "")),
        allow_empty=True,
        max_len=120,
    )
    next_project["problem_statement"] = sanitize_text_strict(
        schema.get("problem_statement", next_project.get("problem_statement", "")),
        allow_empty=True,
        max_len=180,
    )
    next_project["solution_approach"] = sanitize_text_strict(
        schema.get("solution_approach", next_project.get("solution_approach", "")),
        allow_empty=True,
        max_len=180,
    )
    next_project["tech_stack"] = clean_list(schema.get("tech_stack", next_project.get("tech_stack", [])), max_items=4)

    schema_stage = normalize_stage_value(schema.get("stage", next_project.get("stage", "BUILDING")))
    next_project["stage"] = schema_stage
    schema_model_desc = clean_text(schema.get("model_desc", schema.get("model", next_project.get("model_desc", next_project.get("model", "")))), 50)
    if schema_model_desc:
        next_project["model_desc"] = schema_model_desc
        next_project["model"] = schema_model_desc
    next_project["form_type"] = normalize_form_type(
        schema.get("form_type", next_project.get("form_type", "")),
        context=" ".join([next_project.get("title", ""), next_project.get("summary", ""), next_project.get("model_desc", "")]),
    )
    next_project["model_type"] = normalize_model_type(
        schema.get("model_type", next_project.get("model_type", "")),
        model_desc=next_project.get("model_desc", next_project.get("model", "")),
    )
    next_project["pricing_strategy"] = normalize_pricing_strategy(
        schema.get("pricing_strategy", next_project.get("pricing_strategy", "")),
        model_desc=next_project.get("model_desc", ""),
    )

    if signals:
        next_project = apply_rule_overrides(next_project, signals)

    rule_summary = build_rule_summary(signals or {})
    model_version = sanitize_text_strict(
        schema.get("latest_update", schema.get("version_footprint", "")),
        allow_empty=True,
        max_len=90,
    )
    fallback_version = sanitize_text_strict(update_text, allow_empty=False, max_len=90)
    version_parts: List[str] = []
    for part in [rule_summary, model_version, fallback_version]:
        if part and part not in version_parts:
            version_parts.append(part)
    new_version_text = sanitize_version_event("；".join(version_parts), allow_fallback=True)
    next_project["version_footprint"] = new_version_text
    next_project["latest_update"] = sanitize_latest_update(new_version_text, fallback=fallback_version)
    next_project["versions"] = [{"event": new_version_text, "date": sanitize_version_date(timestamp)}]
    next_project["updated_at"] = timestamp
    next_project["stage"] = normalize_stage_value(next_project.get("stage", ""))
    next_project["status_tag"] = infer_status_tag(next_project.get("stage", ""))
    next_project["status_theme"] = get_status_theme(next_project["status_tag"])
    return normalize_project(next_project)


def compare_field_value(value: Any) -> str:
    if isinstance(value, list):
        cleaned = [sanitize_text_strict(item, allow_empty=True, max_len=24) for item in value]
        cleaned = [item for item in cleaned if item]
        return ", ".join(cleaned) if cleaned else "—"
    return sanitize_text_strict(value, allow_empty=True, max_len=120) or "—"


def enrich_generated_project(schema: Dict[str, Any]) -> Dict[str, Any]:
    team_text = normalize_team_text(schema.get("team_text", schema.get("team_size", ""))) or "核心团队：1人"
    stage_metric = normalize_stage_metric_text(schema.get("stage_metric", schema.get("stage_progress", ""))) or "当前阶段：完成首轮验证"
    normalized_stage = normalize_stage_value(schema.get("stage", ""))
    latest_update = sanitize_latest_update(
        schema.get("latest_update", schema.get("version_footprint", "")),
        fallback=schema.get("version_footprint", ""),
    )
    project = normalize_project(
        {
            **schema,
            "stage": normalized_stage,
            "latest_update": latest_update,
            "status_tag": infer_status_tag(normalized_stage),
            "shape": infer_shape(schema),
            "team_text": team_text,
            "stage_metric": stage_metric,
            "status_theme": get_status_theme(infer_status_tag(normalized_stage)),
            "generated": True,
            "versions": build_versions_from_schema(schema),
            "updates": [
                build_update_entry(
                    project_id="",
                    author_user_id="",
                    content=latest_update,
                    source="create",
                    created_at=get_now_str(),
                    input_meta={"has_text": True, "has_file": False, "merged_chars": len(latest_update)},
                )
            ],
            "share": {"is_public": False},
        }
    )
    return project


def project_matches(
    project: Dict[str, Any],
    tech_filter: str,
    stage_filter: str,
    form_filter: str,
    model_filter: str,
    keyword: str,
) -> bool:
    if tech_filter != "全部技术" and tech_filter not in project.get("tech_stack", []):
        return False
    if stage_filter != "所有阶段" and stage_filter != project.get("stage", ""):
        return False
    if form_filter != "所有形态" and form_filter != project.get("form_type", ""):
        return False
    if model_filter != "所有模式" and model_filter != project.get("model_type", ""):
        return False

    query = clean_text(keyword, 40).lower()
    if not query:
        return True
    haystack = " ".join(
        [
            project.get("title", ""),
            " ".join(project.get("tech_stack", [])),
            project.get("users", ""),
            project.get("model_desc", project.get("model", "")),
            project.get("summary", ""),
            project.get("latest_update", ""),
            project.get("shape", ""),
            project.get("stage_label", ""),
            project.get("form_type_label", ""),
            project.get("model_type_label", ""),
        ]
    ).lower()
    return query in haystack
