import streamlit as st

from project_model import get_now_str, project_matches
from state_manager import (
    append_event_safe,
    refresh_ops_signals_from_events,
    get_current_user_email,
    get_current_user_id,
    get_project_by_id,
    get_project_by_id_any,
    get_visible_projects,
    init_state,
    is_authenticated,
    remember_share_cta_token,
    register_or_login_user,
)
from ui_components import (
    render_cards_grid,
    render_create_overlay,
    render_filters,
    render_nav,
    open_create_overlay,
    render_project_detail_page,
    render_share_page,
    render_styles,
    render_update_overlay,
)
try:
    from ui_components import render_edit_page
except ImportError:
    render_edit_page = None

st.set_page_config(page_title="OneFile · 一人档", page_icon="🧬", layout="wide")


# === App Orchestration ===
init_state()

project_id = st.query_params.get("project", "")
page_view = str(st.query_params.get("view", "detail" if project_id else "")).strip().lower()
page_mode = str(st.query_params.get("mode", "")).strip().lower()
page_action = str(st.query_params.get("action", "")).strip().lower()
page_cta_token = str(st.query_params.get("cta_token", "")).strip()

if page_cta_token:
    remember_share_cta_token(page_cta_token)

if "pending_create_after_login" not in st.session_state:
    st.session_state.pending_create_after_login = False

if page_action == "create":
    st.session_state.pending_create_after_login = True
    st.query_params.clear()
    st.rerun()

if page_view == "share" and project_id:
    target_project = get_project_by_id_any(str(project_id))
    if target_project:
        render_styles()
        owner_preview = bool(
            is_authenticated()
            and get_current_user_id()
            and target_project.get("owner_user_id") == get_current_user_id()
        )
        share_state = target_project.get("share", {}) if isinstance(target_project.get("share", {}), dict) else {}
        can_view = bool(share_state.get("is_public", False) or owner_preview)
        append_event_safe(
            event_type="share_viewed" if can_view else "share_denied",
            source="share_page",
            project_id=str(target_project.get("id", "")),
            payload={
                "owner_preview": owner_preview,
                "is_public": bool(share_state.get("is_public", False)),
            },
        )
        refresh_ops_signals_from_events(project_ids=[str(target_project.get("id", ""))], persist=True)
        render_share_page(target_project, access_granted=can_view, owner_preview=owner_preview)
        st.stop()
    st.query_params.clear()
    st.rerun()

if not is_authenticated():
    render_styles()
    st.markdown("## 欢迎使用 OneFile")
    st.markdown("请输入邮箱以进入你的项目空间。")
    with st.form("email_entry_form", clear_on_submit=False):
        email = st.text_input("邮箱", value=get_current_user_email(), placeholder="you@company.com")
        submitted = st.form_submit_button("进入项目空间", type="primary")
    if submitted:
        try:
            register_or_login_user(email)
            st.session_state.flash_message = "已进入你的项目空间。"
            if st.session_state.pending_create_after_login:
                st.session_state.pending_create_after_login = False
                open_create_overlay()
            st.rerun()
        except Exception as exc:
            st.error(f"登录失败：{exc}")
    st.stop()

if page_view == "edit":
    if page_mode == "create":
        st.query_params.clear()
        open_create_overlay()
        st.rerun()
    render_styles()
    render_nav(st.session_state.active_tab)
    if render_edit_page is None:
        st.warning("当前部署版本缺少统一编辑页，请返回项目库后重试。")
        if st.button("返回项目库", type="primary"):
            st.query_params.clear()
            st.rerun()
    else:
        target_project = get_project_by_id(str(project_id)) if project_id else None
        if target_project:
            render_edit_page(target_project, mode="update")
        else:
            st.warning("目标项目不存在，请返回项目库。")
            if st.button("返回项目库", type="primary"):
                st.query_params.clear()
                st.rerun()
    st.stop()

if project_id:
    target_project = get_project_by_id_any(str(project_id))
    if target_project:
        owner_preview = bool(
            is_authenticated()
            and get_current_user_id()
            and target_project.get("owner_user_id") == get_current_user_id()
        )
        share_state = target_project.get("share", {}) if isinstance(target_project.get("share", {}), dict) else {}
        can_view_detail = bool(owner_preview or share_state.get("is_public", False))
        if can_view_detail:
            render_styles()
            render_nav(st.session_state.active_tab)
            render_project_detail_page(target_project)
            st.stop()
        render_styles()
        render_nav(st.session_state.active_tab)
        st.warning("该项目未公开，你无权查看完整档案。")
        back_cols = st.columns([0.2, 0.8])
        with back_cols[0]:
            if st.button("返回项目库", key="detail_back_forbidden", type="primary", use_container_width=True):
                st.query_params.clear()
                st.rerun()
        st.stop()
    st.query_params.clear()

render_styles()
render_nav(st.session_state.active_tab)

top_left, top_right = st.columns([0.72, 0.28])
with top_left:
    st.markdown('<div class="dashboard-title">OPC 项目展示库</div>', unsafe_allow_html=True)
    visible_projects = get_visible_projects()
    st.markdown(
        f'<div class="dashboard-sub">当前共有 {len(visible_projects)} 个入库项目，包含最新投后进展追踪 (更新日期: {get_now_str()})</div>',
        unsafe_allow_html=True,
    )
with top_right:
    if st.button("创建项目档案", type="primary", use_container_width=True):
        open_create_overlay()
        st.rerun()

render_create_overlay()
render_update_overlay()

if st.session_state.flash_message:
    st.success(st.session_state.flash_message)
    st.session_state.flash_message = None

if st.session_state.pending_create_after_login and not st.session_state.create_dialog_open:
    st.session_state.pending_create_after_login = False
    open_create_overlay()
    st.rerun()

if not visible_projects:
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
    empty_cta_cols = st.columns([0.26, 0.74])
    with empty_cta_cols[0]:
        if st.button("创建项目档案", key="empty_state_create", type="primary", use_container_width=True):
            open_create_overlay()
            st.rerun()
else:
    filters = render_filters(visible_projects)
    filtered_projects = [
        project
        for project in visible_projects
        if project_matches(project, filters["tech"], filters["stage"], filters["form"], filters["model"], filters["keyword"])
    ]

    render_cards_grid(filtered_projects, st.session_state.last_generated_id)
