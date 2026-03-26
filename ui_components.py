import json
import os
import uuid
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
    get_project_by_id,
    insert_project_top,
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


CREATE_TEXT_WARNING_THRESHOLD = 50
CREATE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024


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
        if text_clean and len("".join(text_clean.split())) < CREATE_TEXT_WARNING_THRESHOLD:
            st.warning("内容较少，生成结果可能不完整")

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
                disabled=is_submitting,
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
                        )
                    ]
                    insert_project_top(project)

                st.session_state.last_generated_id = project["id"]
                st.session_state.selected_project_id = project["id"]
                st.session_state.flash_message = "项目档案已创建，已生成下一动作。可继续推进。"
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
                disabled=is_submitting,
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
          --tech-blue: #2D7AFF;
          --bg: #F5F7FA;
          --line: #E2E8F0;
          --text: #1E293B;
          --muted: #64748B;
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

        .status-blue { background: #EFF6FF; color: #2D7AFF; border-color: #DBEAFE; }
        .status-amber { background: #FFFBEB; color: #D97706; border-color: #FDE68A; }
        .status-green { background: #F0FDF4; color: #16A34A; border-color: #BBF7D0; }
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
          border-radius: 0.5rem;
          border: 1px solid #E2E8F0;
          background: #fff;
          color: #334155;
          padding: 0.625rem 1rem;
          font-weight: 500;
          transition: all 150ms ease;
        }

        .stButton > button:hover {
          background: #F8FAFC;
          border-color: #CBD5E1;
        }

        .stButton > button[kind="primary"] {
          background: var(--tech-blue);
          color: #fff;
          border-color: var(--tech-blue);
          box-shadow: 0 1px 2px rgba(0,0,0,0.06);
        }

        .stButton > button[kind="primary"]:hover {
          background: #2563EB;
          border-color: #2563EB;
        }

        .stTextInput input, .stTextArea textarea {
          border-radius: 0.5rem !important;
          background: #F8FAFC !important;
          border: 1px solid #E2E8F0 !important;
        }

        .stSelectbox [data-baseweb="select"] > div {
          border-radius: 0.5rem !important;
          background: #F8FAFC !important;
          border-color: #E2E8F0 !important;
        }

        @media (max-width: 1024px) {
          .nav-links { display: none; }
          .archive-kpis { grid-template-columns: 1fr; }
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


def render_card(project: Dict[str, Any], highlight_id: str) -> None:
    project = prepare_project_for_render(project)
    status_class = f"status-chip status-{project.get('status_theme', 'blue')}"
    border_style = "2px solid #DBEAFE" if project.get("id") == highlight_id else "1px solid #E2E8F0"
    box_shadow = "0 10px 18px rgba(45,122,255,0.14)" if project.get("id") == highlight_id else None
    shell_style = f"border:{border_style};"
    if box_shadow:
        shell_style += f"box-shadow:{box_shadow};"
    summary_short = _truncate_text(project.get("summary", ""), 92) or "项目定位待补充"
    latest_short = _truncate_text(project.get("latest_update", ""), 78) or "暂无最新进展"
    next_action = project.get("next_action", {}) if isinstance(project.get("next_action", {}), dict) else {}
    next_action_text = _truncate_text(next_action.get("text", ""), 78) or "待生成下一动作"
    next_action_status = next_action_status_label(next_action.get("status", "open"))

    share_url = build_share_url(project["id"])
    top_actions = st.columns([0.84, 0.16])
    with top_actions[1]:
        with st.popover("⋯", use_container_width=True):
            if st.button("打开分享页", key=f"open_share_{project['id']}", use_container_width=True):
                st.query_params["project"] = project["id"]
                st.query_params["view"] = "share"
                st.rerun()
            render_copy_link_button(project["id"], share_url)
    st.markdown(
        f"""
        <div class="card-shell" style="{shell_style}">
          <div class="card-main">
            <div class="card-top">
              <h2 class="card-title">{escape(project.get("title", ""))}</h2>
              <span class="{status_class}">{escape(project.get("status_tag", ""))}</span>
            </div>
            <div class="card-summary line-clamp-2">{escape(summary_short)}</div>
            <div class="card-divider"></div>
            <div class="card-kv-grid">
              <div class="card-kv">
                <div class="card-kv-label">用户</div>
                <div class="card-kv-value line-clamp-2">{escape(project.get("users", ""))}</div>
              </div>
              <div class="card-kv">
                <div class="card-kv-label">产品形态</div>
                <div class="card-kv-value line-clamp-2">{escape(project.get("form_type_label", project.get("shape", "")))}</div>
              </div>
              <div class="card-kv">
                <div class="card-kv-label">商业模式</div>
                <div class="card-kv-value line-clamp-2">{escape(project.get("model_desc", project.get("model", "")))}</div>
              </div>
              <div class="card-kv">
                <div class="card-kv-label">阶段</div>
                <div class="card-kv-value">{escape(project.get("stage_label", stage_label(project.get("stage", ""))))}</div>
              </div>
            </div>
            <div class="metric-bar" style="display:block;">
              <div style="font-size:11px;color:#94A3B8;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:8px;">当前状态</div>
              <div style="font-size:13px;color:#334155;" class="line-clamp-2"><strong>最新进展：</strong>{escape(latest_short)}</div>
              <div style="font-size:13px;color:#334155;margin-top:6px;" class="line-clamp-2"><strong>下一动作（{escape(next_action_status)}）：</strong>{escape(next_action_text)}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_cols = st.columns([1.0, 1.0])
    with action_cols[0]:
        if st.button("查看完整档案", key=f"view_{project['id']}", type="primary"):
            st.session_state.selected_project_id = project["id"]
            st.query_params["project"] = project["id"]
            st.query_params["view"] = "detail"
            st.rerun()
    with action_cols[1]:
        if st.button("更新项目进展", key=f"update_{project['id']}"):
            st.session_state.selected_project_id = project["id"]
            open_update_overlay(project["id"])
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
        <div class="archive-kpis">
          <div class="archive-kpi"><div class="archive-kpi-label">当前阶段</div><div class="archive-kpi-value">{escape(project.get("stage_label", stage_label(project.get("stage", ""))))}</div></div>
          <div class="archive-kpi"><div class="archive-kpi-label">产品形态</div><div class="archive-kpi-value">{escape(project.get("form_type_label", ""))}</div></div>
          <div class="archive-kpi"><div class="archive-kpi-label">商业模式类型</div><div class="archive-kpi-value">{escape(project.get("model_type_label", model_type_label(project.get("model_type", ""))))}</div></div>
          <div class="archive-kpi"><div class="archive-kpi-label">更新时间</div><div class="archive-kpi-value">{escape(project.get("updated_at", "-"))}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    latest_update = sanitize_text_strict(project.get("latest_update", ""), allow_empty=True, max_len=280) or "暂无最新进展"
    current_tension = sanitize_text_strict(project.get("current_tension", ""), allow_empty=True, max_len=180) or "当前张力待识别"
    next_action = project.get("next_action", {}) if isinstance(project.get("next_action", {}), dict) else {}
    next_action_text = sanitize_text_strict(next_action.get("text", ""), allow_empty=True, max_len=180) or "待生成下一动作"
    next_action_state = next_action_status_label(next_action.get("status", "open"))
    problem_text = sanitize_text_strict(project.get("problem_statement", ""), allow_empty=True, max_len=280) or "待补充"
    solution_text = sanitize_text_strict(project.get("solution_approach", ""), allow_empty=True, max_len=280) or "待补充"
    users_text = sanitize_text_strict(project.get("users", ""), allow_empty=True, max_len=140) or "待补充"
    use_cases_text = sanitize_text_strict(project.get("use_cases", ""), allow_empty=True, max_len=220) or "待补充"

    st.markdown(
        f"""
        <div class="surface surface-section">
          <div class="section-kicker">当前状态</div>
          <div class="status-callout">{escape(latest_update)}</div>
          <div class="status-callout" style="margin-top:8px;"><strong>当前张力：</strong>{escape(current_tension)}</div>
          <div class="status-callout" style="margin-top:8px;"><strong>下一动作（{escape(next_action_state)}）：</strong>{escape(next_action_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="surface surface-section" style="margin-top:12px;">
          <div class="section-kicker">Problem & Solution</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
            <div>
              <div style="font-size:12px;color:#64748B;font-weight:700;margin-bottom:6px;">问题定义</div>
              <div class="section-value">{escape(problem_text)}</div>
            </div>
            <div>
              <div style="font-size:12px;color:#64748B;font-weight:700;margin-bottom:6px;">解决方案</div>
              <div class="section-value">{escape(solution_text)}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="surface surface-section" style="margin-top:12px;">
          <div class="section-kicker">Users & Use Cases</div>
          <div style="font-size:12px;color:#64748B;font-weight:700;margin-bottom:6px;">目标用户</div>
          <div class="section-value">{escape(users_text)}</div>
          <div style="font-size:12px;color:#64748B;font-weight:700;margin:12px 0 6px;">典型场景</div>
          <div class="section-value">{escape(use_cases_text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    updates = project.get("updates", [])
    if isinstance(updates, list) and updates:
        with st.expander("演进轨迹", expanded=False):
            for item in updates[:5]:
                if not isinstance(item, dict):
                    continue
                update_date = sanitize_text_strict(item.get("created_at", ""), allow_empty=True, max_len=24) or "-"
                update_content = sanitize_text_strict(item.get("content", ""), allow_empty=True, max_len=160) or "版本记录已更新"
                update_kind = sanitize_text_strict(item.get("kind", ""), allow_empty=True, max_len=20).lower()
                update_kind_label = {
                    "hypothesis": "假设",
                    "action": "动作",
                    "result": "结果",
                    "note": "记录",
                }.get(update_kind, "记录")
                st.markdown(
                    f"""
                    <div style="padding:10px 12px;border:1px solid #E2E8F0;border-radius:10px;background:#F8FAFC;margin-bottom:8px;">
                      <div style="font-size:12px;color:#94A3B8;font-weight:600;margin-bottom:4px;">{escape(update_date)} · {escape(update_kind_label)}</div>
                      <div style="font-size:14px;color:#1E293B;line-height:1.65;">{escape(update_content)}</div>
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
    share_url = build_share_url(project_id)
    share_state = project.get("share", {}) if isinstance(project.get("share", {}), dict) else {}
    is_public = bool(share_state.get("is_public", False))
    header_cols = st.columns([0.16, 0.16, 0.68])
    with header_cols[0]:
        if st.button("← 项目库", key=f"back_list_{project_id}", use_container_width=True):
            st.query_params.clear()
            st.rerun()
    with header_cols[1]:
        if st.button("编辑项目", key=f"detail_edit_{project_id}", type="primary", use_container_width=True):
            st.query_params["project"] = project_id
            st.query_params["view"] = "edit"
            st.query_params.pop("mode", None)
            st.rerun()
    with header_cols[2]:
        with st.popover("⋯", use_container_width=False):
            toggle_label = "设为私有" if is_public else "设为公开"
            if st.button(toggle_label, key=f"toggle_share_{project_id}", use_container_width=True):
                try:
                    set_project_share_state(project_id, not is_public)
                    st.rerun()
                except Exception as exc:
                    st.error(f"分享状态更新失败：{clean_text(exc, 120)}")
            if st.button("打开分享页", key=f"detail_share_{project_id}", use_container_width=True):
                st.query_params["project"] = project_id
                st.query_params["view"] = "share"
                st.rerun()
            render_copy_link_button(project_id, share_url)
            if st.button("删除项目", key=f"delete_project_{project_id}", use_container_width=True):
                st.session_state.delete_confirm_id = project_id
                st.rerun()

    state_label = "公开" if is_public else "私有"
    st.caption(f"分享状态：{state_label}")

    if st.session_state.get("delete_confirm_id") == project_id:
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
    if not access_granted:
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
            if st.button("创建我的项目档案", type="primary", use_container_width=True, key="share_private_create_cta"):
                st.query_params.clear()
                st.query_params["action"] = "create"
                st.rerun()
        return

    summary = sanitize_text_strict(project.get("summary", ""), allow_empty=True, max_len=140) or "项目定位待补充"
    stage_text = escape(project.get("stage_label", stage_label(project.get("stage", ""))))
    form_text = escape(project.get("form_type_label", ""))
    model_text = escape(project.get("model_type_label", model_type_label(project.get("model_type", ""))))
    latest = sanitize_text_strict(project.get("latest_update", ""), allow_empty=True, max_len=180)
    problem_text = sanitize_text_strict(project.get("problem_statement", ""), allow_empty=True, max_len=220) or "问题定义待补充"
    solution_text = sanitize_text_strict(project.get("solution_approach", ""), allow_empty=True, max_len=220) or "解决方案待补充"
    users_text = sanitize_text_strict(project.get("users", ""), allow_empty=True, max_len=120) or "目标用户待补充"
    use_cases_text = sanitize_text_strict(project.get("use_cases", ""), allow_empty=True, max_len=220) or "典型场景待补充"

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
        </div>
        """,
        unsafe_allow_html=True,
    )
    cta_cols = st.columns([0.3, 0.7])
    with cta_cols[0]:
        if st.button("创建我的项目档案", type="primary", use_container_width=True, key=f"share_create_cta_{project.get('id', '')}"):
            st.query_params.clear()
            st.query_params["action"] = "create"
            st.rerun()


def render_pending_actions_panel(projects: List[Dict[str, Any]]) -> None:
    if not projects:
        return
    st.markdown(
        """
        <div class="archive-panel" style="margin-top: 14px; margin-bottom: 16px; padding: 16px 18px;">
          <div style="font-size:12px;color:#2D7AFF;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">待推进项目</div>
          <div style="font-size:14px;color:#475569;margin-top:4px;">以下项目存在未完成动作，建议先推进并记录结果。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for idx, project in enumerate(projects):
        item = prepare_project_for_render(project)
        next_action = item.get("next_action", {}) if isinstance(item.get("next_action", {}), dict) else {}
        action_text = _truncate_text(next_action.get("text", ""), 92) or "待生成下一动作"
        action_status = next_action_status_label(next_action.get("status", "open"))
        cols = st.columns([0.62, 0.18, 0.2], gap="small")
        with cols[0]:
            st.markdown(
                f"""
                <div style="padding:10px 12px;border:1px solid #E2E8F0;border-radius:10px;background:#FFFFFF;">
                  <div style="font-size:14px;font-weight:700;color:#0f172a;">{escape(item.get("title", ""))}</div>
                  <div style="font-size:13px;color:#475569;margin-top:4px;"><strong>{escape(action_status)}：</strong>{escape(action_text)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with cols[1]:
            if st.button("查看档案", key=f"pending_view_{item.get('id','')}_{idx}", use_container_width=True):
                st.query_params["project"] = item["id"]
                st.query_params["view"] = "detail"
                st.rerun()
        with cols[2]:
            if st.button("立即更新", key=f"pending_update_{item.get('id','')}_{idx}", type="primary", use_container_width=True):
                st.session_state.selected_project_id = item["id"]
                open_update_overlay(item["id"])
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
