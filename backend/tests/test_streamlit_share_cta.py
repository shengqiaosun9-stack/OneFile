from datetime import datetime, timedelta

import streamlit as st

import state_manager


def _reset_session() -> None:
    st.session_state.clear()
    st.session_state["events"] = []
    st.session_state["projects"] = []
    st.session_state[state_manager.SHARE_CTA_TOKEN_SESSION_KEY] = ""


def test_issue_share_cta_token_records_event_and_session(monkeypatch):
    _reset_session()
    monkeypatch.setattr(state_manager, "persist_events", lambda: None)
    monkeypatch.setattr(state_manager, "refresh_ops_signals_from_events", lambda *args, **kwargs: True)

    token = state_manager.issue_share_cta_token(
        project_id="p_source",
        source="share_page_public",
        cta="start_project",
        ref="share_hero",
        access_granted=True,
    )

    assert isinstance(token, str)
    assert len(token) >= 8
    assert state_manager.get_active_share_cta_token() == token

    events = st.session_state.get("events", [])
    assert len(events) == 1
    assert events[0]["event_type"] == "share_cta_clicked"
    payload = events[0].get("payload", {})
    assert payload.get("cta_token") == token
    assert payload.get("cta") == "start_project"


def test_attribute_share_conversion_create_is_deduplicated(monkeypatch):
    _reset_session()
    monkeypatch.setattr(state_manager, "persist_events", lambda: None)
    monkeypatch.setattr(state_manager, "refresh_ops_signals_from_events", lambda *args, **kwargs: True)

    token = state_manager.issue_share_cta_token(
        project_id="p_source",
        source="share_page_public",
        cta="start_project",
        ref="share_hero",
        access_granted=True,
    )
    assert token

    first = state_manager.attribute_share_conversion(kind="create", target_project_id="p_target")
    second = state_manager.attribute_share_conversion(kind="create", target_project_id="p_target")

    assert first is True
    assert second is False

    events = st.session_state.get("events", [])
    attributed = [
        item
        for item in events
        if item.get("event_type") == "share_conversion_attributed"
        and item.get("payload", {}).get("cta_token") == token
        and item.get("payload", {}).get("conversion_kind") == "create"
    ]
    assert len(attributed) == 1



def test_attribute_share_conversion_skips_expired_token(monkeypatch):
    _reset_session()
    monkeypatch.setattr(state_manager, "persist_events", lambda: None)
    monkeypatch.setattr(state_manager, "refresh_ops_signals_from_events", lambda *args, **kwargs: True)

    token = "expiredtoken1234"
    old_ts = (datetime.now() - timedelta(days=state_manager.SHARE_CTA_TOKEN_TTL_DAYS + 1)).strftime("%Y-%m-%d %H:%M:%S")

    st.session_state["events"] = [
        {
            "id": "evt_expired",
            "ts": old_ts,
            "user_id": "",
            "project_id": "p_source",
            "event_type": "share_cta_clicked",
            "source": "share_page_public",
            "payload": {"cta_token": token, "cta": "start_project", "ref": "share_hero"},
        }
    ]
    st.session_state[state_manager.SHARE_CTA_TOKEN_SESSION_KEY] = token

    ok = state_manager.attribute_share_conversion(kind="update", target_project_id="p_target")
    assert ok is False

    events = st.session_state.get("events", [])
    attributed = [item for item in events if item.get("event_type") == "share_conversion_attributed"]
    skipped = [
        item
        for item in events
        if item.get("event_type") == "share_conversion_skipped"
        and item.get("payload", {}).get("reason") == "token_expired"
    ]
    assert len(attributed) == 0
    assert len(skipped) == 1
