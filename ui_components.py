import json
import os
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
    enrich_generated_project,
    get_export_payload,
    model_type_label,
    prepare_project_for_render,
    sanitize_schema,
    stage_label,
    validate_title_candidate,
)
from state_manager import (
    commit_update_preview,
    delete_project_by_id,
    generate_update_preview,
    insert_project_top,
    rename_project_title,
    save_project_from_edit,
    undo_last_update,
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


def render_card(project: Dict[str, Any], highlight_id: str) -> None:
    project = prepare_project_for_render(project)
    status_class = f"status-chip status-{project.get('status_theme', 'blue')}"
    border_style = "2px solid #DBEAFE" if project.get("id") == highlight_id else "1px solid #E2E8F0"
    box_shadow = "0 10px 18px rgba(45,122,255,0.14)" if project.get("id") == highlight_id else None
    shell_style = f"border:{border_style};"
    if box_shadow:
        shell_style += f"box-shadow:{box_shadow};"

    st.markdown(
        f"""
        <div class="card-shell" style="{shell_style}">
          <div class="card-main">
            <div class="card-top">
              <h2 class="card-title">{escape(project.get("title", ""))}</h2>
              <span class="{status_class}">{escape(project.get("status_tag", ""))}</span>
            </div>
            <div class="card-divider"></div>
            <div class="card-grid">
              <div class="meta-line"><span>🧠</span><span><span style="color:#64748B;">技术栈:</span> <strong>{escape(', '.join(project.get("tech_stack", [])))}</strong></span></div>
              <div class="meta-line"><span>👥</span><span><span style="color:#64748B;">用户:</span> <strong>{escape(project.get("users", ""))}</strong></span></div>
              <div class="meta-line"><span>📦</span><span><span style="color:#64748B;">形态:</span> <strong>{escape(project.get("form_type_label", project.get("shape", "")))}</strong></span></div>
              <div class="meta-line"><span>💰</span><span><span style="color:#64748B;">模式:</span> <strong>{escape(project.get("model_desc", project.get("model", "")))}</strong></span></div>
            </div>
            <div class="metric-bar" style="display:block;">
              <div style="font-size:11px;color:#94A3B8;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:8px;">当前状态</div>
              <div style="font-size:13px;color:#334155;margin-bottom:6px;"><strong>阶段：</strong>{escape(project.get("stage_label", stage_label(project.get("stage", ""))))}</div>
              <div style="font-size:13px;color:#334155;"><strong>最新进展：</strong>{escape(project.get("latest_update", ""))}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    share_url = build_share_url(project["id"])
    action_cols = st.columns([1.0, 1.0, 0.9, 0.9])
    with action_cols[0]:
        if st.button("查看完整档案", key=f"view_{project['id']}"):
            st.session_state.selected_project_id = project["id"]
            st.query_params["project"] = project["id"]
            st.query_params["view"] = "detail"
            st.rerun()
    with action_cols[1]:
        if st.button("更新项目进展", key=f"update_{project['id']}"):
            st.session_state.selected_project_id = project["id"]
            st.query_params["project"] = project["id"]
            st.query_params["view"] = "edit"
            st.query_params.pop("mode", None)
            st.rerun()
    with action_cols[2]:
        render_copy_link_button(project["id"], share_url)
    with action_cols[3]:
        if st.button("打开分享页", key=f"open_share_{project['id']}"):
            st.query_params["project"] = project["id"]
            st.query_params["view"] = "share"
            st.rerun()
    st.caption(share_url if share_url.startswith("http") else f"当前应用链接：{share_url}")


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
    project_id = project.get("id", "")
    share_url = build_share_url(project_id)
    st.markdown(
        f"""
        <div class="archive-panel">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:18px;">
            <div>
              <div style="font-size:12px;color:#2D7AFF;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px;">完整档案</div>
              <div style="font-size:28px;font-weight:700;color:#0f172a;line-height:1.2;">{escape(project.get("title", ""))}</div>
              <div style="margin-top:8px;color:#64748B;font-size:14px;">{escape(project.get("summary", ""))}</div>
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
          <div class="archive-kpi"><div class="archive-kpi-label">分享链接</div><div class="archive-kpi-value">{escape(share_url)}</div></div>
          <div class="archive-kpi"><div class="archive-kpi-label">更新时间</div><div class="archive-kpi-value">{escape(project.get("updated_at", "-"))}</div></div>
          <div class="archive-kpi"><div class="archive-kpi-label">最新进展</div><div class="archive-kpi-value">{escape(project.get("latest_update", ""))}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("#### 项目名称维护")
    rename_cols = st.columns([0.78, 0.22])
    with rename_cols[0]:
        edited_title = st.text_input(
            "项目名称",
            value=project.get("title", ""),
            key=f"title_edit_{project_id}",
            label_visibility="collapsed",
            placeholder="输入项目名称",
        )
    with rename_cols[1]:
        if st.button("保存名称", key=f"save_title_{project_id}", use_container_width=True):
            try:
                rename_project_title(project_id, edited_title)
                st.rerun()
            except Exception as exc:
                st.error(f"保存失败：{clean_text(exc, 120)}")

    st.markdown("#### Structured Metadata")
    meta_cols = st.columns([0.33, 0.33, 0.34])
    with meta_cols[0]:
        st.markdown(f"**项目名称**\n\n{escape(project.get('title', ''))}")
        st.markdown(f"**当前阶段**\n\n{escape(project.get('stage_label', stage_label(project.get('stage', ''))))}")
    with meta_cols[1]:
        st.markdown(f"**产品形态**\n\n{escape(project.get('form_type_label', ''))}")
        st.markdown(f"**商业模式类型**\n\n{escape(project.get('model_type_label', model_type_label(project.get('model_type', ''))))}")
    with meta_cols[2]:
        model_desc = sanitize_text_strict(project.get("model_desc", project.get("model", "")), allow_empty=True, max_len=120)
        pricing = sanitize_text_strict(project.get("pricing_strategy", ""), allow_empty=True, max_len=24) or "未设置"
        st.markdown(f"**商业模式描述**\n\n{escape(model_desc or '待补充')}")
        st.markdown(f"**定价策略**\n\n{escape(pricing)}")

    st.markdown("#### Problem & Solution")
    st.markdown(f"**问题定义**\n\n{escape(sanitize_text_strict(project.get('problem_statement', ''), allow_empty=True, max_len=220) or '待补充')}")
    st.markdown(f"**解决方案**\n\n{escape(sanitize_text_strict(project.get('solution_approach', ''), allow_empty=True, max_len=220) or '待补充')}")

    st.markdown("#### Users & Use Cases")
    users_text = sanitize_text_strict(project.get("users", ""), allow_empty=True, max_len=120) or "待补充"
    use_cases_text = sanitize_text_strict(project.get("use_cases", ""), allow_empty=True, max_len=180) or "待补充"
    st.markdown(f"**目标用户**\n\n{escape(users_text)}")
    st.markdown(f"**典型场景**\n\n{escape(use_cases_text)}")

    st.markdown("#### Current Status")
    latest_update = sanitize_text_strict(project.get("latest_update", ""), allow_empty=True, max_len=220) or "暂无最新进展"
    st.info(latest_update)

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

    st.markdown("#### 项目操作")
    action_cols = st.columns([0.18, 0.82])
    with action_cols[0]:
        if st.button("删除项目", key=f"delete_project_{project_id}", use_container_width=True):
            st.session_state.delete_confirm_id = project_id
            st.rerun()

    if st.session_state.get("delete_confirm_id") == project_id:
        st.warning("确认删除该项目档案？此操作不可恢复。")
        confirm_cols = st.columns([0.18, 0.18, 0.64])
        with confirm_cols[0]:
            if st.button("确认删除", key=f"confirm_delete_{project_id}", type="primary", use_container_width=True):
                try:
                    delete_project_by_id(project_id)
                    st.rerun()
                except Exception as exc:
                    st.error(f"删除失败：{clean_text(exc, 120)}")
        with confirm_cols[1]:
            if st.button("取消", key=f"cancel_delete_{project_id}", use_container_width=True):
                st.session_state.delete_confirm_id = None
                st.rerun()


def render_project_detail_page(project: Dict[str, Any]) -> None:
    project_id = clean_text(project.get("id", ""), 24, aggressive=True)
    header_cols = st.columns([0.18, 0.18, 0.18, 0.46])
    with header_cols[0]:
        if st.button("返回项目库", key=f"back_list_{project_id}", use_container_width=True):
            st.query_params.clear()
            st.rerun()
    with header_cols[1]:
        if st.button("进入编辑态", key=f"detail_edit_{project_id}", use_container_width=True):
            st.query_params["project"] = project_id
            st.query_params["view"] = "edit"
            st.query_params.pop("mode", None)
            st.rerun()
    with header_cols[2]:
        if st.button("打开分享页", key=f"detail_share_{project_id}", use_container_width=True):
            st.query_params["project"] = project_id
            st.query_params["view"] = "share"
            st.rerun()
    render_archive_panel(project)


def render_edit_page(project: Optional[Dict[str, Any]], mode: str = "update") -> None:
    is_create = mode == "create" or not project
    target_project = prepare_project_for_render(project) if project else {}
    project_id = clean_text(target_project.get("id", ""), 24, aggressive=True)
    default_title = sanitize_text_strict(target_project.get("title", ""), allow_empty=True, max_len=42)
    default_desc = sanitize_text_strict(target_project.get("desc", ""), allow_empty=True, max_len=6000)
    if not default_desc and project:
        default_desc = sanitize_text_strict(
            f"项目摘要：{target_project.get('summary', '')}\n目标用户：{target_project.get('users', '')}\n商业模式：{target_project.get('model_desc', target_project.get('model', ''))}",
            allow_empty=True,
            max_len=6000,
        )
    default_latest = sanitize_text_strict(target_project.get("latest_update", ""), allow_empty=True, max_len=280)

    title_for_header = default_title or "新建项目"
    st.markdown(
        f"""
        <div class="creator-panel">
          <div class="creator-kicker">Edit Mode</div>
          <div style="font-size:24px;font-weight:700;color:#0f172a;margin-bottom:6px;">{escape(title_for_header)}</div>
          <div style="color:#64748B;font-size:14px;">
            {'创建项目档案：请先填写项目名称与描述，随后可持续完善。' if is_create else '更新项目档案：你正在编辑同一项目对象，保存后卡片、完整档案与分享页将同步更新。'}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if project and project_id in st.session_state.undo_snapshots:
        undo_cols = st.columns([0.22, 0.78])
        with undo_cols[0]:
            if st.button("撤销最近一次编辑", key=f"undo_edit_{project_id}", use_container_width=True):
                try:
                    undo_last_update(project_id)
                    st.query_params["project"] = project_id
                    st.query_params["view"] = "detail"
                    st.rerun()
                except Exception as exc:
                    st.error(f"撤销失败：{clean_text(exc, 120)}")

    with st.form(f"edit_form_{project_id or 'new'}", clear_on_submit=False):
        title_input = st.text_input(
            "项目名称（必填）",
            value=default_title if not is_create else "",
            placeholder="例如：星火计划",
        )
        desc_input = st.text_area(
            "项目描述（必填）",
            value=default_desc,
            height=220,
            placeholder="输入项目背景、目标用户、产品方案、商业模式等信息。",
        )
        latest_update_input = st.text_area(
            "当前状态（可选）",
            value=default_latest,
            height=110,
            placeholder="例如：产品已上线并新增3个客户。",
        )
        st.caption("保存时会先清洗文本，再进入同一套 AI 结构化流程；详情页展示的字段为唯一事实源。")

        action_cols = st.columns([0.2, 0.16, 0.64])
        with action_cols[0]:
            submit = st.form_submit_button(
                "创建项目档案" if is_create else "保存项目档案",
                type="primary",
                use_container_width=True,
            )
        with action_cols[1]:
            cancel = st.form_submit_button("取消", use_container_width=True)

    if cancel:
        if is_create:
            st.query_params.clear()
        else:
            st.query_params["project"] = project_id
            st.query_params["view"] = "detail"
        st.rerun()

    if submit:
        try:
            with st.spinner("正在结构化并保存档案..."):
                saved_id = save_project_from_edit(
                    project_id if not is_create else None,
                    title_input,
                    desc_input,
                    latest_update_input,
                )
            st.query_params["project"] = saved_id
            st.query_params["view"] = "detail"
            st.query_params.pop("mode", None)
            st.rerun()
        except Exception as exc:
            st.error(f"保存失败：{clean_text(exc, 140)}")


def render_creator_panel() -> None:
    st.markdown(
        """
        <div class="creator-panel">
          <div class="creator-kicker">AI Structuring Engine</div>
          <div style="font-size:26px;font-weight:700;color:#0f172a;margin-bottom:6px;">30 秒创建你的 OneFile 项目档案</div>
          <div style="color:#64748B;font-size:14px;">输入混乱描述、BP 摘要或口述信息，系统会自动提炼为可展示、可分享、可归档的结构化项目资产。</div>
          <div style="margin-top:10px;color:#2D7AFF;font-size:13px;font-weight:600;">你的项目档案可用于：融资展示 / 园区申请 / 合作对接 / 持续记录</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("creator_form", clear_on_submit=False):
        manual_title = st.text_input(
            "项目名称（必填）",
            placeholder="例如：星火计划",
        )
        input_cols = st.columns([0.72, 0.28])
        with input_cols[0]:
            raw_input = st.text_area(
                "输入项目描述",
                height=180,
                placeholder="例：我们在做一个面向园区创业者的 AI 申报助手，输入项目 PDF 和口述内容后，30 秒内输出标准化项目档案、版本足迹和投递摘要。",
            )
        with input_cols[1]:
            uploaded_file = st.file_uploader(
                "上传文件（可选）",
                type=["pdf", "txt", "md"],
                accept_multiple_files=False,
                help="支持 PDF / TXT / MD。系统会先提取纯文本，再与输入描述一起结构化。",
            )
        action_cols = st.columns([0.22, 0.16, 0.62])
        with action_cols[0]:
            submitted = st.form_submit_button("创建项目档案", type="primary", use_container_width=True)
        with action_cols[1]:
            cancel = st.form_submit_button("收起", use_container_width=True)
        if cancel:
            st.session_state.show_creator = False
        if submitted:
            manual_title_clean = sanitize_text_strict(manual_title, allow_empty=True, max_len=42)
            if not manual_title_clean:
                st.warning("请先填写项目名称，再创建项目档案。")
                return
            if not validate_title_candidate(manual_title_clean):
                st.warning("项目名称格式无效，请使用简短清晰的名称（不含句子或模板代码）。")
                return

            try:
                file_text = extract_text_from_uploaded_file(uploaded_file) if uploaded_file else ""
            except Exception as exc:
                st.error(f"文件解析失败：{clean_text(exc, 140)}")
                file_text = ""

            composed_input_parts = []
            if raw_input.strip():
                composed_input_parts.append(raw_input.strip())
            if file_text.strip():
                composed_input_parts.append(file_text.strip())
            composed_input = "\n\n".join(composed_input_parts).strip()

            if not composed_input:
                st.warning("请先输入项目描述或上传可解析文件。")
            else:
                with st.spinner("混元正在进行结构化抽取..."):
                    try:
                        schema = structure_project(composed_input, user_title=manual_title_clean)
                        schema = sanitize_schema({**schema, "title": manual_title_clean})
                        project = enrich_generated_project(schema)
                        insert_project_top(project)
                        st.session_state.last_generated_id = project["id"]
                        st.session_state.selected_project_id = project["id"]
                        st.session_state.show_creator = False
                        st.success("项目档案已创建并插入项目库顶部。")
                        if st.session_state.get("used_local_structuring"):
                            api_err = clean_text(st.session_state.get("last_api_error", ""), 120)
                            st.info(f"已使用本地结构化兜底（API 暂不可用）：{api_err}")
                    except Exception as exc:
                        st.error(f"生成失败：{clean_text(exc, 140)}")


def render_update_panel(project: Dict[str, Any]) -> None:
    project_id = project["id"]
    st.session_state.selected_project_id = project_id
    undo_available = project_id in st.session_state.undo_snapshots
    update_key = f"update_input_{project_id}"
    preview = st.session_state.get("update_preview")
    preview_for_current = isinstance(preview, dict) and preview.get("project_id") == project_id

    st.markdown(
        f"""
        <div class="creator-panel">
          <div class="creator-kicker">Project Update</div>
          <div style="font-size:24px;font-weight:700;color:#0f172a;margin-bottom:6px;">更新项目进展：{escape(project.get("title", ""))}</div>
          <div style="color:#64748B;font-size:14px;">这是档案维护流程：进入更新模式 → 生成更新预览 → 确认写入。写入后会新增历史记录，并可能刷新当前阶段与最新进展快照。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("本次更新会写入历史记录，并刷新“当前状态”中的阶段或最新进展。取消预览不会修改任何已有档案。")
    update_text = st.text_area(
        "最新进展",
        key=update_key,
        height=130,
        placeholder="例如：新增3个企业试点客户，完成支付闭环，月收入达到2万元。",
    )
    action_cols = st.columns([0.22, 0.18, 0.2, 0.4])
    with action_cols[0]:
        if st.button("生成更新预览", type="primary", key=f"preview_{project_id}", use_container_width=True):
            if not sanitize_text_strict(update_text, allow_empty=True, max_len=240):
                st.warning("请先输入有效进展内容。")
            else:
                with st.spinner("正在生成更新预览..."):
                    try:
                        st.session_state.update_preview = generate_update_preview(project_id, update_text)
                        st.session_state.selected_project_id = project_id
                        st.rerun()
                    except Exception as exc:
                        st.error(f"预览生成失败：{clean_text(exc, 140)}")
    with action_cols[1]:
        if st.button("退出更新模式", key=f"close_update_{project_id}", use_container_width=True):
            if preview_for_current:
                st.session_state.update_preview = None
            st.session_state.update_target_id = None
            st.rerun()
    with action_cols[2]:
        if st.button(
            "撤销最近一次更新",
            key=f"undo_update_{project_id}",
            use_container_width=True,
            disabled=not undo_available,
        ):
            try:
                undo_last_update(project_id)
                st.rerun()
            except Exception as exc:
                st.error(f"撤销失败：{clean_text(exc, 140)}")

    if preview_for_current:
        changed_fields = preview.get("changed_fields", [])
        preview_fields = preview.get("preview_fields", [])
        signals = preview.get("signals", {})
        rule_hits = [sanitize_text_strict(hit, allow_empty=True, max_len=40) for hit in signals.get("hits", [])] if isinstance(signals, dict) else []
        rule_hits = [hit for hit in rule_hits if hit]
        preview_project = preview.get("preview_project", {})
        new_version = ""
        if isinstance(preview_project, dict):
            versions = preview_project.get("versions", [])
            if isinstance(versions, list) and versions and isinstance(versions[0], dict):
                new_version = sanitize_text_strict(versions[0].get("event", ""), allow_empty=True, max_len=120)
        st.markdown("#### 更新预览（未写入）")
        st.markdown(
            f"- 目标项目：`{escape(project.get('title', ''))}`\n"
            f"- 预览时间：`{escape(clean_text(preview.get('timestamp', ''), 24))}`\n"
            f"- 将新增版本记录：`{escape(new_version or '（无）')}`"
        )
        if rule_hits:
            st.markdown(f"**规则命中：** {' / '.join([escape(hit) for hit in rule_hits])}")
        if preview_fields:
            st.markdown("**关键字段前后对比：**")
            for item in preview_fields:
                label = sanitize_text_strict(item.get("label", ""), allow_empty=True, max_len=20)
                before = sanitize_text_strict(item.get("before", ""), allow_empty=True, max_len=120)
                after = sanitize_text_strict(item.get("after", ""), allow_empty=True, max_len=120)
                changed = bool(item.get("changed"))
                prefix = "变更" if changed else "不变"
                st.markdown(f"- {escape(label)}（{prefix}）：`{escape(before)}` → `{escape(after)}`")
        else:
            st.info("结构化字段无明显变化，但确认后仍会新增一条版本历史。")

        if not changed_fields:
            st.info("当前更新不会修改核心字段，将只写入一条新的版本记录。")

        confirm_cols = st.columns([0.24, 0.2, 0.56])
        with confirm_cols[0]:
            if st.button("确认写入档案", type="primary", key=f"confirm_update_{project_id}", use_container_width=True):
                try:
                    commit_update_preview(project_id)
                    st.rerun()
                except Exception as exc:
                    st.error(f"写入失败：{clean_text(exc, 140)}")
        with confirm_cols[1]:
            if st.button("取消预览", key=f"cancel_preview_{project_id}", use_container_width=True):
                st.session_state.update_preview = None
                st.rerun()


def render_share_page(project: Dict[str, Any]) -> None:
    project = prepare_project_for_render(project)
    share_url = build_share_url(project["id"])
    st.markdown("# OneFile 项目档案")
    st.caption(f"公开链接：{share_url}")
    st.markdown(
        f"""
        <div class="archive-panel">
          <div style="font-size:30px;font-weight:700;color:#0f172a;line-height:1.2;margin-bottom:8px;">{escape(project.get("title", ""))}</div>
          <div style="color:#64748B;font-size:14px;margin-bottom:18px;">{escape(project.get("summary", ""))}</div>
          <div class="archive-kpis">
            <div class="archive-kpi"><div class="archive-kpi-label">技术栈</div><div class="archive-kpi-value">{escape(', '.join(project.get("tech_stack", [])))}</div></div>
            <div class="archive-kpi"><div class="archive-kpi-label">目标用户</div><div class="archive-kpi-value">{escape(project.get("users", ""))}</div></div>
            <div class="archive-kpi"><div class="archive-kpi-label">商业模式</div><div class="archive-kpi-value">{escape(project.get("model_desc", project.get("model", "")))}</div></div>
            <div class="archive-kpi"><div class="archive-kpi-label">当前阶段</div><div class="archive-kpi-value">{escape(project.get("stage_label", stage_label(project.get("stage", ""))))}</div></div>
            <div class="archive-kpi"><div class="archive-kpi-label">产品形态</div><div class="archive-kpi-value">{escape(project.get("form_type_label", ""))}</div></div>
            <div class="archive-kpi"><div class="archive-kpi-label">最新进展</div><div class="archive-kpi-value">{escape(project.get("latest_update", ""))}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### 问题与解决方案")
    st.markdown(f"**问题定义**：{escape(sanitize_text_strict(project.get('problem_statement', ''), allow_empty=True, max_len=180) or '待补充')}")
    st.markdown(f"**解决方案**：{escape(sanitize_text_strict(project.get('solution_approach', ''), allow_empty=True, max_len=180) or '待补充')}")
    st.markdown("### 用户与场景")
    st.markdown(f"**目标用户**：{escape(sanitize_text_strict(project.get('users', ''), allow_empty=True, max_len=100) or '待补充')}")
    st.markdown(f"**典型场景**：{escape(sanitize_text_strict(project.get('use_cases', ''), allow_empty=True, max_len=180) or '待补充')}")
    st.markdown("### 当前状态")
    st.info(sanitize_text_strict(project.get("latest_update", ""), allow_empty=True, max_len=180) or "暂无最新进展")
    if st.button("返回项目库"):
        st.query_params.clear()
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
