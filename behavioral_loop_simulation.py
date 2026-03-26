from copy import deepcopy
from datetime import datetime, timedelta

from project_model import (
    build_update_entry,
    derive_ops_signals,
    ensure_action_loop_defaults,
    evolve_action_loop,
    normalize_project,
)


def _ts(days_ago: int = 0) -> str:
    return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _base_project(pid: str = "p_demo"):
    project = {
        "id": pid,
        "title": "Loop Demo",
        "summary": "测试项目",
        "stage": "MVP",
        "users": "独立开发者",
        "model": "订阅制",
        "model_desc": "订阅制",
        "form_type": "SAAS",
        "model_type": "B2B_SUBSCRIPTION",
        "latest_update": "完成初版发布",
        "version_footprint": "完成初版发布",
        "updated_at": _ts(8),
        "owner_user_id": "u_demo",
        "share": {"is_public": False},
        "updates": [
            build_update_entry(
                project_id=pid,
                author_user_id="u_demo",
                content="完成初版发布",
                source="create",
                created_at=_ts(8),
                kind="result",
                next_action_text="完成一次真实用户访谈并记录反馈",
            )
        ],
    }
    initialized = ensure_action_loop_defaults(normalize_project(project))
    events = [
        {"project_id": pid, "event_type": "project_created", "ts": _ts(8)},
        {"project_id": pid, "event_type": "project_updated", "ts": _ts(8)},
    ]
    initialized["ops_signals"] = derive_ops_signals(pid, events, now_ts=_ts(0))
    initialized = evolve_action_loop(initialized, initialized.get("latest_update", ""), initialized.get("updated_at", _ts(0)))
    return normalize_project(initialized), events


def _apply_update(project: dict, events: list, text: str, days_ago: int = 0) -> dict:
    next_project = deepcopy(project)
    next_events = list(events)
    ts = _ts(days_ago)
    entry = build_update_entry(
        project_id=next_project["id"],
        author_user_id=next_project.get("owner_user_id", "u_demo"),
        content=text,
        source="overlay_update",
        created_at=ts,
        next_action_text=(next_project.get("next_action", {}) or {}).get("text", ""),
    )
    updates = [entry] + [u for u in next_project.get("updates", []) if isinstance(u, dict)]
    next_project["updates"] = updates
    next_project["latest_update"] = text
    next_project["version_footprint"] = text
    next_project["updated_at"] = ts
    next_events.append({"project_id": next_project["id"], "event_type": "project_updated", "ts": ts})
    if bool(entry.get("completion_signal", False)):
        next_events.append({"project_id": next_project["id"], "event_type": "next_action_completed", "ts": ts})
    next_project["ops_signals"] = derive_ops_signals(next_project["id"], next_events, now_ts=_ts(0))
    evolved = evolve_action_loop(next_project, text, ts)
    return normalize_project(evolved), next_events


def _decision_signature(project: dict):
    progress = project.get("progress_eval", {}) if isinstance(project.get("progress_eval", {}), dict) else {}
    intervention = project.get("intervention", {}) if isinstance(project.get("intervention", {}), dict) else {}
    reason_codes = tuple(progress.get("reason_codes", [])) if isinstance(progress.get("reason_codes", []), list) else tuple()
    return (
        progress.get("status"),
        int(progress.get("score", 0)),
        intervention.get("status"),
        intervention.get("type"),
        reason_codes,
    )


def run():
    scenarios = {}
    scenario_events = {}

    passive, passive_events = _base_project("p_passive")
    passive["updated_at"] = _ts(10)
    passive["ops_signals"] = derive_ops_signals(passive["id"], passive_events, now_ts=_ts(0))
    passive = ensure_action_loop_defaults(passive)
    scenarios["passive"] = passive
    scenario_events["passive"] = passive_events

    fake, fake_events = _base_project("p_fake")
    fake, fake_events = _apply_update(fake, fake_events, "记录一下，后续再看", 2)
    fake, fake_events = _apply_update(fake, fake_events, "暂时没有实质进展，先记个note", 1)
    scenarios["fake_progress"] = fake
    scenario_events["fake_progress"] = fake_events

    active, active_events = _base_project("p_active")
    active, active_events = _apply_update(active, active_events, "已完成下一步：完成了5位用户访谈并整理反馈", 1)
    active, active_events = _apply_update(active, active_events, "基于反馈上线改进并新增2个付费客户", 0)
    scenarios["active"] = active
    scenario_events["active"] = active_events

    confused, confused_events = _base_project("p_confused")
    confused, confused_events = _apply_update(confused, confused_events, "今天感觉还行哈哈，随便试试这个那个", 1)
    confused, confused_events = _apply_update(confused, confused_events, "嗯嗯先这样吧，可能下周再说", 0)
    scenarios["confused"] = confused
    scenario_events["confused"] = confused_events

    print("=== Behavioral Simulation ===")
    for name, project in scenarios.items():
        pe = project.get("progress_eval", {})
        intervention = project.get("intervention", {})
        next_action = project.get("next_action", {})
        print(f"[{name}] status={pe.get('status')} score={pe.get('score')} confidence={project.get('system_confidence')}")
        print(f"  action={next_action.get('status')} | {next_action.get('text')}")
        print(f"  intervention={intervention.get('status')}:{intervention.get('type')} | {intervention.get('message')}")
        print(f"  decision_quality={project.get('decision_quality_score')} effect={project.get('last_intervention_effectiveness')}")
        print(f"  reasons={pe.get('reason_codes')}")

    print("\n=== Determinism Check ===")
    all_passed = True
    for name, project in scenarios.items():
        events = scenario_events[name]
        replay = deepcopy(project)
        replay["ops_signals"] = derive_ops_signals(replay["id"], events, now_ts=_ts(0))
        replay = evolve_action_loop(replay, replay.get("latest_update", ""), replay.get("updated_at", _ts(0)))
        replay = normalize_project(replay)
        same = _decision_signature(project) == _decision_signature(replay)
        all_passed = all_passed and same
        print(f"[{name}] deterministic={same}")
    print(f"determinism_overall={all_passed}")


if __name__ == "__main__":
    run()
