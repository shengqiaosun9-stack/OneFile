import json
import os
import re
from io import BytesIO
from html import unescape
from typing import Any, Dict, List, Optional

from project_model import (
    get_export_payload,
    normalize_form_type,
    normalize_model_type,
    normalize_pricing_strategy,
    normalize_stage_value,
    parse_count_token,
    parse_update_signals,
    sanitize_schema,
)
from text_cleaning import clean_text, sanitize_text_strict

_LAST_USED_LOCAL_STRUCTURING = False
_LAST_API_ERROR = ""


def _safe_secret_get(key: str) -> Optional[str]:
    _ = key
    return None


def _safe_session_state_set(key: str, value: Any) -> None:
    _ = (key, value)


def _set_structuring_meta(used_local_structuring: bool, api_error: str = "") -> None:
    global _LAST_USED_LOCAL_STRUCTURING, _LAST_API_ERROR
    _LAST_USED_LOCAL_STRUCTURING = bool(used_local_structuring)
    _LAST_API_ERROR = clean_text(api_error or "", 180)
    _safe_session_state_set("used_local_structuring", _LAST_USED_LOCAL_STRUCTURING)
    _safe_session_state_set("last_api_error", _LAST_API_ERROR or None)


def get_last_structuring_meta() -> Dict[str, Any]:
    return {
        "used_local_structuring": bool(_LAST_USED_LOCAL_STRUCTURING),
        "last_api_error": _LAST_API_ERROR or "",
    }


def extract_text_from_uploaded_file(uploaded_file: Any) -> str:
    if not uploaded_file:
        return ""
    name = str(getattr(uploaded_file, "name", "") or "").lower()
    data = uploaded_file.getvalue()
    if not data:
        return ""

    if name.endswith(".pdf"):
        try:
            try:
                from pypdf import PdfReader  # type: ignore
            except Exception as exc:
                raise ValueError(f"PDF 解析依赖不可用：{clean_text(exc, 80)}")
            reader = PdfReader(BytesIO(data))
            pages: List[str] = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text)
            merged = "\n".join(pages).strip()
            return sanitize_text_strict(merged, allow_empty=True, max_len=6000)
        except Exception as exc:
            raise ValueError(f"PDF 解析失败：{clean_text(exc, 80)}")

    if name.endswith(".txt") or name.endswith(".md"):
        try:
            text = data.decode("utf-8", errors="ignore")
            return sanitize_text_strict(text, allow_empty=True, max_len=6000)
        except Exception as exc:
            raise ValueError(f"文本文件解析失败：{clean_text(exc, 80)}")

    raise ValueError("仅支持 PDF、TXT、MD 文件。")


def get_model_name() -> str:
    model = (
        os.getenv("HUNYUAN_MODEL")
        or os.getenv("MODEL_NAME")
    )
    if not model:
        model = _safe_secret_get("HUNYUAN_MODEL") or _safe_secret_get("MODEL_NAME")
    return str(model or "hunyuan-turbos-latest").strip()


