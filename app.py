import streamlit as st

from project_model import get_now_str, project_matches
from state_manager import get_project_by_id, init_state
from ui_components import (
    render_cards_grid,
    render_creator_panel,
    render_filters,
    render_nav,
    render_project_detail_page,
    render_share_page,
    render_styles,
    render_update_panel,
)

st.set_page_config(page_title="OneFile · 一人档", page_icon="🧬", layout="wide")


# === App Orchestration ===
init_state()

project_id = st.query_params.get("project", "")
page_view = str(st.query_params.get("view", "share" if project_id else "")).strip().lower()
if project_id:
    target_project = get_project_by_id(str(project_id))
    if target_project:
        render_styles()
        if page_view == "detail":
            render_nav(st.session_state.active_tab)
            render_project_detail_page(target_project)
        else:
            render_share_page(target_project)
        st.stop()
    st.query_params.clear()

render_styles()
render_nav(st.session_state.active_tab)

top_left, top_right = st.columns([0.72, 0.28])
with top_left:
    st.markdown('<div class="dashboard-title">OPC 项目展示库</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="dashboard-sub">当前共有 {len(st.session_state.projects)} 个入库项目，包含最新投后进展追踪 (更新日期: {get_now_str()})</div>',
        unsafe_allow_html=True,
    )
with top_right:
    if st.button("创建项目档案", type="primary", use_container_width=True):
        st.session_state.show_creator = not st.session_state.show_creator
    if st.button("园区后台", use_container_width=True):
        st.toast("园区管理后台为下一阶段功能，目前保留交互入口。")

if st.session_state.flash_message:
    st.success(st.session_state.flash_message)
    st.session_state.flash_message = None

if st.session_state.show_creator:
    render_creator_panel()

if st.session_state.update_target_id:
    target_project = get_project_by_id(st.session_state.update_target_id)
    if target_project:
        render_update_panel(target_project)
    else:
        st.session_state.update_target_id = None

if not st.session_state.projects:
    st.markdown(
        """
        <div class="archive-panel" style="margin-top: 20px;">
          <div style="font-size:22px;font-weight:700;color:#0f172a;margin-bottom:8px;">项目库为空</div>
          <div style="font-size:14px;color:#64748B;">
            当前还没有项目档案。点击右上角“创建项目档案”开始录入你的第一个 OPC 项目。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    filters = render_filters(st.session_state.projects)
    filtered_projects = [
        project
        for project in st.session_state.projects
        if project_matches(project, filters["tech"], filters["stage"], filters["form"], filters["model"], filters["keyword"])
    ]

    render_cards_grid(filtered_projects, st.session_state.last_generated_id)
