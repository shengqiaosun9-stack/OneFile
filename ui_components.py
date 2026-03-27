import json
import os
import uuid
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional

import streamlit as st
import streamlit.components.v1 as components

from ai_service import extract_text_from_uploaded_file, structure_project
from project_model import (
    FORM_TYPE_LABELS,
    FORM_TYPE_VALUES,
    MODEL_TYPE_LABELS,
    MODEL_TYPE_VALUES,
    STAGE_LABELS,
    STAGE_VALUES,
    build_update_entry,
    enrich_generated_project,
    form_type_label,
    get_export_payload,
    get_now_str,
    model_type_label,
    next_action_status_label,
    prepare_project_for_render,
    sanitize_schema,
    stage_label,
    validate_title_candidate,
)
from state_manager import (
    delete_project_by_id,
    get_current_user_id,
    get_recent_project_events,
    get_project_by_id,
    issue_share_cta_token,
    insert_project_top,
    rebuild_ops_signals_from_events,
    save_project_direct_edit,
    set_project_share_state,
    submit_overlay_update,
)
from text_cleaning import clean_text, sanitize_text_strict


def get_share_base_url() -> str:
    configured = (
        os.getenv("ONEFILE_BASE_URL")
        or os.getenv("APP_BASE_URL")
        or os.getenv("STREAMLIT_PUBLIC_URL")
    )
    if not configured:
        try:
            configured = (
                st.secrets.get("ONEFILE_BASE_URL")
                or st.secrets.get("APP_BASE_URL")
                or st.secrets.get("STREAMLIT_PUBLIC_URL")
            )
        except Exception:
            configured = None
    base = str(configured or "").strip().rstrip("/")
    return base


def build_share_url(project_id: str) -> str:
    pid = clean_text(project_id, 24, aggressive=True)
    base = get_share_base_url()
    if base:
        return f"{base}/?project={pid}&view=share"
    return f"/?project={pid}&view=share"


def export_enabled() -> bool:
    raw = (
        os.getenv("ONEFILE_ENABLE_EXPORT")
        or os.getenv("ONEFILE_SHOW_EXPORT")
    )
    if not raw:
        try:
            raw = st.secrets.get("ONEFILE_ENABLE_EXPORT") or st.secrets.get("ONEFILE_SHOW_EXPORT")
        except Exception:
            raw = None
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def ops_debug_enabled() -> bool:
    raw = os.getenv("ONEFILE_DEBUG_EVENTS") or os.getenv("ONEFILE_DEBUG_MODE")
    if not raw:
        try:
            raw = st.secrets.get("ONEFILE_DEBUG_EVENTS") or st.secrets.get("ONEFILE_DEBUG_MODE")
        except Exception:
            raw = None
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


CREATE_TEXT_WARNING_THRESHOLD = 50
CREATE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024


def get_screen_primary_cta(screen: str, is_owner: bool = False) -> str:
    safe = clean_text(screen, 24, aggressive=True).lower()
    if safe == "landing":
        return "进入项目空间"
    if safe == "list_card":
        return "查看完整档案"
    if safe == "detail":
        return "编辑项目" if is_owner else "创建我的项目档案"
    if safe == "share":
        return "继续更新这个项目" if is_owner else "创建我的项目档案"
    return "继续"


