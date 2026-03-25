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
    "tech_stack": [],
    "users": "",
    "model": "",
    "stage": "",
    "version_footprint": "",
    "summary": "",
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


def get_now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def sanitize_version_event(value: Any, allow_fallback: bool = True) -> str:
    raw = unescape(str(value or ""))
    if has_markup_contamination(raw) or is_timeline_leak_text(raw):
        cleaned = sanitize_text_strict(raw, allow_empty=True, max_len=120)
    else:
        cleaned = sanitize_text_strict(raw, allow_empty=True, max_len=120)
    if has_markup_contamination(cleaned) or is_timeline_leak_text(cleaned):
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
    clean["tech_stack"] = clean_list(data.get("tech_stack", []), max_items=4)
    clean["users"] = clean_text(data.get("users", "待补充"), max_len=44) or "待补充"
    clean["model"] = clean_text(data.get("model", "待补充"), max_len=34) or "待补充"
    clean["stage"] = clean_text(data.get("stage", "早期阶段"), max_len=24) or "早期阶段"
    clean["version_footprint"] = sanitize_text_strict(data.get("version_footprint", "初始版本"), allow_empty=False, max_len=120)
    clean["summary"] = sanitize_text_strict(data.get("summary", "暂无亮点摘要"), allow_empty=False, max_len=78)
    team_text = normalize_team_text(data.get("team_text", data.get("team_size", "")))
    stage_metric = normalize_stage_metric_text(data.get("stage_metric", data.get("stage_progress", "")))
    if team_text:
        clean["team_text"] = team_text
    if stage_metric:
        clean["stage_metric"] = stage_metric

    return clean


def infer_status_tag(stage: str) -> str:
    s = stage.lower()
    if "seed" in s or "种子" in stage:
        return "融资中 (Seed)"
    if "pre-a" in s or "pre a" in s or "prea" in s:
        return "融资中 (Pre-A)"
    if "融资" in stage or "fundraising" in s or "raising" in s:
        return "融资中"
    if "mvp" in s or "上线" in stage:
        return "MVP 已上线"
    if "公测" in stage:
        return "公测中"
    if "内测" in stage or "beta" in s:
        return "内测中"
    if "增长" in stage:
        return "增长阶段"
    return "早期阶段"


def infer_metrics(schema: Dict[str, Any]) -> Dict[str, str]:
    m = schema.get("model", "")
    stg = schema.get("stage", "")
    sig = "订阅收入验证中" if ("订阅" in m or "付费" in m) else "产品价值验证中"
    prog = "稳定迭代" if ("上线" in stg or "运营" in stg) else ("小范围验证" if "内测" in stg else "方向打磨")
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
        "footprints": build_footprints(schema.get("version_footprint", "")),
        "metrics": infer_metrics(schema),
        "generated": generated,
        **schema,
    }


def get_export_payload(project: Dict[str, Any]) -> Dict[str, Any]:
    return {k: project.get(k) for k in EXPORT_KEYS}


def get_status_theme(status: str) -> str:
    if "Seed" in status or "种子" in status:
        return "purple"
    if "Pre-A" in status or "Pre A" in status:
        return "amber"
    if "融资中" in status:
        return "amber"
    if "投后" in status or "稳定增长" in status:
        return "green"
    if "已上线" in status or "MVP" in status:
        return "blue"
    return "slate"


def infer_shape(schema: Dict[str, Any]) -> str:
    tech_text = " ".join(schema.get("tech_stack", []))
    model = schema.get("model", "")
    if "Rust" in tech_text or "硬件" in model:
        return "嵌入式硬件模块"
    if "AI" in schema.get("title", "") or "AI" in tech_text:
        return "AI 原生应用"
    if "订阅" in model or "SaaS" in model:
        return "Cloud Native SaaS"
    return "结构化项目平台"


def build_versions_from_schema(schema: Dict[str, Any]) -> List[Dict[str, str]]:
    date = get_now_str()
    event = sanitize_version_event(schema.get("version_footprint", "初始版本"), allow_fallback=True)
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
    ui["shape"] = clean_text(project.get("shape", infer_shape(schema)), 28)
    ui["team_text"] = clean_text(project.get("team_text", ui["metrics"]["team_size"]), 28)
    ui["stage_metric"] = clean_text(project.get("stage_metric", ui["metrics"]["progress"]), 44)
    ui["share_slug"] = clean_text(project.get("share_slug", f"onefile-{ui['id']}"), 40)
    ui["summary"] = sanitize_text_strict(project.get("summary", ui["summary"]), allow_empty=False, max_len=78)

    versions: List[Dict[str, str]] = []
    raw_versions = project.get("versions")
    if isinstance(raw_versions, list):
        for item in raw_versions:
            if not isinstance(item, dict):
                continue
            event = sanitize_version_event(
                item.get("event", item.get("update_text", item.get("version_text", ""))),
                allow_fallback=False,
            )
            date = sanitize_version_date(item.get("date", item.get("timestamp", get_now_str())))
            if not event:
                continue
            versions.append({"event": event, "date": date})

    if not versions:
        versions = build_versions_from_schema(schema)

    ui["versions"] = versions[:20]
    ui["version_footprint"] = sanitize_version_event(ui["versions"][0].get("event", ""), allow_fallback=True)

    timeline_items: List[Dict[str, Any]] = []
    for i, version in enumerate(ui["versions"][:3]):
        version_text = sanitize_version_event(version.get("event", ""), allow_fallback=False)
        if not version_text:
            continue
        timeline_items.append(
            {
                "title": clean_text(version_text, 42, aggressive=True),
                "date": clean_text(version.get("date", ""), 24, aggressive=True),
                "desc": clean_text(version_text, 82, aggressive=True) if len(version_text) > 44 else "",
                "current": i == 0,
            }
        )
    if not timeline_items:
        timeline_items = [
            {
                "title": clean_text(ui["version_footprint"], 42, aggressive=True),
                "date": clean_text(ui.get("updated_at", get_now_str()), 24, aggressive=True),
                "desc": "",
                "current": True,
            }
        ]
    ui["timeline"] = timeline_items
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

    return cleaned_versions[:20]


