import re
from html import unescape
from typing import Any, List, Optional

MARKUP_TOKENS = [
    "<div",
    "</div",
    "<span",
    "</span",
    "<script",
    "</script",
    "<style",
    "</style",
    "class=",
    "timeline-",
    "timeline_",
    "timeline-item",
    "timeline-row",
    "timeline-dot",
    "```",
]

TIMELINE_LEAK_TOKENS = [
    "timeline-item",
    "timeline-row",
    "timeline-dot",
    "timeline-headline",
    "timeline-date",
    "class=",
    "</div",
    "<div",
    "<span",
    "</span",
    "div class",
    "span class",
]

TEMPLATE_ARTIFACT_RE = re.compile(
    r"(</?\s*(div|span|section|article)\b|class\s*=|timeline[-_]|timeline(item|row|dot|headline|date)|```|\b(div|span)\s+class\b)",
    re.IGNORECASE,
)

SAFE_TEXT_PATTERN = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9\-\+\.,，。；;：:（）()《》“”‘’、/ ]+$")

_CN_NUM_MAP = {
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


def _parse_count_token(token: str) -> Optional[int]:
    value = (token or "").strip().lower()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if value in _CN_NUM_MAP:
        return _CN_NUM_MAP[value]
    if value == "十":
        return 10
    match = re.match(r"^([一二两三四五六七八九])?十([一二三四五六七八九])?$", value)
    if match:
        tens = _CN_NUM_MAP.get(match.group(1), 1)
        ones = _CN_NUM_MAP.get(match.group(2), 0)
        return tens * 10 + ones
    return None


def clean_text(value: Any, max_len: int = 88, aggressive: bool = False) -> str:
    txt = unescape(str(value or ""))
    txt = re.sub(r"```[\s\S]*?```", "", txt)
    txt = txt.replace("```", "")
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = re.sub(r"&lt;[^&]*&gt;", "", txt)
    txt = re.sub(r"\b[a-zA-Z:_-]+\s*=\s*\"[^\"]*\"", "", txt)
    txt = re.sub(r"\b[a-zA-Z:_-]+\s*=\s*'[^']*'", "", txt)
    txt = re.sub(r"[{}\[\]\\]", "", txt)
    if aggressive:
        txt = re.sub(r"class\s*=", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"</?\w+[^>]*>", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"\b(div|span|section|article|script|style|html|body)\b", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"timeline[-_a-z0-9]*", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"\b(item|row|dot|headline|date|desc)\b", "", txt, flags=re.IGNORECASE)
    txt = txt.replace("\n", " ").replace("\r", " ")
    txt = re.sub(r"[<>`$]", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) > max_len:
        txt = txt[: max_len - 1].rstrip() + "…"
    return txt


def has_markup_contamination(text: Any) -> bool:
    lowered = unescape(str(text or "")).lower()
    if any(token in lowered for token in MARKUP_TOKENS):
        return True
    if TEMPLATE_ARTIFACT_RE.search(lowered):
        return True
    if re.search(r"</?\w+[^>]*>", lowered):
        return True
    if re.search(r"\b(class|id|style|src|href|onclick|onload|data-[a-z0-9_-]+)\s*=", lowered):
        return True
    return False


def sanitize_text_strict(text: Any, allow_empty: bool = True, max_len: int = 120) -> str:
    raw = unescape(str(text or ""))
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"```[\s\S]*?```", "\n", raw)
    raw = raw.replace("```", "\n")
    lines: List[str] = []
    for line in raw.split("\n"):
        probe = line.strip()
        if not probe:
            continue
        if TEMPLATE_ARTIFACT_RE.search(probe):
            continue
        if has_markup_contamination(probe):
            continue
        cleaned = re.sub(r"<[^>]+>", " ", probe)
        cleaned = re.sub(r"&lt;[^&]*&gt;", " ", cleaned)
        cleaned = re.sub(r"\b[a-zA-Z:_-]+\s*=\s*\"[^\"]*\"", " ", cleaned)
        cleaned = re.sub(r"\b[a-zA-Z:_-]+\s*=\s*'[^']*'", " ", cleaned)
        cleaned = re.sub(r"\b(div|span|section|article|script|style|timeline[-_a-z0-9]*)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[<>{}\[\]`$\\]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and not has_markup_contamination(cleaned):
            lines.append(cleaned)
    merged = " ".join(lines).strip()
    if not merged and not allow_empty:
        merged = "本次更新已记录"
    merged = re.sub(r"\s+", " ", merged).strip()
    if len(merged) > max_len:
        merged = merged[: max_len - 1].rstrip() + "…"
    return merged


def is_timeline_leak_text(text: Any) -> bool:
    probe = unescape(str(text or "")).lower()
    return any(token in probe for token in TIMELINE_LEAK_TOKENS)


def clean_list(values: Any, max_items: int = 4) -> List[str]:
    if isinstance(values, str):
        raw = re.split(r"[,，/|；;]", values)
    elif isinstance(values, list):
        raw = values
    else:
        raw = []

    out: List[str] = []
    for v in raw:
        c = clean_text(v, max_len=22)
        if c and c not in out:
            out.append(c)
    return out[:max_items]


def normalize_team_text(value: Any) -> str:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=36)
    if not raw:
        return ""
    match = re.search(r"([0-9一二两三四五六七八九十俩]+)\s*人", raw)
    if match:
        count = _parse_count_token(match.group(1))
        if count is not None:
            return f"核心团队：{max(count, 1)}人"
    if raw.startswith("核心团队："):
        return clean_text(raw, 28, aggressive=True)
    return clean_text(f"核心团队：{raw}", 28, aggressive=True)


def normalize_stage_metric_text(value: Any) -> str:
    raw = sanitize_text_strict(value, allow_empty=True, max_len=44)
    if not raw:
        return ""
    if raw.startswith("当前阶段："):
        return clean_text(raw, 44, aggressive=True)
    return clean_text(f"当前阶段：{raw}", 44, aggressive=True)
