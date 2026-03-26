from copy import deepcopy
from datetime import datetime, timedelta

from project_model import build_update_entry, ensure_action_loop_defaults, evolve_action_loop, normalize_project


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
    return ensure_action_loop_defaults(normalize_project(project))


def _apply_update(project: dict, text: str, days_ago: int = 0) -> dict:
    next_project = deepcopy(project)
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
    evolved = evolve_action_loop(next_project, text, ts)
    return normalize_project(evolved)


def run():
    scenarios = {}

    passive = _base_project("p_passive")
    passive["updated_at"] = _ts(10)
    passive = ensure_action_loop_defaults(passive)
    scenarios["passive"] = passive

    fake = _base_project("p_fake")
    fake = _apply_update(fake, "记录一下，后续再看", 2)
    fake = _apply_update(fake, "暂时没有实质进展，先记个note", 1)
    scenarios["fake_progress"] = fake

    active = _base_project("p_active")
    active = _apply_update(active, "已完成下一步：完成了5位用户访谈并整理反馈", 1)
    active = _apply_update(active, "基于反馈上线改进并新增2个付费客户", 0)
    scenarios["active"] = active

    confused = _base_project("p_confused")
    confused = _apply_update(confused, "今天感觉还行哈哈，随便试试这个那个", 1)
    confused = _apply_update(confused, "嗯嗯先这样吧，可能下周再说", 0)
    scenarios["confused"] = confused

    print("=== Behavioral Simulation ===")
    for name, project in scenarios.items():
        pe = project.get("progress_eval", {})
        intervention = project.get("intervention", {})
        next_action = project.get("next_action", {})
        print(f"[{name}] status={pe.get('status')} score={pe.get('score')} confidence={project.get('system_confidence')}")
        print(f"  action={next_action.get('status')} | {next_action.get('text')}")
        print(f"  intervention={intervention.get('status')}:{intervention.get('type')} | {intervention.get('message')}")
        print(f"  decision_quality={project.get('decision_quality_score')} effect={project.get('last_intervention_effectiveness')}")


if __name__ == "__main__":
    run()