def _ensure_create_overlay_state() -> None:
    defaults = {
        "create_dialog_open": False,
        "create_status": "idle",
        "create_draft_title": "",
        "create_draft_text": "",
        "create_clear_requested": False,
        "create_error": None,
        "create_file_error": None,
        "create_submit_nonce": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if st.session_state.get("create_clear_requested") and not st.session_state.get("create_dialog_open"):
        st.session_state.create_draft_title = ""
        st.session_state.create_draft_text = ""
        st.session_state.create_clear_requested = False


def open_create_overlay() -> None:
    _ensure_create_overlay_state()
    _ensure_update_overlay_state()
    st.session_state.update_dialog_open = False
    st.session_state.create_dialog_open = True
    if st.session_state.create_status != "submitting":
        st.session_state.create_status = "editing"
    st.session_state.create_error = None


def _reset_create_overlay_state(clear_draft: bool) -> None:
    if "create_dialog_open" not in st.session_state:
        _ensure_create_overlay_state()
    st.session_state.create_dialog_open = False
    st.session_state.create_status = "idle"
    st.session_state.create_error = None
    st.session_state.create_file_error = None
    st.session_state.create_submit_nonce = None
    if clear_draft:
        # 避免在 widget 已实例化后直接写入同 key
        st.session_state.create_clear_requested = True


def _on_create_overlay_dismiss() -> None:
    _ensure_create_overlay_state()
    if st.session_state.create_status == "submitting":
        return
    # ESC / 遮罩关闭：关闭创建态但保留草稿
    _reset_create_overlay_state(clear_draft=False)


def render_create_overlay() -> None:
    _ensure_create_overlay_state()
    _ensure_update_overlay_state()
    if st.session_state.update_dialog_open:
        return
    if not st.session_state.create_dialog_open:
        return

    dismissible = st.session_state.create_status != "submitting"

    @st.dialog("创建项目档案", width="large", dismissible=dismissible, on_dismiss=_on_create_overlay_dismiss)
    def _render_dialog() -> None:
        _ensure_create_overlay_state()

        status = str(st.session_state.get("create_status", "editing"))
        is_submitting = status == "submitting"

        if st.session_state.get("create_error"):
            st.error(clean_text(st.session_state.create_error, 180))
        if st.session_state.get("create_file_error"):
            st.warning(clean_text(st.session_state.create_file_error, 180))

        st.markdown(
            """
            <div class="editor-shell" style="margin-bottom:12px;">
              <div class="editor-kicker">Create</div>
              <div class="editor-title">自然输入，自动结构化</div>
              <div class="editor-sub">粘贴聊天记录、BP、会议纪要或零散描述，系统将自动生成项目档案。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.text_input(
            "项目名 / 公司名（必填）",
            key="create_draft_title",
            placeholder="例如：星火计划",
            disabled=is_submitting,
        )
        st.text_area(
            "项目描述（核心输入）",
            key="create_draft_text",
            height=240,
            placeholder="可直接粘贴：聊天记录 / BP 文本 / 口述整理 / 零散要点。无需先整理结构。",
            disabled=is_submitting,
        )

        text_clean = sanitize_text_strict(
            st.session_state.get("create_draft_text", ""),
            allow_empty=True,
            max_len=12000,
        )
        title_preview = sanitize_text_strict(
            st.session_state.get("create_draft_title", ""),
            allow_empty=True,
            max_len=42,
        )
        can_submit_create = bool(title_preview and validate_title_candidate(title_preview) and text_clean)
        if text_clean and len("".join(text_clean.split())) < CREATE_TEXT_WARNING_THRESHOLD:
            st.warning("内容较少，生成结果可能不完整")
        if not title_preview:
            st.caption("请先填写项目名/公司名。")
        elif not validate_title_candidate(title_preview):
            st.caption("项目名称建议使用简短清晰的中文、英文或数字组合。")
        elif not text_clean:
            st.caption("请补充项目描述后再创建。")

        uploaded_file = None
        with st.expander("补充文件（可选）", expanded=False):
            uploaded_file = st.file_uploader(
                "上传文件（单文件，<=10MB）",
                type=["pdf", "txt", "md"],
                accept_multiple_files=False,
                key="create_upload_file",
                disabled=is_submitting,
                help="文件为补充输入，主文本仍是创建主输入。",
            )

        action_cols = st.columns([0.2, 0.2, 0.6])
        with action_cols[0]:
            submit_clicked = st.button(
                "创建项目档案",
                type="primary",
                use_container_width=True,
                disabled=is_submitting or not can_submit_create,
                key="create_overlay_submit",
            )
        with action_cols[1]:
            cancel_clicked = st.button(
                "取消",
                use_container_width=True,
                disabled=is_submitting,
                key="create_overlay_cancel",
            )

        if cancel_clicked:
            _reset_create_overlay_state(clear_draft=True)
            st.rerun()

        if submit_clicked and not is_submitting:
            title_clean = sanitize_text_strict(
                st.session_state.get("create_draft_title", ""),
                allow_empty=True,
                max_len=42,
            )
            if not title_clean:
                st.session_state.create_status = "error"
                st.session_state.create_error = "请先填写项目名/公司名。"
                st.rerun()
            if not validate_title_candidate(title_clean):
                st.session_state.create_status = "error"
                st.session_state.create_error = "项目名称格式无效，请使用简短清晰的名称。"
                st.rerun()
            if not text_clean:
                st.session_state.create_status = "error"
                st.session_state.create_error = "请先输入项目描述。"
                st.rerun()

            st.session_state.create_status = "submitting"
            st.session_state.create_submit_nonce = uuid.uuid4().hex
            st.session_state.create_error = None
            st.session_state.create_file_error = None
            st.rerun()

        submit_nonce = st.session_state.get("create_submit_nonce")
        if st.session_state.create_status == "submitting" and submit_nonce:
            try:
                title_clean = sanitize_text_strict(
                    st.session_state.get("create_draft_title", ""),
                    allow_empty=True,
                    max_len=42,
                )
                main_text = sanitize_text_strict(
                    st.session_state.get("create_draft_text", ""),
                    allow_empty=True,
                    max_len=12000,
                )

                file_text = ""
                if uploaded_file is not None:
                    if getattr(uploaded_file, "size", 0) > CREATE_UPLOAD_MAX_BYTES:
                        st.session_state.create_file_error = "上传文件超过 10MB，已忽略该文件。"
                    else:
                        try:
                            file_text = extract_text_from_uploaded_file(uploaded_file)
                        except Exception as exc:
                            st.session_state.create_file_error = f"文件解析失败，已仅使用文本创建：{clean_text(exc, 120)}"

                # 固定顺序合并：主文本在前，文件文本在后
                parts = [main_text.strip()]
                if file_text and file_text.strip():
                    parts.append(file_text.strip())
                composed_input = "\n\n".join(parts).strip()

                if not composed_input:
                    raise ValueError("请输入项目描述后再创建。")

                with st.spinner("正在结构化并创建项目档案..."):
                    schema = structure_project(composed_input, user_title=title_clean)
                    schema = sanitize_schema({**schema, "title": title_clean})
                    project = enrich_generated_project(schema)
                    current_user_id = get_current_user_id()
                    project["desc"] = composed_input
                    project["owner_user_id"] = current_user_id
                    project["updates"] = [
                        build_update_entry(
                            project_id=project.get("id", ""),
                            author_user_id=current_user_id,
                            content=project.get("latest_update", project.get("version_footprint", "")),
                            source="create",
                            created_at=project.get("updated_at", get_now_str()),
                            input_meta={
                                "has_text": bool(main_text),
                                "has_file": bool(file_text and file_text.strip()),
                                "merged_chars": len(composed_input),
                            },
                            next_action_text=(project.get("next_action", {}) or {}).get("text", ""),
                        )
                    ]
                    insert_project_top(project)

                st.session_state.last_generated_id = project["id"]
                st.session_state.selected_project_id = project["id"]
                st.session_state.flash_message = "项目档案已创建，系统已生成并评估下一步动作。"
                st.session_state.create_status = "success"
                _reset_create_overlay_state(clear_draft=True)
                st.rerun()
            except Exception as exc:
                st.session_state.create_status = "error"
                st.session_state.create_error = f"创建失败：{clean_text(exc, 140)}"
                st.session_state.create_submit_nonce = None
                st.rerun()

    _render_dialog()


def _ensure_update_overlay_state() -> None:
    defaults = {
        "update_dialog_open": False,
        "update_target_project_id": "",
        "update_draft_text": "",
        "update_clear_requested": False,
        "update_status": "idle",
        "update_error": None,
        "update_file_error": None,
        "update_submit_nonce": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if st.session_state.get("update_clear_requested") and not st.session_state.get("update_dialog_open"):
        st.session_state.update_draft_text = ""
        st.session_state.update_clear_requested = False


def _reset_update_overlay_state(clear_draft: bool) -> None:
    if "update_dialog_open" not in st.session_state:
        _ensure_update_overlay_state()
    st.session_state.update_dialog_open = False
    st.session_state.update_target_project_id = ""
    st.session_state.update_status = "idle"
    st.session_state.update_error = None
    st.session_state.update_file_error = None
    st.session_state.update_submit_nonce = None
    if clear_draft:
        # 避免在 widget 已实例化后直接写入同 key
        st.session_state.update_clear_requested = True


def open_update_overlay(project_id: str) -> None:
    _ensure_create_overlay_state()
    _ensure_update_overlay_state()
    # 互斥：创建与更新 Overlay 不并存
    st.session_state.create_dialog_open = False
    st.session_state.update_dialog_open = True
    st.session_state.update_target_project_id = clean_text(project_id, 24, aggressive=True)
    if st.session_state.update_status != "submitting":
        st.session_state.update_status = "editing"
    st.session_state.update_error = None
    st.session_state.update_file_error = None


def _on_update_overlay_dismiss() -> None:
    _ensure_update_overlay_state()
    if st.session_state.update_status == "submitting":
        return
    # ESC/遮罩关闭：清空草稿并关闭
    _reset_update_overlay_state(clear_draft=True)


def render_update_overlay() -> None:
    _ensure_update_overlay_state()
    _ensure_create_overlay_state()
    if st.session_state.create_dialog_open:
        return
    if not st.session_state.update_dialog_open:
        return

    project_id = clean_text(st.session_state.get("update_target_project_id", ""), 24, aggressive=True)
    if not project_id:
        _reset_update_overlay_state(clear_draft=True)
        return
    target = get_project_by_id(project_id)
    if not target:
        _reset_update_overlay_state(clear_draft=True)
        st.warning("目标项目不存在，无法更新。")
        return
    target = prepare_project_for_render(target)

    dismissible = st.session_state.update_status != "submitting"

    @st.dialog("更新项目进展", width="large", dismissible=dismissible, on_dismiss=_on_update_overlay_dismiss)
    def _render_dialog() -> None:
        _ensure_update_overlay_state()
        is_submitting = st.session_state.update_status == "submitting"

        if st.session_state.get("update_error"):
            st.error(clean_text(st.session_state.update_error, 180))
        if st.session_state.get("update_file_error"):
            st.warning(clean_text(st.session_state.update_file_error, 180))

        st.markdown(
            f"""
            <div class="editor-shell" style="margin-bottom:12px;">
              <div class="editor-kicker">Update</div>
              <div class="editor-title">{escape(target.get('title', ''))}</div>
              <div class="editor-sub">只需描述发生了什么变化，系统会自动更新完整档案中的当前状态与相关结构字段。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.text_area(
            "最近变化",
            key="update_draft_text",
            height=220,
            placeholder="描述最近的变化，例如：新增客户、开始收费、产品上线新功能…",
            disabled=is_submitting,
        )
        update_text_preview = sanitize_text_strict(
            st.session_state.get("update_draft_text", ""),
            allow_empty=True,
            max_len=280,
        )
        can_submit_update = bool(update_text_preview)
        if not update_text_preview:
            st.caption("请先输入本次更新内容。")

        uploaded_file = None
        with st.expander("补充文件（可选）", expanded=False):
            uploaded_file = st.file_uploader(
                "上传文件（单文件，<=10MB）",
                type=["pdf", "txt", "md"],
                accept_multiple_files=False,
                key="update_upload_file",
                disabled=is_submitting,
                help="文件用于补充上下文，主输入仍是更新文本。",
            )

        action_cols = st.columns([0.2, 0.18, 0.62])
        with action_cols[0]:
            submit_clicked = st.button(
                "提交更新",
                type="primary",
                use_container_width=True,
                disabled=is_submitting or not can_submit_update,
                key="update_overlay_submit",
            )
        with action_cols[1]:
            cancel_clicked = st.button(
                "取消",
                use_container_width=True,
                disabled=is_submitting,
                key="update_overlay_cancel",
            )

        if cancel_clicked:
            _reset_update_overlay_state(clear_draft=True)
            st.rerun()

        if submit_clicked and not is_submitting:
            update_text = sanitize_text_strict(
                st.session_state.get("update_draft_text", ""),
                allow_empty=False,
                max_len=280,
            )
            if not update_text:
                st.session_state.update_status = "error"
                st.session_state.update_error = "请先输入本次更新内容。"
                st.rerun()

            st.session_state.update_status = "submitting"
            st.session_state.update_submit_nonce = uuid.uuid4().hex
            st.session_state.update_error = None
            st.session_state.update_file_error = None
            st.rerun()

        update_nonce = st.session_state.get("update_submit_nonce")
        if st.session_state.update_status == "submitting" and update_nonce:
            try:
                update_text = sanitize_text_strict(
                    st.session_state.get("update_draft_text", ""),
                    allow_empty=False,
                    max_len=280,
                )
                supplemental_text = ""
                if uploaded_file is not None:
                    if getattr(uploaded_file, "size", 0) > CREATE_UPLOAD_MAX_BYTES:
                        st.session_state.update_file_error = "上传文件超过 10MB，已忽略该文件。"
                    else:
                        try:
                            supplemental_text = extract_text_from_uploaded_file(uploaded_file)
                        except Exception as exc:
                            st.session_state.update_file_error = f"文件解析失败，已仅使用文本更新：{clean_text(exc, 120)}"

                with st.spinner("正在分析更新并刷新项目档案..."):
                    submit_overlay_update(project_id, update_text, supplemental_text)

                _reset_update_overlay_state(clear_draft=True)
                st.rerun()
            except Exception as exc:
                st.session_state.update_status = "error"
                st.session_state.update_error = f"更新失败：{clean_text(exc, 140)}"
                st.session_state.update_submit_nonce = None
                st.rerun()

    _render_dialog()


def render_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        :root {
          --tech-blue: #2563EB;
          --accent: #2563EB;
          --success: #16A34A;
          --bg: #F7F8FA;
          --surface: #FFFFFF;
          --line: #E5E7EB;
          --text: #111827;
          --muted: #6B7280;
          --white: #FFFFFF;
        }

        html, body, [class*="css"] {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }

        .stApp {
          background: var(--bg);
          color: var(--text);
        }

        .block-container {
          max-width: 1440px;
          padding-top: 1.2rem;
          padding-bottom: 2rem;
          padding-left: 2rem;
          padding-right: 2rem;
        }

        .onefile-nav {
          position: sticky;
          top: 0;
          z-index: 30;
          background: #fff;
          border: 1px solid var(--line);
          border-radius: 16px;
          padding: 16px 20px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 24px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }

        .nav-brand-wrap {
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .nav-brand-icon {
          width: 32px;
          height: 32px;
          background: var(--tech-blue);
          border-radius: 8px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: white;
          font-size: 18px;
          font-weight: 700;
        }

        .nav-brand-text {
          font-size: 22px;
          font-weight: 700;
          letter-spacing: -0.02em;
        }

        .nav-links {
          display: flex;
          gap: 24px;
          color: #64748B;
          font-size: 15px;
          font-weight: 500;
        }

        .nav-links .active {
          color: var(--tech-blue);
          font-weight: 600;
          border-bottom: 2px solid var(--tech-blue);
          padding-bottom: 10px;
          margin-bottom: -10px;
        }

        .nav-user {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .avatar-dot {
          width: 36px;
          height: 36px;
          border-radius: 999px;
          background: #dbeafe;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: var(--tech-blue);
          font-weight: 700;
        }

        .dashboard-title {
          font-size: 1.5rem;
          line-height: 2rem;
          font-weight: 700;
          color: #0f172a;
        }

        .dashboard-sub {
          color: #64748B;
          font-size: 0.875rem;
          margin-top: 4px;
        }

        .creator-panel {
          background: #fff;
          border: 1px solid var(--line);
          border-radius: 16px;
          padding: 22px;
          margin: 18px 0 24px;
          box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }

        .creator-kicker {
          color: var(--tech-blue);
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-bottom: 6px;
        }

        .card-shell {
          background: #fff;
          border: 1px solid #E2E8F0;
          border-radius: 0.75rem;
          overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          height: 100%;
        }

        .card-shell:hover {
          box-shadow: 0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05);
          transform: translateY(-2px);
        }

        .card-main {
          padding: 24px;
        }

        .card-top {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 16px;
        }

        .card-title {
          font-size: 1.25rem;
          line-height: 1.4;
          font-weight: 700;
          color: #0f172a;
        }

        .status-chip {
          display: inline-flex;
          align-items: center;
          padding: 4px 10px;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          border: 1px solid transparent;
          white-space: nowrap;
        }

        .status-blue { background: #EFF6FF; color: #2563EB; border-color: #DBEAFE; }
        .status-amber { background: #FFFBEB; color: #D97706; border-color: #FDE68A; }
        .status-green { background: #F0FDF4; color: var(--success); border-color: #BBF7D0; }
        .status-purple { background: #FAF5FF; color: #9333EA; border-color: #E9D5FF; }
        .status-slate { background: #F1F5F9; color: #475569; border-color: #CBD5E1; }

        .card-divider {
          border-top: 1px solid #F1F5F9;
          margin: 16px 0;
        }

        .card-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 16px 12px;
          font-size: 14px;
        }

        .card-summary {
          font-size: 14px;
          color: #334155;
          line-height: 1.65;
          margin-top: 4px;
          margin-bottom: 8px;
        }

        .card-kv-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px 12px;
          margin-top: 4px;
        }

        .card-kv {
          border: 1px solid #E2E8F0;
          background: #F8FAFC;
          border-radius: 8px;
          padding: 9px 10px;
        }

        .card-kv-label {
          color: #94A3B8;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          margin-bottom: 4px;
        }

        .card-kv-value {
          color: #1E293B;
          font-size: 13px;
          font-weight: 600;
          line-height: 1.5;
        }

        .line-clamp-2 {
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .meta-line {
          display: flex;
          align-items: center;
          gap: 8px;
          color: #64748B;
        }

        .meta-line strong {
          color: #334155;
          font-weight: 500;
        }

        .metric-bar {
          margin-top: 20px;
          display: flex;
          justify-content: space-between;
          gap: 8px;
          padding: 10px 12px;
          font-size: 12px;
          color: #94A3B8;
          background: #F8FAFC;
          border-radius: 8px;
          border: 1px solid #F1F5F9;
        }

        .timeline-wrap {
          padding: 0 24px 24px;
          margin-top: auto;
        }

        .timeline-title {
          padding-top: 16px;
          border-top: 1px solid #F8FAFC;
          color: #94A3B8;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          margin-bottom: 12px;
        }

        .timeline {
          position: relative;
          padding-left: 18px;
          border-left: 2px solid #F1F5F9;
          margin-left: 4px;
        }

        .timeline-item {
          position: relative;
          margin-bottom: 14px;
        }

        .timeline-dot {
          position: absolute;
          left: -23px;
          top: 3px;
          width: 10px;
          height: 10px;
          border-radius: 999px;
          border: 2px solid #fff;
          background: #CBD5E1;
        }

        .timeline-dot.current {
          background: var(--tech-blue);
        }

        .timeline-row {
          display: flex;
          justify-content: space-between;
          gap: 10px;
          align-items: flex-start;
        }

        .timeline-headline {
          font-size: 12px;
          font-weight: 600;
          color: #0f172a;
        }

        .timeline-headline.faded {
          color: #94A3B8;
          font-weight: 500;
        }

        .timeline-date {
          font-size: 10px;
          color: #94A3B8;
          background: #F1F5F9;
          padding: 2px 6px;
          border-radius: 4px;
          white-space: nowrap;
        }

        .timeline-date.faded {
          background: transparent;
          padding: 0;
          color: #CBD5E1;
        }

        .timeline-desc {
          margin-top: 4px;
          font-size: 11px;
          color: #64748B;
        }

        .archive-panel {
          background: #fff;
          border: 1px solid #E2E8F0;
          border-radius: 16px;
          padding: 24px;
          margin-top: 32px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }

        .archive-kpis {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
          margin: 18px 0 20px;
        }

        .archive-kpi {
          background: #F8FAFC;
          border: 1px solid #E2E8F0;
          border-radius: 12px;
          padding: 14px;
        }

        .archive-kpi-label {
          font-size: 11px;
          color: #94A3B8;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-bottom: 8px;
          font-weight: 700;
        }

        .archive-kpi-value {
          font-size: 16px;
          color: #0f172a;
          font-weight: 700;
        }

        .surface {
          background: #fff;
          border: 1px solid #E2E8F0;
          border-radius: 14px;
          box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }

        .surface-hero {
          padding: 26px 28px;
        }

        .surface-section {
          padding: 22px 24px;
        }

        .section-kicker {
          font-size: 12px;
          color: #94A3B8;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-bottom: 8px;
        }

        .section-value {
          color: #1E293B;
          font-size: 15px;
          line-height: 1.75;
        }

        .section-strong {
          color: #0f172a;
          font-size: 17px;
          line-height: 1.75;
          font-weight: 650;
        }

        .status-callout {
          margin-top: 12px;
          padding: 12px 14px;
          border: 1px solid #E2E8F0;
          border-radius: 10px;
          background: #F8FAFC;
          color: #334155;
          font-size: 14px;
          line-height: 1.65;
        }

        .page-stack {
          max-width: 920px;
          margin: 0 auto;
        }

        .editor-shell {
          background: #fff;
          border: 1px solid #E2E8F0;
          border-radius: 14px;
          padding: 18px;
          box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }

        .editor-kicker {
          font-size: 11px;
          color: #94A3B8;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-bottom: 6px;
        }

        .editor-title {
          font-size: 22px;
          font-weight: 700;
          color: #0f172a;
          line-height: 1.3;
          margin-bottom: 6px;
        }

        .editor-sub {
          color: #64748B;
          font-size: 14px;
          line-height: 1.6;
        }

        .stButton > button {
          min-height: 42px;
          border-radius: 10px;
          border: 1px solid #E2E8F0;
          background: #fff;
          color: #334155;
          padding: 0.625rem 1rem;
          font-weight: 600;
          transition: all 150ms ease;
        }

        .stButton > button:hover {
          background: #F8FAFC;
          border-color: #CBD5E1;
        }

        .stButton > button[kind="primary"] {
          background: var(--accent);
          color: #fff;
          border-color: var(--accent);
          box-shadow: 0 4px 10px rgba(37, 99, 235, 0.18);
        }

        .stButton > button[kind="primary"]:hover {
          background: #1D4ED8;
          border-color: #1D4ED8;
        }

        .stButton > button:focus-visible {
          outline: none;
          box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.24);
        }

        .stTextInput input, .stTextArea textarea {
          border-radius: 10px !important;
          background: #FFFFFF !important;
          border: 1px solid #E2E8F0 !important;
          min-height: 42px;
        }

        .stSelectbox [data-baseweb="select"] > div {
          border-radius: 10px !important;
          background: #FFFFFF !important;
          border-color: #E2E8F0 !important;
        }

        .stTextInput input:focus, .stTextArea textarea:focus {
          border-color: #2563EB !important;
          box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18) !important;
        }

        .status-amber { background: #F8FAFC; color: #334155; border-color: #E2E8F0; }
        .status-purple { background: #F8FAFC; color: #334155; border-color: #E2E8F0; }
        .status-slate { background: #F8FAFC; color: #475569; border-color: #E2E8F0; }

        .card-shell {
          box-shadow: 0 1px 2px rgba(15,23,42,0.06);
          border-radius: 14px;
        }
        .card-shell:hover {
          transform: translateY(-1px);
          box-shadow: 0 10px 20px rgba(15,23,42,0.08);
        }
        .metric-bar {
          background: #F8FAFC;
          border: 1px solid #E5E7EB;
          border-radius: 10px;
        }
        .surface {
          border-radius: 16px;
          box-shadow: 0 1px 3px rgba(15,23,42,0.06);
        }

        .detail-focus-panel {
          margin: 12px 0 14px;
          border: 1px solid #E5E7EB;
          border-radius: 16px;
          background: #FFFFFF;
          box-shadow: 0 1px 3px rgba(15,23,42,0.06);
          padding: 16px;
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
        }
        .detail-focus-item {
          background: #F8FAFC;
          border: 1px solid #E5E7EB;
          border-radius: 12px;
          padding: 12px;
        }
        .detail-focus-kicker {
          font-size: 11px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: #64748B;
          font-weight: 700;
          margin-bottom: 6px;
        }
        .detail-focus-value {
          font-size: 14px;
          line-height: 1.6;
          color: #0F172A;
          font-weight: 600;
        }

        .login-shell {
          width: 100%;
          padding: 2.5rem 0 1rem;
        }
        .login-value-pane {
          background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
          border: 1px solid #E5E7EB;
          border-radius: 20px;
          box-shadow: 0 10px 20px rgba(15,23,42,0.06);
          padding: 28px;
          min-height: 360px;
          display: flex;
          flex-direction: column;
          justify-content: center;
        }
        .login-kicker {
          display: inline-flex;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: #2563EB;
          margin-bottom: 12px;
        }
        .login-title {
          font-size: 38px;
          line-height: 1.18;
          letter-spacing: -0.02em;
          margin: 0;
          color: #0F172A;
          font-weight: 760;
        }
        .login-subtitle {
          font-size: 16px;
          line-height: 1.75;
          color: #475569;
          margin: 16px 0 0;
        }
        .login-trust-line {
          margin-top: 18px;
          padding-top: 14px;
          border-top: 1px solid #E5E7EB;
          font-size: 13px;
          color: #64748B;
        }
        .login-card-pane {
          border: 1px solid #E5E7EB;
          border-radius: 20px;
          background: #FFFFFF;
          box-shadow: 0 10px 20px rgba(15,23,42,0.06);
          padding: 24px;
          min-height: 360px;
          display: flex;
          flex-direction: column;
          justify-content: center;
        }
        .login-card-headline {
          font-size: 24px;
          line-height: 1.25;
          color: #0F172A;
          font-weight: 720;
          margin-bottom: 6px;
        }
        .login-card-desc {
          font-size: 14px;
          line-height: 1.65;
          color: #64748B;
          margin-bottom: 12px;
        }
        .form-inline-error {
          color: #B91C1C;
          font-size: 12px;
          margin: 2px 0 10px;
        }
        .form-inline-hint {
          color: #64748B;
          font-size: 12px;
          margin: 2px 0 10px;
        }

        @media (max-width: 1024px) {
          .nav-links { display: none; }
          .archive-kpis { grid-template-columns: 1fr; }
          .detail-focus-panel { grid-template-columns: 1fr; }
          .login-shell { padding-top: 1rem; }
          .login-title { font-size: 30px; }
          .login-value-pane, .login-card-pane { min-height: auto; padding: 20px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_nav(active_tab: str) -> None:
    project_active = "active" if active_tab == "项目库" else ""
    map_active = "active" if active_tab == "投资地图" else ""
    park_active = "active" if active_tab == "园区动态" else ""
    st.markdown(
        f"""
        <nav class="onefile-nav">
          <div class="nav-brand-wrap">
            <div class="nav-brand-icon">D</div>
            <div class="nav-brand-text">OneFile</div>
            <div class="nav-links">
              <span class="{project_active}">项目库</span>
              <span class="{map_active}">投资地图</span>
              <span class="{park_active}">园区动态</span>
            </div>
          </div>
          <div class="nav-user">
            <span style="font-size:12px;color:#64748B;font-weight:600;">孙圣乔<br><span style="font-size:10px;color:#94A3B8;">管理员</span></span>
            <span class="avatar-dot">S</span>
          </div>
        </nav>
        """,
        unsafe_allow_html=True,
    )


def render_copy_link_button(project_id: str, share_url: str) -> None:
    safe_project = clean_text(project_id, 20, aggressive=True)
    button_id = f"copy-btn-{safe_project}"
    payload = json.dumps(share_url)
    components.html(
        f"""
        <style>
          html, body {{
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: transparent;
          }}
          #wrap-{button_id} {{
            width: 100%;
            height: 56px;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            margin: 0;
            box-sizing: border-box;
          }}
        </style>
        <div id="wrap-{button_id}">
        <button id="{button_id}" style="
          width:100%;
          height:42px;
          line-height:42px;
          box-sizing:border-box;
          margin:0;
          border-radius:8px;
          border:1px solid #E2E8F0;
          background:#FFFFFF;
          color:#334155;
          padding:0 14px;
          font-size:14px;
          font-weight:500;
          cursor:pointer;">
          复制链接
        </button>
        </div>
        <script>
          (function() {{
            const btn = document.getElementById("{button_id}");
            if (!btn || btn.dataset.bound === "1") return;
            btn.dataset.bound = "1";
            btn.addEventListener("click", async function() {{
              let text = {payload};
              if (typeof text === "string" && text.startsWith("/")) {{
                text = window.location.origin + text;
              }}
              let ok = false;
              try {{
                if (navigator.clipboard && window.isSecureContext) {{
                  await navigator.clipboard.writeText(text);
                  ok = true;
                }}
              }} catch (e) {{}}
              if (!ok) {{
                const input = document.createElement("textarea");
                input.value = text;
                input.style.position = "fixed";
                input.style.opacity = "0";
                document.body.appendChild(input);
                input.focus();
                input.select();
                try {{
                  ok = document.execCommand("copy");
                }} catch (e) {{
                  ok = false;
                }}
                document.body.removeChild(input);
              }}
              if (ok) {{
                btn.textContent = "已复制";
                btn.style.background = "#EFF6FF";
                btn.style.color = "#2D7AFF";
                btn.style.borderColor = "#DBEAFE";
              }} else {{
                btn.textContent = "复制失败";
                btn.style.background = "#FEF2F2";
                btn.style.color = "#DC2626";
                btn.style.borderColor = "#FECACA";
              }}
            }});
          }})();
        </script>
        """,
        height=86,
    )


def _truncate_text(value: Any, limit: int) -> str:
    text = sanitize_text_strict(value, allow_empty=True, max_len=max(limit * 2, limit))
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def _parse_display_dt(value: Any) -> Optional[datetime]:
    text = sanitize_text_strict(value, allow_empty=True, max_len=24)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _public_progress_text(project: Dict[str, Any]) -> str:
    progress_eval = project.get("progress_eval", {}) if isinstance(project.get("progress_eval", {}), dict) else {}
    status = sanitize_text_strict(progress_eval.get("status", ""), allow_empty=True, max_len=20).lower()
    if status == "advancing":
        return "项目近期持续推进"
    if status == "stalled":
        return "项目近期更新较少，正在收敛下一步"
    return "项目正在验证关键方向"


def _activity_snapshot(project: Dict[str, Any]) -> Dict[str, str]:
    ops = project.get("ops_signals", {}) if isinstance(project.get("ops_signals", {}), dict) else {}
    updates_7d = max(int(ops.get("updates_7d", 0) or 0), 0)
    last_activity = sanitize_text_strict(
        ops.get("last_activity_at", project.get("updated_at", "")),
        allow_empty=True,
        max_len=24,
    )
    updated_at = sanitize_text_strict(project.get("updated_at", ""), allow_empty=True, max_len=24) or "-"
    now_dt = datetime.now()
    last_dt = _parse_display_dt(last_activity)
    days_since = None
    if last_dt:
        days_since = max((now_dt.date() - last_dt.date()).days, 0)

    if updates_7d >= 3 and days_since is not None and days_since <= 3:
        badge = "近期持续更新"
    elif updates_7d >= 1 and days_since is not None and days_since <= 7:
        badge = "近期有进展"
    elif days_since is not None and days_since <= 14:
        badge = "轻度活跃"
    else:
        badge = "更新较少"

    if days_since is None:
        freshness = "活跃度数据待补充"
    elif days_since == 0:
        freshness = "今天有更新"
    elif days_since == 1:
        freshness = "1天前更新"
    else:
        freshness = f"{days_since}天前更新"

    return {
        "badge": badge,
        "freshness": freshness,
        "last_updated": updated_at,
    }


def render_card(project: Dict[str, Any], highlight_id: str) -> None:
    project = prepare_project_for_render(project)
    current_user_id = clean_text(get_current_user_id(), 40, aggressive=True)
    owner_user_id = clean_text(project.get("owner_user_id", ""), 40, aggressive=True)
    is_owner = bool(current_user_id and owner_user_id and current_user_id == owner_user_id)
    share_state = project.get("share", {}) if isinstance(project.get("share", {}), dict) else {}
    is_public = bool(share_state.get("is_public", False))
    status_class = f"status-chip status-{project.get('status_theme', 'blue')}"
    border_style = "2px solid #DBEAFE" if project.get("id") == highlight_id else "1px solid #E2E8F0"
    box_shadow = "0 10px 18px rgba(45,122,255,0.14)" if project.get("id") == highlight_id else None
    shell_style = f"border:{border_style};"
    if box_shadow:
        shell_style += f"box-shadow:{box_shadow};"
    summary_short = _truncate_text(project.get("summary", ""), 92) or "项目定位待补充"
    latest_short = _truncate_text(project.get("latest_update", ""), 80) or "暂无最新进展"
    next_action = project.get("next_action", {}) if isinstance(project.get("next_action", {}), dict) else {}
    next_action_text = _truncate_text(next_action.get("text", ""), 82) or "正在梳理下一步关键动作"
    stage_text = project.get("stage_label", stage_label(project.get("stage", "")))
    users_text = _truncate_text(project.get("users", ""), 56) or "待补充"
    form_text = _truncate_text(project.get("form_type_label", project.get("shape", "")), 36) or "待补充"
    model_text = _truncate_text(project.get("model_desc", project.get("model", "")), 52) or "待补充"
    activity = _activity_snapshot(project)
    private_badge_html = (
        "<div style='margin-top:6px;'><span class='status-chip status-slate'>我的私有</span></div>"
        if is_owner and not is_public
        else ""
    )

    share_url = build_share_url(project["id"])
    top_actions = st.columns([0.84, 0.16])
    with top_actions[1]:
        with st.popover("⋯", use_container_width=True):
            if st.button("打开分享页", key=f"open_share_{project['id']}", use_container_width=True):
                st.query_params["project"] = project["id"]
                st.query_params["view"] = "share"
                st.rerun()
            if is_owner:
                render_copy_link_button(project["id"], share_url)
            else:
                if st.button("创建我的项目档案", key=f"clone_from_card_{project['id']}", use_container_width=True):
                    st.query_params.clear()
                    st.query_params["action"] = "create"
                    st.rerun()
    st.markdown(
        f"""
        <div class="card-shell" style="{shell_style}">
          <div class="card-main">
            <div class="card-top">
              <h2 class="card-title">{escape(project.get("title", ""))}</h2>
              <span class="{status_class}">{escape(project.get("status_tag", ""))}</span>
            </div>
            {private_badge_html}
            <div class="card-summary line-clamp-2">{escape(summary_short)}</div>
            <div class="card-divider"></div>
            <div style="display:grid;grid-template-columns:1fr;gap:8px;">
              <div style="font-size:12px;color:#64748B;"><strong>用户：</strong>{escape(users_text)}</div>
              <div style="font-size:12px;color:#64748B;"><strong>产品形态：</strong>{escape(form_text)}</div>
              <div style="font-size:12px;color:#64748B;" class="line-clamp-1"><strong>商业模式：</strong>{escape(model_text)}</div>
            </div>
            <div class="metric-bar" style="display:block;margin-top:12px;">
              <div style="font-size:11px;color:#94A3B8;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:8px;">当前阶段与状态</div>
              <div style="font-size:13px;color:#334155;"><strong>阶段：</strong>{escape(stage_text)}</div>
              <div style="font-size:13px;color:#334155;margin-top:6px;" class="line-clamp-2"><strong>当前状态：</strong>{escape(latest_short)}</div>
            </div>
            <div class="metric-bar" style="display:block;margin-top:10px;">
              <div style="font-size:11px;color:#94A3B8;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:8px;">活跃信号</div>
              <div style="font-size:13px;color:#334155;"><strong>{escape(activity.get("badge", ""))}</strong> · {escape(activity.get("freshness", ""))}</div>
              <div style="font-size:12px;color:#64748B;margin-top:4px;"><strong>最近更新时间：</strong>{escape(activity.get("last_updated", "-"))}</div>
            </div>
            <div class="metric-bar" style="display:block;margin-top:10px;">
              <div style="font-size:11px;color:#94A3B8;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:8px;">创始人当前下一步</div>
              <div style="font-size:13px;color:#334155;" class="line-clamp-2">{escape(next_action_text)}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_cols = st.columns([1.0, 1.0])
    with action_cols[0]:
        if st.button(get_screen_primary_cta("list_card", is_owner=is_owner), key=f"view_{project['id']}", type="primary"):
            st.session_state.selected_project_id = project["id"]
            st.query_params["project"] = project["id"]
            st.query_params["view"] = "detail"
            st.rerun()
    with action_cols[1]:
        if is_owner:
            if st.button("更新项目进展", key=f"update_{project['id']}"):
                st.session_state.selected_project_id = project["id"]
                open_update_overlay(project["id"])
                st.rerun()
        else:
            if st.button("创建我的项目档案", key=f"cta_create_{project['id']}"):
                st.query_params.clear()
                st.query_params["action"] = "create"
                st.rerun()


def render_cards_grid(projects: List[Dict[str, Any]], highlight_id: str) -> None:
    if not projects:
        st.info("当前筛选条件下暂无项目。")
        return
    for start in range(0, len(projects), 3):
        row = st.columns(3)
        for col, project in zip(row, projects[start : start + 3]):
            with col:
                render_card(project, highlight_id)


def render_archive_panel(project: Dict[str, Any]) -> None:
    project = prepare_project_for_render(project)
    summary_text = sanitize_text_strict(project.get("summary", ""), allow_empty=True, max_len=180) or "项目定位待补充"
    stage_text = project.get("stage_label", stage_label(project.get("stage", "")))
    form_text = project.get("form_type_label", form_type_label(project.get("form_type", "")))
    model_text = project.get("model_type_label", model_type_label(project.get("model_type", "")))
    latest_update = sanitize_text_strict(project.get("latest_update", ""), allow_empty=True, max_len=280) or "暂无最新进展"
    current_tension = sanitize_text_strict(project.get("current_tension", ""), allow_empty=True, max_len=200) or "当前关键焦点待补充"
    next_action = project.get("next_action", {}) if isinstance(project.get("next_action", {}), dict) else {}
    next_action_text = sanitize_text_strict(next_action.get("text", ""), allow_empty=True, max_len=180) or "正在梳理下一步关键动作"
    problem_text = sanitize_text_strict(project.get("problem_statement", ""), allow_empty=True, max_len=280) or "待补充"
    solution_text = sanitize_text_strict(project.get("solution_approach", ""), allow_empty=True, max_len=280) or "待补充"
    users_text = sanitize_text_strict(project.get("users", ""), allow_empty=True, max_len=140) or "待补充"
    use_cases_text = sanitize_text_strict(project.get("use_cases", ""), allow_empty=True, max_len=220) or "待补充"
    model_desc_text = sanitize_text_strict(project.get("model_desc", project.get("model", "")), allow_empty=True, max_len=160) or "待补充"
    activity = _activity_snapshot(project)
    progress_public = _public_progress_text(project)
    recent_change_short = _truncate_text(latest_update, 120)

    st.markdown(
        f"""
        <div class="surface surface-hero">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:18px;">
            <div>
              <div class="section-kicker" style="color:#2D7AFF;">完整档案</div>
              <div style="font-size:30px;font-weight:760;color:#0f172a;line-height:1.2;">{escape(project.get("title", ""))}</div>
              <div style="margin-top:10px;color:#475569;font-size:15px;line-height:1.7;">{escape(summary_text)}</div>
            </div>
            <div>
              <span class="status-chip status-{project.get('status_theme', 'blue')}">{escape(project.get("status_tag", ""))}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="surface surface-section" style="margin-top:12px;">
          <div class="section-kicker">Core Structured Overview</div>
          <div class="archive-kpis">
            <div class="archive-kpi"><div class="archive-kpi-label">当前阶段</div><div class="archive-kpi-value">{escape(stage_text)}</div></div>
            <div class="archive-kpi"><div class="archive-kpi-label">产品形态</div><div class="archive-kpi-value">{escape(form_text)}</div></div>
            <div class="archive-kpi"><div class="archive-kpi-label">商业模式</div><div class="archive-kpi-value">{escape(model_text)}</div></div>
            <div class="archive-kpi"><div class="archive-kpi-label">模式描述</div><div class="archive-kpi-value">{escape(model_desc_text)}</div></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px;">
            <div>
              <div style="font-size:12px;color:#64748B;font-weight:700;margin-bottom:6px;">问题定义</div>
              <div class="section-value">{escape(problem_text)}</div>
            </div>
            <div>
              <div style="font-size:12px;color:#64748B;font-weight:700;margin-bottom:6px;">解决方案</div>
              <div class="section-value">{escape(solution_text)}</div>
            </div>
          </div>
          <div style="margin-top:12px;">
            <div style="font-size:12px;color:#64748B;font-weight:700;margin-bottom:6px;">目标用户</div>
            <div class="section-value">{escape(users_text)}</div>
            <div style="font-size:12px;color:#64748B;font-weight:700;margin:10px 0 6px;">典型场景</div>
            <div class="section-value">{escape(use_cases_text)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="surface surface-section">
          <div class="section-kicker">Current Stage / Current Status</div>
          <div class="status-callout"><strong>当前阶段：</strong>{escape(stage_text)}</div>
          <div class="status-callout" style="margin-top:8px;"><strong>状态解读：</strong>{escape(progress_public)}</div>
          <div class="status-callout" style="margin-top:8px;"><strong>当前进展：</strong>{escape(latest_update)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="surface surface-section" style="margin-top:12px;">
          <div class="section-kicker">Lightweight Proof of Life</div>
          <div class="status-callout"><strong>{escape(activity.get("badge", ""))}</strong> · {escape(activity.get("freshness", ""))}</div>
          <div class="status-callout" style="margin-top:8px;"><strong>最近更新时间：</strong>{escape(activity.get("last_updated", "-"))}</div>
          <div class="status-callout" style="margin-top:8px;"><strong>最近变化摘要：</strong>{escape(recent_change_short)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="surface surface-section" style="margin-top:12px;">
          <div class="section-kicker">Current Key Focus</div>
          <div class="section-value">{escape(current_tension)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="surface surface-section" style="margin-top:12px;">
          <div class="section-kicker">Founder Current Next Move</div>
          <div class="section-value">{escape(next_action_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if export_enabled():
        payload = get_export_payload(project)
        st.markdown("#### 结构化导出（内部）")
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")
        st.download_button(
            "下载 JSON 档案",
            data=json.dumps(payload, ensure_ascii=False, indent=2),
            file_name=f"onefile_{project.get('id', 'project')}.json",
            mime="application/json",
            use_container_width=True,
        )

def render_project_detail_page(project: Dict[str, Any]) -> None:
    project = prepare_project_for_render(project)
    project_id = clean_text(project.get("id", ""), 24, aggressive=True)
    current_user_id = clean_text(get_current_user_id(), 40, aggressive=True)
    owner_user_id = clean_text(project.get("owner_user_id", ""), 40, aggressive=True)
    is_owner = bool(current_user_id and owner_user_id and current_user_id == owner_user_id)
    share_url = build_share_url(project_id)
    share_state = project.get("share", {}) if isinstance(project.get("share", {}), dict) else {}
    is_public = bool(share_state.get("is_public", False))
    header_cols = st.columns([0.16, 0.16, 0.68])
    with header_cols[0]:
        if st.button("← 项目库", key=f"back_list_{project_id}", use_container_width=True):
            st.query_params.clear()
            st.rerun()
    with header_cols[1]:
        primary_detail_cta = get_screen_primary_cta("detail", is_owner=is_owner)
        if is_owner:
            if st.button(primary_detail_cta, key=f"detail_edit_{project_id}", type="primary", use_container_width=True):
                st.query_params["project"] = project_id
                st.query_params["view"] = "edit"
                st.query_params.pop("mode", None)
                st.rerun()
        else:
            if st.button(primary_detail_cta, key=f"detail_create_entry_{project_id}", type="primary", use_container_width=True):
                st.query_params.clear()
                st.query_params["action"] = "create"
                st.rerun()
    with header_cols[2]:
        with st.popover("⋯", use_container_width=False):
            if st.button("打开分享页", key=f"detail_share_{project_id}", use_container_width=True):
                st.query_params["project"] = project_id
                st.query_params["view"] = "share"
                st.rerun()
            if is_owner:
                toggle_label = "设为私有" if is_public else "设为公开"
                if st.button(toggle_label, key=f"toggle_share_{project_id}", use_container_width=True):
                    try:
                        set_project_share_state(project_id, not is_public)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"分享状态更新失败：{clean_text(exc, 120)}")
                render_copy_link_button(project_id, share_url)
                if st.button("删除项目", key=f"delete_project_{project_id}", use_container_width=True):
                    st.session_state.delete_confirm_id = project_id
                    st.rerun()
            else:
                if st.button("创建我的项目档案", key=f"detail_create_from_public_{project_id}", use_container_width=True):
                    st.query_params.clear()
                    st.query_params["action"] = "create"
                    st.rerun()

    state_label = "公开" if is_public else "私有"
    focus_stage = project.get("stage_label", stage_label(project.get("stage", "")))
    focus_status = sanitize_text_strict(project.get("latest_update", ""), allow_empty=True, max_len=120) or "暂无最新进展"
    focus_next = sanitize_text_strict(
        ((project.get("next_action", {}) or {}).get("text", "") if isinstance(project.get("next_action", {}), dict) else ""),
        allow_empty=True,
        max_len=120,
    ) or "正在梳理下一步关键动作"
    st.markdown(
        f"""
        <section class="detail-focus-panel">
          <div class="detail-focus-item">
            <div class="detail-focus-kicker">Current Stage</div>
            <div class="detail-focus-value">{escape(focus_stage)}</div>
          </div>
          <div class="detail-focus-item">
            <div class="detail-focus-kicker">Current Status</div>
            <div class="detail-focus-value">{escape(focus_status)}</div>
          </div>
          <div class="detail-focus-item">
            <div class="detail-focus-kicker">Next Action</div>
            <div class="detail-focus-value">{escape(focus_next)}</div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"分享状态：{state_label}")

    if is_owner and st.session_state.get("delete_confirm_id") == project_id:
        st.warning("确认删除该项目档案？此操作不可恢复。")
        confirm_cols = st.columns([0.18, 0.18, 0.64])
        with confirm_cols[0]:
            if st.button("确认删除", key=f"confirm_delete_{project_id}", type="primary", use_container_width=True):
                try:
                    delete_project_by_id(project_id)
                    st.query_params.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(f"删除失败：{clean_text(exc, 120)}")
        with confirm_cols[1]:
            if st.button("取消", key=f"cancel_delete_{project_id}", use_container_width=True):
                st.session_state.delete_confirm_id = None
                st.rerun()
    render_archive_panel(project)

    if ops_debug_enabled():
        with st.expander("调试：事件账本（最近12条）", expanded=False):
            if st.button("重建 ops_signals", key=f"rebuild_ops_{project_id}", use_container_width=False):
                changed = rebuild_ops_signals_from_events(persist=True)
                st.success("ops_signals 已重建。" if changed else "ops_signals 无需重建。")
                st.rerun()
            recent_events = get_recent_project_events(project_id, limit=12)
            if not recent_events:
                st.caption("暂无事件记录。")
            for item in recent_events:
                event_type = sanitize_text_strict(item.get("event_type", ""), allow_empty=True, max_len=32) or "-"
                event_ts = sanitize_text_strict(item.get("ts", ""), allow_empty=True, max_len=24) or "-"
                source = sanitize_text_strict(item.get("source", ""), allow_empty=True, max_len=24) or "-"
                payload = item.get("payload", {})
                payload_text = sanitize_text_strict(json.dumps(payload, ensure_ascii=False), allow_empty=True, max_len=220)
                st.markdown(
                    f"- `{event_ts}` · `{event_type}` · `{source}`  \n  {escape(payload_text)}",
                    unsafe_allow_html=False,
                )


def render_edit_page(project: Optional[Dict[str, Any]], mode: str = "update") -> None:
    del mode
    if not project:
        st.warning("编辑页仅支持已有项目。请先在项目库创建项目。")
        if st.button("返回项目库", type="primary"):
            st.query_params.clear()
            st.rerun()
        return

    target_project = prepare_project_for_render(project)
    project_id = clean_text(target_project.get("id", ""), 24, aggressive=True)
    state_suffix = project_id or "edit"

    defaults = {
        f"direct_title_{state_suffix}": sanitize_text_strict(target_project.get("title", ""), allow_empty=True, max_len=42),
        f"direct_summary_{state_suffix}": sanitize_text_strict(target_project.get("summary", ""), allow_empty=True, max_len=140),
        f"direct_problem_{state_suffix}": sanitize_text_strict(target_project.get("problem_statement", ""), allow_empty=True, max_len=220),
        f"direct_solution_{state_suffix}": sanitize_text_strict(target_project.get("solution_approach", ""), allow_empty=True, max_len=220),
        f"direct_users_{state_suffix}": sanitize_text_strict(target_project.get("users", ""), allow_empty=True, max_len=120),
        f"direct_use_cases_{state_suffix}": sanitize_text_strict(target_project.get("use_cases", ""), allow_empty=True, max_len=220),
        f"direct_latest_{state_suffix}": sanitize_text_strict(target_project.get("latest_update", ""), allow_empty=True, max_len=280),
        f"direct_model_desc_{state_suffix}": sanitize_text_strict(
            target_project.get("model_desc", target_project.get("model", "")),
            allow_empty=True,
            max_len=120,
        ),
        f"direct_stage_{state_suffix}": target_project.get("stage", "BUILDING"),
        f"direct_model_type_{state_suffix}": target_project.get("model_type", "UNKNOWN"),
        f"direct_form_type_{state_suffix}": target_project.get("form_type", "OTHER"),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    st.markdown(
        f"""
        <div class="editor-shell" style="margin-bottom:14px;">
          <div class="editor-kicker">Edit Project</div>
          <div class="editor-title">{escape(target_project.get("title", ""))}</div>
          <div class="editor-sub">人工精修完整档案字段，保存后会同步到卡片、详情页与分享页。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    title_cols = st.columns([0.72, 0.14, 0.14])
    with title_cols[0]:
        st.text_input("项目名称", key=f"direct_title_{state_suffix}", placeholder="请输入项目名称")
    with title_cols[1]:
        save_clicked = st.button("保存项目", type="primary", use_container_width=True, key=f"save_direct_{state_suffix}")
    with title_cols[2]:
        cancel_clicked = st.button("取消", use_container_width=True, key=f"cancel_direct_{state_suffix}")

    edit_cols = st.columns([0.7, 0.3], gap="large")
    with edit_cols[0]:
        st.markdown('<div class="editor-shell"><div class="editor-kicker">Core Narrative</div></div>', unsafe_allow_html=True)
        st.text_area("一句话定位（Summary）", key=f"direct_summary_{state_suffix}", height=110, placeholder="用一句话说明项目是什么。")
        st.text_area("问题定义", key=f"direct_problem_{state_suffix}", height=160, placeholder="这个项目要解决什么问题？")
        st.text_area("解决方案", key=f"direct_solution_{state_suffix}", height=160, placeholder="你如何解决这个问题？")
        st.text_input("目标用户", key=f"direct_users_{state_suffix}", placeholder="核心用户是谁？")
        st.text_area("典型场景", key=f"direct_use_cases_{state_suffix}", height=130, placeholder="用户在什么场景下使用？")
        st.text_area("最新进展", key=f"direct_latest_{state_suffix}", height=130, placeholder="请描述当前最新进展。")
    with edit_cols[1]:
        st.markdown('<div class="editor-shell"><div class="editor-kicker">Structured Metadata</div></div>', unsafe_allow_html=True)
        st.selectbox(
            "阶段",
            STAGE_VALUES,
            key=f"direct_stage_{state_suffix}",
            format_func=lambda x: STAGE_LABELS.get(x, x),
        )
        st.selectbox(
            "商业模式类型",
            MODEL_TYPE_VALUES,
            key=f"direct_model_type_{state_suffix}",
            format_func=lambda x: MODEL_TYPE_LABELS.get(x, x),
        )
        st.selectbox(
            "产品形态",
            FORM_TYPE_VALUES,
            key=f"direct_form_type_{state_suffix}",
            format_func=lambda x: FORM_TYPE_LABELS.get(x, x),
        )
        st.text_area("商业模式描述", key=f"direct_model_desc_{state_suffix}", height=120, placeholder="补充对外可读的商业模式描述。")

    if cancel_clicked:
        st.query_params["project"] = project_id
        st.query_params["view"] = "detail"
        st.query_params.pop("mode", None)
        st.rerun()

    if save_clicked:
        try:
            payload = {
                "title": st.session_state.get(f"direct_title_{state_suffix}", ""),
                "problem_statement": st.session_state.get(f"direct_problem_{state_suffix}", ""),
                "solution_approach": st.session_state.get(f"direct_solution_{state_suffix}", ""),
                "summary": st.session_state.get(f"direct_summary_{state_suffix}", ""),
                "users": st.session_state.get(f"direct_users_{state_suffix}", ""),
                "use_cases": st.session_state.get(f"direct_use_cases_{state_suffix}", ""),
                "latest_update": st.session_state.get(f"direct_latest_{state_suffix}", ""),
                "model_desc": st.session_state.get(f"direct_model_desc_{state_suffix}", ""),
                "stage": st.session_state.get(f"direct_stage_{state_suffix}", "BUILDING"),
                "model_type": st.session_state.get(f"direct_model_type_{state_suffix}", "UNKNOWN"),
                "form_type": st.session_state.get(f"direct_form_type_{state_suffix}", "OTHER"),
            }
            save_project_direct_edit(project_id, payload)
            st.query_params["project"] = project_id
            st.query_params["view"] = "detail"
            st.query_params.pop("mode", None)
            st.rerun()
        except Exception as exc:
            st.error(f"保存失败：{clean_text(exc, 140)}")


def render_share_page(project: Dict[str, Any], access_granted: bool = True, owner_preview: bool = False) -> None:
    project = prepare_project_for_render(project)
    current_user_id = clean_text(get_current_user_id(), 40, aggressive=True)
    is_logged_in = bool(current_user_id)
    owner_user_id = clean_text(project.get("owner_user_id", ""), 40, aggressive=True)
    is_owner = bool(current_user_id and owner_user_id and current_user_id == owner_user_id)
    project_id = clean_text(project.get("id", ""), 24, aggressive=True)
    if not access_granted:
        if is_logged_in:
            top_cols = st.columns([0.2, 0.8])
            with top_cols[0]:
                if st.button("← 返回项目库", key="share_private_back_list", use_container_width=True):
                    st.query_params.clear()
                    st.rerun()
        st.markdown(
            """
            <div class="page-stack">
              <section class="surface surface-hero">
                <div style="font-size:32px;font-weight:800;color:#0f172a;line-height:1.2;">该项目暂未公开</div>
                <div style="font-size:16px;line-height:1.7;color:#475569;margin-top:10px;">
                  该分享链接当前处于私有状态。你可以返回 OneFile 创建并维护自己的项目档案。
                </div>
              </section>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cta_cols = st.columns([0.3, 0.7])
        with cta_cols[0]:
            if st.button(
                get_screen_primary_cta("share", is_owner=False),
                type="primary",
                use_container_width=True,
                key="share_private_create_cta",
            ):
                cta_token = issue_share_cta_token(
                    project_id=project_id,
                    source="share_page_private",
                    cta="start_project",
                    ref="private_gate",
                    access_granted=False,
                )
                st.query_params.clear()
                st.query_params["action"] = "create"
                if cta_token:
                    st.query_params["cta_token"] = cta_token
                st.rerun()
        return

    summary = sanitize_text_strict(project.get("summary", ""), allow_empty=True, max_len=140) or "项目定位待补充"
    stage_text = escape(project.get("stage_label", stage_label(project.get("stage", ""))))
    form_text = escape(project.get("form_type_label", ""))
    model_text = escape(project.get("model_type_label", model_type_label(project.get("model_type", ""))))
    latest = sanitize_text_strict(project.get("latest_update", ""), allow_empty=True, max_len=180)
    next_action = project.get("next_action", {}) if isinstance(project.get("next_action", {}), dict) else {}
    next_move = sanitize_text_strict(next_action.get("text", ""), allow_empty=True, max_len=180) or "创始人正在梳理下一步关键动作。"
    problem_text = sanitize_text_strict(project.get("problem_statement", ""), allow_empty=True, max_len=220) or "问题定义待补充"
    solution_text = sanitize_text_strict(project.get("solution_approach", ""), allow_empty=True, max_len=220) or "解决方案待补充"
    users_text = sanitize_text_strict(project.get("users", ""), allow_empty=True, max_len=120) or "目标用户待补充"
    use_cases_text = sanitize_text_strict(project.get("use_cases", ""), allow_empty=True, max_len=220) or "典型场景待补充"
    activity = _activity_snapshot(project)
    recent_change_short = _truncate_text(latest or "暂无最新进展", 120)
    public_status = _public_progress_text(project)

    if is_logged_in:
        top_cols = st.columns([0.2, 0.8])
        with top_cols[0]:
            if st.button("← 返回项目库", key=f"share_back_list_{project.get('id', '')}", use_container_width=True):
                st.query_params.clear()
                st.rerun()

    st.markdown(
        f"""
        <div class="page-stack">
          <section class="surface surface-hero">
            {"<div style='display:inline-flex;padding:4px 10px;border-radius:999px;background:#FEF3C7;color:#92400E;font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:12px;'>私有预览（仅你可见）</div>" if owner_preview and not project.get("share", {}).get("is_public", False) else ""}
            <div style="font-size:40px;font-weight:800;color:#0f172a;line-height:1.12;margin-bottom:12px;">{escape(project.get("title", ""))}</div>
            <div style="font-size:20px;line-height:1.65;color:#1e293b;font-weight:650;margin-bottom:14px;">{escape(summary)}</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <span class="status-chip status-{project.get('status_theme', 'blue')}">{stage_text}</span>
              <span class="status-chip status-slate">{form_text}</span>
              <span class="status-chip status-slate">{model_text}</span>
            </div>
          </section>

          <section class="surface surface-section" style="margin-top:14px;">
            <div class="section-kicker">Problem</div>
            <div class="section-strong">{escape(problem_text)}</div>
          </section>

          <section class="surface surface-section" style="margin-top:12px;">
            <div class="section-kicker">Solution</div>
            <div class="section-strong">{escape(solution_text)}</div>
          </section>

          <section class="surface surface-section" style="margin-top:12px;">
            <div class="section-kicker">Users & Use Cases</div>
            <div class="section-value"><strong>目标用户：</strong>{escape(users_text)}</div>
            <div class="section-value" style="margin-top:8px;"><strong>使用场景：</strong>{escape(use_cases_text)}</div>
          </section>

          <section class="surface surface-section" style="margin-top:12px;">
            <div class="section-kicker">Current Status</div>
            <div class="status-callout">{escape(latest or "暂无最新进展")}</div>
          </section>

          <section class="surface surface-section" style="margin-top:12px;">
            <div class="section-kicker">Founder Current Next Move</div>
            <div class="status-callout">{escape(next_move)}</div>
          </section>

          <section class="surface surface-section" style="margin-top:12px;">
            <div class="section-kicker">Proof of Life</div>
            <div class="status-callout"><strong>{escape(activity.get("badge", ""))}</strong> · {escape(activity.get("freshness", ""))}</div>
            <div class="status-callout" style="margin-top:8px;"><strong>最近更新时间：</strong>{escape(activity.get("last_updated", "-"))}</div>
            <div class="status-callout" style="margin-top:8px;"><strong>状态解读：</strong>{escape(public_status)}</div>
            <div class="status-callout" style="margin-top:8px;"><strong>最近变化摘要：</strong>{escape(recent_change_short)}</div>
          </section>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cta_cols = st.columns([0.3, 0.7])
    with cta_cols[0]:
        share_cta_label = get_screen_primary_cta("share", is_owner=is_owner)
        if is_owner:
            if st.button(share_cta_label, type="primary", use_container_width=True, key=f"share_update_cta_{project_id}"):
                cta_token = issue_share_cta_token(
                    project_id=project_id,
                    source="share_page_owner",
                    cta="continue_update",
                    ref="share_hero",
                    access_granted=True,
                )
                st.query_params.clear()
                st.query_params["project"] = project_id
                st.query_params["view"] = "detail"
                if cta_token:
                    st.query_params["cta_token"] = cta_token
                st.rerun()
        else:
            if st.button(share_cta_label, type="primary", use_container_width=True, key=f"share_create_cta_{project_id}"):
                cta_token = issue_share_cta_token(
                    project_id=project_id,
                    source="share_page_public",
                    cta="start_project",
                    ref="share_hero",
                    access_granted=True,
                )
                st.query_params.clear()
                st.query_params["action"] = "create"
                if cta_token:
                    st.query_params["cta_token"] = cta_token
                st.rerun()


def render_filters(projects: List[Dict[str, Any]]) -> Dict[str, str]:
    all_tech = sorted({tech for project in projects for tech in project.get("tech_stack", [])})
    stage_options = [stage for stage in STAGE_VALUES if any(p.get("stage") == stage for p in projects)]
    form_options = [form for form in FORM_TYPE_VALUES if any(p.get("form_type") == form for p in projects)]
    model_options = [model for model in MODEL_TYPE_VALUES if any(p.get("model_type") == model for p in projects)]
    st.markdown(
        """
        <div style="height:10px;"></div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns([0.17, 0.17, 0.17, 0.17, 0.32])
    with cols[0]:
        tech_filter = st.selectbox("技术栈", ["全部技术"] + all_tech)
    with cols[1]:
        stage_filter = st.selectbox(
            "阶段",
            ["所有阶段"] + stage_options,
            format_func=lambda x: STAGE_LABELS.get(x, x),
        )
    with cols[2]:
        form_filter = st.selectbox(
            "产品形态",
            ["所有形态"] + form_options,
            format_func=lambda x: FORM_TYPE_LABELS.get(x, x),
        )
    with cols[3]:
        model_filter = st.selectbox(
            "商业模式",
            ["所有模式"] + model_options,
            format_func=lambda x: MODEL_TYPE_LABELS.get(x, x),
        )
    with cols[4]:
        keyword = st.text_input("搜索", placeholder="搜索项目、团队或技术关键词...")
    return {
        "tech": tech_filter,
        "stage": stage_filter,
        "form": form_filter,
        "model": model_filter,
        "keyword": keyword,
    }