def get_base_url() -> str:
    base_url = os.getenv("HUNYUAN_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    if not base_url:
        base_url = _safe_secret_get("HUNYUAN_BASE_URL") or _safe_secret_get("OPENAI_BASE_URL")
    return str(base_url or "https://api.hunyuan.cloud.tencent.com/v1").strip()


def get_client() -> Any:
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        raise ValueError(f"OpenAI 兼容 SDK 不可用：{clean_text(exc, 80)}")

    api_key = (
        os.getenv("HUNYUAN_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        api_key = _safe_secret_get("HUNYUAN_API_KEY") or _safe_secret_get("OPENAI_API_KEY")
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ValueError("未检测到 API Key。请设置 HUNYUAN_API_KEY，或使用 OPENAI_API_KEY 作为回退。")

    return OpenAI(
        api_key=api_key,
        base_url=get_base_url(),
    )


def extract_json_object(text: str) -> Dict[str, Any]:
    txt = (text or "").strip()
    if txt.startswith("```"):
        txt = txt.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        start = txt.find("{")
        end = txt.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(txt[start : end + 1])
        raise


def infer_stage_from_text(text: str) -> str:
    return normalize_stage_value(text)


def extract_tech_stack_heuristic(text: str) -> List[str]:
    mapping = [
        ("python", "Python"),
        ("fastapi", "FastAPI"),
        ("flask", "Flask"),
        ("django", "Django"),
        ("react", "React"),
        ("next", "Next.js"),
        ("vue", "Vue"),
        ("node", "Node.js"),
        ("tailwind", "Tailwind"),
        ("supabase", "Supabase"),
        ("vercel", "Vercel"),
        ("stripe", "Stripe API"),
        ("rust", "Rust"),
        ("webassembly", "WebAssembly"),
        ("ai", "AI"),
        ("llm", "LLM"),
    ]
    lowered = text.lower()
    out: List[str] = []
    for keyword, label in mapping:
        if keyword in lowered and label not in out:
            out.append(label)
    return out[:4]


def extract_field_by_prefix(text: str, prefixes: List[str], max_len: int) -> str:
    for prefix in prefixes:
        match = re.search(rf"{prefix}\s*[:：]\s*([^\n。；;]+)", text, flags=re.IGNORECASE)
        if match:
            value = sanitize_text_strict(match.group(1), allow_empty=True, max_len=max_len)
            if value:
                return value
    return ""


def fallback_structure_project(raw_input: str, user_title: str = "") -> Dict[str, Any]:
    raw = unescape(str(raw_input or ""))
    safe_text = sanitize_text_strict(raw, allow_empty=False, max_len=1500)
    lines = [sanitize_text_strict(line, allow_empty=True, max_len=80) for line in raw.splitlines()]
    lines = [line for line in lines if line]

    title = sanitize_text_strict(user_title, allow_empty=True, max_len=42) or "未命名项目"

    tech_stack = extract_tech_stack_heuristic(raw)
    users = extract_field_by_prefix(raw, [r"目标用户", r"用户", r"target users?"], 44) or "待补充"
    model = extract_field_by_prefix(raw, [r"商业模式", r"模式", r"business model"], 50) or "待补充"
    stage = infer_stage_from_text(safe_text)
    form_type = normalize_form_type("", context=safe_text)
    model_type = normalize_model_type("", model_desc=model)
    pricing_strategy = normalize_pricing_strategy("", model_desc=model)
    summary = extract_field_by_prefix(raw, [r"一句话亮点", r"亮点", r"summary"], 78)
    if not summary:
        summary = sanitize_text_strict(safe_text, allow_empty=False, max_len=78)
    problem_statement = extract_field_by_prefix(raw, [r"问题", r"痛点", r"problem"], 160) or sanitize_text_strict(safe_text, allow_empty=True, max_len=140)
    solution_approach = extract_field_by_prefix(raw, [r"解决方案", r"方案", r"solution"], 160) or summary
    use_cases = extract_field_by_prefix(raw, [r"使用场景", r"场景", r"use case"], 120) or f"{users}典型使用场景待补充"

    signals = parse_update_signals(safe_text, {})
    team_text = ""
    stage_metric = ""
    team_match = re.search(r"([0-9一二两三四五六七八九十俩]{1,3})\s*人", safe_text)
    if team_match:
        team_count = parse_count_token(team_match.group(1))
        if team_count:
            team_text = f"核心团队：{max(team_count, 1)}人"
    if signals.get("customer_delta"):
        stage_metric = f"当前阶段：新增{int(signals['customer_delta'])}个客户"
    elif "上线" in stage:
        stage_metric = "当前阶段：完成上线发布"

    return sanitize_schema(
        {
            "title": title,
            "desc": safe_text,
            "tech_stack": tech_stack,
            "users": users,
            "use_cases": use_cases,
            "problem_statement": problem_statement,
            "solution_approach": solution_approach,
            "model": model,
            "model_desc": model,
            "model_type": model_type,
            "pricing_strategy": pricing_strategy,
            "form_type": form_type,
            "stage": stage,
            "version_footprint": "v1.0 建立项目档案并完成首轮结构化",
            "latest_update": "已完成首次结构化归档",
            "summary": summary,
            "team_text": team_text,
            "stage_metric": stage_metric,
        }
    )


def build_update_input(project: Dict[str, Any], update_text: str) -> str:
    context = {
        **get_export_payload(project),
        "form_type": project.get("form_type", ""),
        "model_type": project.get("model_type", ""),
        "pricing_strategy": project.get("pricing_strategy", ""),
        "model_desc": project.get("model_desc", project.get("model", "")),
        "desc": project.get("desc", ""),
        "use_cases": project.get("use_cases", ""),
        "problem_statement": project.get("problem_statement", ""),
        "solution_approach": project.get("solution_approach", ""),
        "latest_update": project.get("latest_update", ""),
        "team_text": project.get("team_text", ""),
        "stage_metric": project.get("stage_metric", ""),
    }
    return (
        "这是一个已存在的项目档案，请根据最新进展更新结构化字段。"
        f"\n\n当前档案：\n{json.dumps(context, ensure_ascii=False)}"
        f"\n\n最新进展：\n{update_text}"
    )


def structure_project(raw_input: str, user_title: str = "") -> Dict[str, Any]:
    _set_structuring_meta(used_local_structuring=False, api_error="")
    system_prompt = (
        "你是 OneFile 的 AI 结构化引擎。"
        "任务是把混乱项目描述整理为投资人可快速理解、可比较、可检索的结构化项目档案。"
        "你需要自动去噪、去重复、统一表达，并在信息缺失时做谨慎推断。"
    )

    user_prompt = f"""
你将收到一段可能中英混杂、口语化、冗余、甚至不完整的项目描述。

目标：输出一个高质量、可比较、可用于数据库检索的标准化 JSON。

严格要求：
1) 严格按照以下 JSON 格式输出，不要任何解释，不要 markdown，不要额外文本。
2) tech_stack 必须是字符串数组。
3) 每个字段尽量简洁，避免空话和重复。
4) users 必须是一句话明确目标用户。
5) summary 必须是一句话亮点（偏投资人视角）。
6) 所有字段必须是纯自然语言，不要 HTML、标签或模板代码（例如 <div>、<span>、class=、timeline-*）。
7) stage 必须严格为以下枚举之一：IDEA、BUILDING、MVP、VALIDATION、EARLY_REVENUE、SCALING、MATURE。
8) form_type 必须严格为以下枚举之一：AI_NATIVE_APP、SAAS、API_SERVICE、AGENT、MARKETPLACE、DATA_TOOL、INFRASTRUCTURE、OTHER。
9) model_type 必须严格为以下枚举之一：B2B_SUBSCRIPTION、B2C_SUBSCRIPTION、USAGE_BASED、COMMISSION、ONE_TIME、OUTSOURCING、ADS、MARKETPLACE、HYBRID、UNKNOWN。
10) pricing_strategy 可为空字符串；若有值仅能是：FREEMIUM、FREE_TRIAL、ENTERPRISE_ONLY、SELF_SERVE。
11) 在不影响 7 个标准字段的前提下，补充 model_desc、form_type、model_type、pricing_strategy、team_text、stage_metric。
12) 可选补充字段：desc、problem_statement、solution_approach、use_cases、latest_update。

JSON Schema:
{{
  "title": "项目名称",
  "desc": "用户原始输入整理后的干净描述（可为空字符串）",
  "tech_stack": ["技术1", "技术2"],
  "users": "目标用户一句话",
  "use_cases": "目标用户典型使用场景",
  "problem_statement": "项目解决的问题",
  "solution_approach": "解决方案路径",
  "model": "商业模式自然语言描述",
  "model_desc": "商业模式自然语言描述（与model一致）",
  "model_type": "B2B_SUBSCRIPTION|B2C_SUBSCRIPTION|USAGE_BASED|COMMISSION|ONE_TIME|OUTSOURCING|ADS|MARKETPLACE|HYBRID|UNKNOWN",
  "pricing_strategy": "FREEMIUM|FREE_TRIAL|ENTERPRISE_ONLY|SELF_SERVE|''",
  "form_type": "AI_NATIVE_APP|SAAS|API_SERVICE|AGENT|MARKETPLACE|DATA_TOOL|INFRASTRUCTURE|OTHER",
  "stage": "IDEA|BUILDING|MVP|VALIDATION|EARLY_REVENUE|SCALING|MATURE",
  "version_footprint": "版本足迹",
  "latest_update": "当前状态的一句话进展",
  "summary": "一句话亮点",
  "team_text": "核心团队：X人（可为空字符串）",
  "stage_metric": "当前阶段：关键进展一句话（可为空字符串）"
}}

项目输入：
{raw_input}
""".strip()

    try:
        client = get_client()
        model_name = get_model_name()
        base_url = get_base_url()
        print(f"[OneFile] provider=hunyuan base_url={base_url} model={model_name}")
        resp = client.chat.completions.create(
            model=model_name,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            extra_body={"enable_enhancement": True},
        )
        parsed = extract_json_object(resp.choices[0].message.content or "{}")
        schema = sanitize_schema(parsed)
        if sanitize_text_strict(user_title, allow_empty=True, max_len=42):
            schema["title"] = sanitize_text_strict(user_title, allow_empty=False, max_len=42)
        return sanitize_schema(schema)
    except Exception as exc:
        _set_structuring_meta(used_local_structuring=True, api_error=str(exc))
        return fallback_structure_project(raw_input, user_title=user_title)


def _extract_response_output_text(resp: Any) -> str:
    direct = getattr(resp, "output_text", "")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    payload: Dict[str, Any] = {}
    if hasattr(resp, "model_dump"):
        try:
            payload = resp.model_dump()  # type: ignore[assignment]
        except Exception:
            payload = {}
    if not payload:
        return ""

    output_items = payload.get("output", [])
    if not isinstance(output_items, list):
        return ""
    for item in output_items:
        if not isinstance(item, dict):
            continue
        content_items = item.get("content", [])
        if not isinstance(content_items, list):
            continue
        for part in content_items:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"}:
                text = part.get("text", "")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    return ""


def _normalize_generate_stage(value: Any) -> str:
    stage = sanitize_text_strict(value, allow_empty=True, max_len=32).lower()
    if stage == "idea":
        return "idea"
    if stage == "launched":
        return "launched"
    return "building"


def _map_existing_stage_to_generate(value: Any) -> str:
    stage = sanitize_text_strict(value, allow_empty=True, max_len=32).upper()
    if stage == "IDEA":
        return "idea"
    if stage in {"EARLY_REVENUE", "SCALING", "MATURE"}:
        return "launched"
    return "building"


def fallback_structure_project_object(raw_input: str, optional_title: str = "") -> Dict[str, Any]:
    legacy = fallback_structure_project(raw_input, user_title=optional_title)
    name = sanitize_text_strict(optional_title, allow_empty=True, max_len=42) or sanitize_text_strict(
        legacy.get("title", ""),
        allow_empty=True,
        max_len=42,
    )
    if not name:
        name = "未命名项目"

    one_liner = sanitize_text_strict(legacy.get("summary", ""), allow_empty=True, max_len=140) or "项目摘要待补充"
    core_problem = sanitize_text_strict(legacy.get("problem_statement", ""), allow_empty=True, max_len=220) or "核心问题待补充"
    solution = sanitize_text_strict(legacy.get("solution_approach", ""), allow_empty=True, max_len=220) or "解决方案待补充"
    target_user = sanitize_text_strict(legacy.get("users", ""), allow_empty=True, max_len=120) or "目标用户待补充"
    use_case = sanitize_text_strict(legacy.get("use_cases", ""), allow_empty=True, max_len=220) or "使用场景待补充"
    monetization = sanitize_text_strict(legacy.get("model_desc", legacy.get("model", "")), allow_empty=True, max_len=120) or "变现方式待补充"
    progress_note = sanitize_text_strict(legacy.get("latest_update", ""), allow_empty=True, max_len=220) or "已完成首次结构化生成"
    key_metric = sanitize_text_strict(legacy.get("stage_metric", ""), allow_empty=True, max_len=120) or "关键指标待补充"

    return {
        "name": name,
        "one_liner": one_liner,
        "core_problem": core_problem,
        "solution": solution,
        "target_user": target_user,
        "use_case": use_case,
        "monetization": monetization,
        "current_stage": _map_existing_stage_to_generate(legacy.get("stage", "")),
        "progress_note": progress_note,
        "key_metric": key_metric,
    }


def structure_project_object(raw_input: str, optional_title: str = "") -> Dict[str, Any]:
    _set_structuring_meta(used_local_structuring=False, api_error="")
    safe_optional_title = sanitize_text_strict(optional_title, allow_empty=True, max_len=42)

    schema: Dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "one_liner": {"type": "string"},
            "core_problem": {"type": "string"},
            "solution": {"type": "string"},
            "target_user": {"type": "string"},
            "use_case": {"type": "string"},
            "monetization": {"type": "string"},
            "current_stage": {"type": "string", "enum": ["idea", "building", "launched"]},
            "progress_note": {"type": "string"},
            "key_metric": {"type": "string"},
        },
        "required": [
            "name",
            "one_liner",
            "core_problem",
            "solution",
            "target_user",
            "use_case",
            "monetization",
            "current_stage",
            "progress_note",
            "key_metric",
        ],
    }

    system_prompt = (
        "你是 OneFile 的项目结构化引擎。"
        "你的任务是把用户输入整理成标准项目对象。"
        "你只能输出符合 schema 的 JSON，不要解释、不要闲聊、不要附加文本。"
        "不要编造不存在的数据，信息不足时使用保守默认值。"
    )
    user_prompt = (
        "请根据输入生成项目对象。\n"
        f"optional_title={safe_optional_title or '(none)'}\n"
        "规则：若 optional_title 非空，name 必须优先使用 optional_title。\n"
        "current_stage 只能是 idea/building/launched。\n\n"
        f"输入文本：\n{raw_input}"
    )

    try:
        client = get_client()
        model_name = get_model_name()
        base_url = get_base_url()
        print(f"[OneFile] provider=hunyuan base_url={base_url} model={model_name}")
        resp = client.responses.create(
            model=model_name,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "onefile_project_object",
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        output_text = _extract_response_output_text(resp)
        parsed = extract_json_object(output_text or "{}")

        result = {
            "name": sanitize_text_strict(parsed.get("name", ""), allow_empty=True, max_len=42),
            "one_liner": sanitize_text_strict(parsed.get("one_liner", ""), allow_empty=True, max_len=140),
            "core_problem": sanitize_text_strict(parsed.get("core_problem", ""), allow_empty=True, max_len=220),
            "solution": sanitize_text_strict(parsed.get("solution", ""), allow_empty=True, max_len=220),
            "target_user": sanitize_text_strict(parsed.get("target_user", ""), allow_empty=True, max_len=120),
            "use_case": sanitize_text_strict(parsed.get("use_case", ""), allow_empty=True, max_len=220),
            "monetization": sanitize_text_strict(parsed.get("monetization", ""), allow_empty=True, max_len=120),
            "current_stage": _normalize_generate_stage(parsed.get("current_stage", "")),
            "progress_note": sanitize_text_strict(parsed.get("progress_note", ""), allow_empty=True, max_len=220),
            "key_metric": sanitize_text_strict(parsed.get("key_metric", ""), allow_empty=True, max_len=120),
        }
        if safe_optional_title:
            result["name"] = safe_optional_title
        if not result["name"]:
            result["name"] = "未命名项目"
        if not result["one_liner"]:
            result["one_liner"] = "项目摘要待补充"
        if not result["core_problem"]:
            result["core_problem"] = "核心问题待补充"
        if not result["solution"]:
            result["solution"] = "解决方案待补充"
        if not result["target_user"]:
            result["target_user"] = "目标用户待补充"
        if not result["use_case"]:
            result["use_case"] = "使用场景待补充"
        if not result["monetization"]:
            result["monetization"] = "变现方式待补充"
        if not result["progress_note"]:
            result["progress_note"] = "已完成首次结构化生成"
        if not result["key_metric"]:
            result["key_metric"] = "关键指标待补充"
        return result
    except Exception as exc:
        _set_structuring_meta(used_local_structuring=True, api_error=str(exc))
        return fallback_structure_project_object(raw_input, optional_title=safe_optional_title)
