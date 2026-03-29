import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_store(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, list):
        return {
            "schema_version": 3,
            "users": [],
            "projects": [item for item in raw if isinstance(item, dict)],
            "events": [],
        }
    if not isinstance(raw, dict):
        raise ValueError("invalid store payload")
    return {
        "schema_version": int(raw.get("schema_version", 2) or 2),
        "users": [item for item in raw.get("users", []) if isinstance(item, dict)],
        "projects": [item for item in raw.get("projects", []) if isinstance(item, dict)],
        "events": [item for item in raw.get("events", []) if isinstance(item, dict)],
    }


def _normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
    return {
        "id": str(event.get("id") or uuid.uuid4().hex[:12]),
        "ts": str(event.get("ts") or _now_ts()),
        "user_id": str(event.get("user_id") or ""),
        "project_id": str(event.get("project_id") or ""),
        "event_type": str(event.get("event_type") or "unknown_event"),
        "source": str(event.get("source") or "migration"),
        "payload": payload,
    }


def _normalize_project(project: Dict[str, Any]) -> Dict[str, Any]:
    pid = str(project.get("id") or uuid.uuid4().hex[:12])
    share = project.get("share", {}) if isinstance(project.get("share", {}), dict) else {}
    share_slug = str(share.get("slug") or f"onefile-{pid}")
    normalized_share = {
        "is_public": bool(share.get("is_public", False)),
        "slug": share_slug,
        "published_at": str(share.get("published_at", "")),
        "last_shared_at": str(share.get("last_shared_at", "")),
    }
    migrated = dict(project)
    migrated["id"] = pid
    migrated["share"] = normalized_share
    return migrated


def migrate_store_to_v3(source_path: Path) -> Dict[str, Any]:
    source = Path(source_path)
    if not source.exists():
        raise ValueError("source file not found")

    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("invalid json file") from exc

    store = _normalize_store(raw)
    users = [item for item in store.get("users", []) if isinstance(item, dict)]
    projects = [_normalize_project(item) for item in store.get("projects", []) if isinstance(item, dict)]
    events = [_normalize_event(item) for item in store.get("events", []) if isinstance(item, dict)]

    migrated = {
        "schema_version": 3,
        "users": users,
        "projects": projects,
        "events": events,
    }

    backup_path = source.with_suffix(f"{source.suffix}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(source, backup_path)
    source.write_text(json.dumps(migrated, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"schema_version": 3, "backup_path": str(backup_path), "events_migrated": len(events), "projects_migrated": len(projects)}