def prepare_project_for_render(project: Dict[str, Any]) -> Dict[str, Any]:
    render_project = normalize_project(project)
    render_versions = sanitize_versions_for_render(render_project)
    render_project["versions"] = render_versions
    render_project["version_footprint"] = render_versions[0]["event"]
    return render_project


def hard_scrub_project_for_state(project: Dict[str, Any]) -> Dict[str, Any]:
    scrubbed = normalize_project(project)
    scrubbed_versions = sanitize_versions_for_render(scrubbed)
    scrubbed["versions"] = scrubbed_versions
    scrubbed["version_footprint"] = scrubbed_versions[0]["event"]
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
        "title_override": "",
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
        (["产品已上线", "正式上线", "已上线", "上线了"], "产品已上线"),
        (["public beta", "公开测试", "公测"], "公测阶段"),
        (["internal beta", "内部测试", "内测"], "内测阶段"),
        (["公测"], "公测阶段"),
        (["内测"], "内测阶段"),
        (["mvp"], "MVP 已上线"),
    ]
    for keywords, stage in stage_keywords:
        if any(keyword in lowered for keyword in keywords):
            signals["stage_override"] = stage
            if stage == "产品已上线":
                signals["hits"].append("产品已上线")
            else:
                signals["hits"].append(stage)
            break

    fundraising_keywords = [
        (["seed", "种子"], "融资中 (Seed)"),
        (["pre-a", "pre a", "prea"], "融资中 (Pre-A)"),
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

    rename_to = detect_rename_signal(text)
    if rename_to:
        signals["title_override"] = rename_to
        signals["hits"].append(f"项目更名为{rename_to}")

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
    title_override = _sanitize_title_candidate(signals.get("title_override", ""))

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
        next_project["stage"] = stage_override
        next_project["status_tag"] = infer_status_tag(stage_override)

    if status_tag_override:
        next_project["status_tag"] = status_tag_override

    final_status = next_project.get("status_tag", "")
    if final_status:
        next_project["status_theme"] = status_theme_override or get_status_theme(final_status)

    if title_override and validate_title_candidate(title_override):
        next_project["title"] = title_override

    return next_project


def build_rule_summary(signals: Dict[str, Any]) -> str:
    hits = [sanitize_text_strict(hit, allow_empty=True, max_len=30) for hit in signals.get("hits", [])]
    hits = [hit for hit in hits if hit]
    return "；".join(hits[:3])


def apply_schema_to_project(
    project: Dict[str, Any], schema: Dict[str, Any], update_text: str, timestamp: str, signals: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    next_project = copy.deepcopy(project)
    rename_to = detect_rename_signal(update_text)
    if rename_to and validate_title_candidate(rename_to):
        next_project["title"] = rename_to
    # Update flow: keep stable profile fields; AI only refines summary/version text.
    next_project["summary"] = sanitize_text_strict(
        schema.get("summary", next_project.get("summary", "")),
        allow_empty=False,
        max_len=78,
    )

    if signals:
        next_project = apply_rule_overrides(next_project, signals)

    rule_summary = build_rule_summary(signals or {})
    model_version = sanitize_text_strict(schema.get("version_footprint", ""), allow_empty=True, max_len=90)
    fallback_version = sanitize_text_strict(update_text, allow_empty=False, max_len=90)
    version_parts: List[str] = []
    for part in [rule_summary, model_version, fallback_version]:
        if part and part not in version_parts:
            version_parts.append(part)
    new_version_text = sanitize_version_event("；".join(version_parts), allow_fallback=True)
    next_project["version_footprint"] = new_version_text

    versions = next_project.get("versions", [])
    if not isinstance(versions, list):
        versions = []
    versions.insert(0, {"event": new_version_text, "date": sanitize_version_date(timestamp)})
    next_project["versions"] = versions[:20]
    next_project["updated_at"] = timestamp
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
    project = normalize_project(
        {
            **schema,
            "status_tag": infer_status_tag(schema.get("stage", "")),
            "shape": infer_shape(schema),
            "team_text": team_text,
            "stage_metric": stage_metric,
            "status_theme": get_status_theme(infer_status_tag(schema.get("stage", ""))),
            "generated": True,
            "versions": build_versions_from_schema(schema),
        }
    )
    return project


def project_matches(project: Dict[str, Any], tech_filter: str, stage_filter: str, model_filter: str, keyword: str) -> bool:
    if tech_filter != "全部技术" and tech_filter not in project.get("tech_stack", []):
        return False
    if stage_filter != "所有阶段" and stage_filter != project.get("status_tag", ""):
        return False
    if model_filter != "所有模式" and model_filter not in project.get("model", ""):
        return False

    query = clean_text(keyword, 40).lower()
    if not query:
        return True
    haystack = " ".join(
        [
            project.get("title", ""),
            " ".join(project.get("tech_stack", [])),
            project.get("users", ""),
            project.get("model", ""),
            project.get("summary", ""),
            project.get("shape", ""),
        ]
    ).lower()
    return query in haystack
