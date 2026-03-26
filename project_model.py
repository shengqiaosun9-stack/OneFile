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
    "model_type": "UNKNOWN",
    "pricing_strategy": "",
    "form_type": "OTHER",
    "stage": "",
    "version_footprint": "",
    "latest_update": "",
    "summary": "",
    "owner_user_id": "",
    "share": {},
    "updates": [],
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

UPDATE_SOURCE_VALUES = {"create", "overlay_update", "direct_edit", "system_migration"}


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


def build_update_entry(
    project_id: str,
    author_user_id: str,
    content: Any,
    source: str,
    created_at: str = "",
    input_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    safe_content = sanitize_version_event(content, allow_fallback=True)
    safe_created_at = sanitize_version_date(created_at or get_now_str())
    safe_source = source if source in UPDATE_SOURCE_VALUES else "overlay_update"
    merged_chars = len(safe_content)
    return {
        "id": clean_text(str(uuid.uuid4())[:12], 20, aggressive=True),
        "project_id": clean_text(project_id, 20, aggressive=True),
        "author_user_id": _sanitize_owner_user_id(author_user_id),
        "content": safe_content,
        "created_at": safe_created_at,
        "source": safe_source,
        "input_meta": normalize_input_meta(input_meta or {}, merged_chars_fallback=merged_chars),
    }


def _update_sort_key(item: Dict[str, Any]) -> str:
    return sanitize_version_date(item.get("created_at", ""))


def normalize_updates_state(project: Dict[str, Any], project_id: str, owner_user_id: str) -> List[Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
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
