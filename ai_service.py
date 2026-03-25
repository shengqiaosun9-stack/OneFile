import json
import os
import re
from io import BytesIO
from html import unescape
from typing import Any, Dict, List

import streamlit as st
from openai import OpenAI
from pypdf import PdfReader

from project_model import (
    get_export_payload,
    parse_count_token,
    parse_update_signals,
    resolve_title,
    sanitize_schema,
)
from text_cleaning import clean_text, sanitize_text_strict


def extract_text_from_uploaded_file(uploaded_file: Any) -> str:
    if not uploaded_file:
        return ""
    name = str(getattr(uploaded_file, "name", "") or "").lower()
    data = uploaded_file.getvalue()
    if not data:
        return ""

    if name.endswith(".pdf"):
        try:
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
        os.getenv("DASHSCOPE_MODEL")
        or os.getenv("QWEN_MODEL")
        or os.getenv("MODEL_NAME")
    )
    if not model:
        try:
            model = (
                st.secrets.get("DASHSCOPE_MODEL")
                or st.secrets.get("QWEN_MODEL")
                or st.secrets.get("MODEL_NAME")
            )
        except Exception:
            model = None
    return str(model or "qwen3.5-flash").strip()


def get_client() -> OpenAI:
    api_key = (
        os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("QWEN_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        try:
            api_key = (
                st.secrets.get("DASHSCOPE_API_KEY")
                or st.secrets.get("QWEN_API_KEY")
                or st.secrets.get("OPENAI_API_KEY")
            )
        except Exception:
            api_key = None
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ValueError("未检测到 API Key。请设置环境变量 DASHSCOPE_API_KEY，或在 .streamlit/secrets.toml 中配置 DASHSCOPE_API_KEY。")

    return OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
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
    lowered = text.lower()
    if "已上线" in text or "正式上线" in text or "上线" in text:
        return "产品已上线"
    if "mvp" in lowered:
        return "MVP 已上线"
    if "公测" in text:
        return "公测阶段"
    if "内测" in text or "beta" in lowered:
        return "内测阶段"
    if "融资" in text:
        return "融资中"
    return "早期阶段"


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

    title = extract_field_by_prefix(raw, [r"项目名称", r"项目名", r"name"], 42)
    if not title and lines:
        title = clean_text(lines[0], 42)
    title = resolve_title(user_title, raw, title)

    tech_stack = extract_tech_stack_heuristic(raw)
    users = extract_field_by_prefix(raw, [r"目标用户", r"用户", r"target users?"], 44) or "待补充"
    model = extract_field_by_prefix(raw, [r"商业模式", r"模式", r"business model"], 34) or "待补充"
    stage = infer_stage_from_text(safe_text)
    summary = extract_field_by_prefix(raw, [r"一句话亮点", r"亮点", r"summary"], 78)
    if not summary:
        summary = sanitize_text_strict(safe_text, allow_empty=False, max_len=78)

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
            "tech_stack": tech_stack,
            "users": users,
            "model": model,
            "stage": stage,
            "version_footprint": "v1.0 建立项目档案并完成首轮结构化",
            "summary": summary,
            "team_text": team_text,
            "stage_metric": stage_metric,
        }
    )


def build_update_input(project: Dict[str, Any], update_text: str) -> str:
    context = {
        **get_export_payload(project),
        "team_text": project.get("team_text", ""),
        "stage_metric": project.get("stage_metric", ""),
    }
    return (
        "这是一个已存在的项目档案，请根据最新进展更新结构化字段。"
        f"\n\n当前档案：\n{json.dumps(context, ensure_ascii=False)}"
        f"\n\n最新进展：\n{update_text}"
    )


def structure_project(raw_input: str, user_title: str = "") -> Dict[str, Any]:
    st.session_state.used_local_structuring = False
    st.session_state.last_api_error = None
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
7) 在不影响 7 个标准字段的前提下，尽量补充 team_text 和 stage_metric 两个内部结构化字段。

JSON Schema:
{{
  "title": "项目名称",
  "tech_stack": ["技术1", "技术2"],
  "users": "目标用户一句话",
  "model": "商业模式",
  "stage": "当前阶段",
  "version_footprint": "版本足迹",
  "summary": "一句话亮点",
  "team_text": "核心团队：X人（可为空字符串）",
  "stage_metric": "当前阶段：关键进展一句话（可为空字符串）"
}}

项目输入：
{raw_input}
""".strip()

    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=get_model_name(),
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        parsed = extract_json_object(resp.choices[0].message.content or "{}")
        schema = sanitize_schema(parsed)
        schema["title"] = resolve_title(user_title, raw_input, schema.get("title", ""))
        return sanitize_schema(schema)
    except Exception as exc:
        st.session_state.used_local_structuring = True
        st.session_state.last_api_error = clean_text(exc, 180)
        return fallback_structure_project(raw_input, user_title=user_title)
