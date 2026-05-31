import json
import os
from pathlib import Path
from typing import Any, Dict, List
import uuid

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("ONEFILE_DATA_DIR", str(BASE_DIR / "data"))).resolve()
PROJECTS_FILE = Path(os.getenv("ONEFILE_PROJECTS_FILE", str(DATA_DIR / "projects.json"))).resolve()
SEED_FILE = Path(os.getenv("ONEFILE_PROJECTS_SEED_FILE", str(PROJECTS_FILE.with_name("projects.seed.json")))).resolve()
SCHEMA_VERSION = 5
BACKUP_KEEP_COUNT = int(os.getenv("ONEFILE_BACKUP_KEEP_COUNT", "50"))
BP_STORE_KEYS = [
    "bp_projects",
    "bp_raw_materials",
    "bp_project_insights",
    "bp_evidence",
    "bp_pages",
    "bp_gap_reports",
    "bp_service_requests",
    "bp_project_cards",
    "bp_feedback",
    "bp_next_actions",
    "bp_versions",
]
STORE_TEMPLATE: Dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "users": [],
    "projects": [],
    "events": [],
    "bp_projects": [],
    "bp_raw_materials": [],
    "bp_project_insights": [],
    "bp_evidence": [],
    "bp_pages": [],
    "bp_gap_reports": [],
    "bp_service_requests": [],
    "bp_project_cards": [],
    "bp_feedback": [],
    "bp_next_actions": [],
    "bp_versions": [],
    "ops_inbox_items": [],
    "ops_people": [],
    "ops_organizations": [],
    "ops_projects": [],
    "ops_opportunities": [],
    "ops_needs": [],
    "ops_offers": [],
    "ops_interactions": [],
    "ops_contents": [],
    "ops_next_actions": [],
    "ops_leads": [],
    "ops_profiles": [],
    "ops_activities": [],
    "ops_activity_memberships": [],
    "ops_routing_records": [],
    "ops_events": [],
    "auth_challenges": [],
    "auth_sessions": [],
}

SYSTEM_EXAMPLE_IDS = {"7451c54f", "9c28454f", "c36ea7f2", "xljz2026"}


def _local_mode_enabled() -> bool:
    return os.getenv("ONEFILE_LOCAL_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _ensure_storage_dir() -> None:
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _clone_store(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Deep clone to avoid cross-request mutation of shared templates.
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _normalize_store(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, list):
        # backward compatible: old format was pure project list
        legacy_store = {
            "schema_version": SCHEMA_VERSION,
            "users": [],
            "projects": [item for item in raw if isinstance(item, dict)],
            "events": [],
            "ops_inbox_items": [],
            "ops_people": [],
            "ops_organizations": [],
            "ops_projects": [],
            "ops_opportunities": [],
            "ops_needs": [],
            "ops_offers": [],
            "ops_interactions": [],
            "ops_contents": [],
            "ops_next_actions": [],
            "ops_leads": [],
            "ops_profiles": [],
            "ops_activities": [],
            "ops_activity_memberships": [],
            "ops_routing_records": [],
            "ops_events": [],
            "auth_challenges": [],
            "auth_sessions": [],
        }
        for key in BP_STORE_KEYS:
            legacy_store[key] = []
        return legacy_store
    if not isinstance(raw, dict):
        return dict(STORE_TEMPLATE)

    users = raw.get("users", [])
    projects = raw.get("projects", [])
    events = raw.get("events", [])
    bp_payloads = {key: raw.get(key, []) for key in BP_STORE_KEYS}
    ops_inbox_items = raw.get("ops_inbox_items", [])
    ops_people = raw.get("ops_people", [])
    ops_organizations = raw.get("ops_organizations", [])
    ops_projects = raw.get("ops_projects", [])
    ops_opportunities = raw.get("ops_opportunities", [])
    ops_needs = raw.get("ops_needs", [])
    ops_offers = raw.get("ops_offers", [])
    ops_interactions = raw.get("ops_interactions", [])
    ops_contents = raw.get("ops_contents", [])
    ops_next_actions = raw.get("ops_next_actions", [])
    ops_leads = raw.get("ops_leads", [])
    ops_profiles = raw.get("ops_profiles", [])
    ops_activities = raw.get("ops_activities", [])
    ops_activity_memberships = raw.get("ops_activity_memberships", [])
    ops_routing_records = raw.get("ops_routing_records", [])
    ops_events = raw.get("ops_events", [])
    auth_challenges = raw.get("auth_challenges", [])
    auth_sessions = raw.get("auth_sessions", [])
    normalized: Dict[str, Any] = {
        "schema_version": int(raw.get("schema_version", SCHEMA_VERSION)),
        "users": [item for item in users if isinstance(item, dict)],
        "projects": [item for item in projects if isinstance(item, dict)],
        "events": [item for item in events if isinstance(item, dict)],
        **{key: [item for item in value if isinstance(item, dict)] if isinstance(value, list) else [] for key, value in bp_payloads.items()},
        "ops_inbox_items": [item for item in ops_inbox_items if isinstance(item, dict)],
        "ops_people": [item for item in ops_people if isinstance(item, dict)],
        "ops_organizations": [item for item in ops_organizations if isinstance(item, dict)],
        "ops_projects": [item for item in ops_projects if isinstance(item, dict)],
        "ops_opportunities": [item for item in ops_opportunities if isinstance(item, dict)],
        "ops_needs": [item for item in ops_needs if isinstance(item, dict)],
        "ops_offers": [item for item in ops_offers if isinstance(item, dict)],
        "ops_interactions": [item for item in ops_interactions if isinstance(item, dict)],
        "ops_contents": [item for item in ops_contents if isinstance(item, dict)],
        "ops_next_actions": [item for item in ops_next_actions if isinstance(item, dict)],
        "ops_leads": [item for item in ops_leads if isinstance(item, dict)],
        "ops_profiles": [item for item in ops_profiles if isinstance(item, dict)],
        "ops_activities": [item for item in ops_activities if isinstance(item, dict)],
        "ops_activity_memberships": [item for item in ops_activity_memberships if isinstance(item, dict)],
        "ops_routing_records": [item for item in ops_routing_records if isinstance(item, dict)],
        "ops_events": [item for item in ops_events if isinstance(item, dict)],
        "auth_challenges": [item for item in auth_challenges if isinstance(item, dict)],
        "auth_sessions": [item for item in auth_sessions if isinstance(item, dict)],
    }
    return normalized


def _write_backup() -> None:
    if not PROJECTS_FILE.exists():
        return
    try:
        backup_dir = DATA_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = uuid.uuid4().hex[:8]
        backup_file = backup_dir / f"{PROJECTS_FILE.stem}.{Path(PROJECTS_FILE).stat().st_mtime_ns}.{stamp}.json"
        backup_file.write_bytes(PROJECTS_FILE.read_bytes())
        backups = sorted(backup_dir.glob(f"{PROJECTS_FILE.stem}.*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for old_backup in backups[BACKUP_KEEP_COUNT:]:
            old_backup.unlink(missing_ok=True)
    except Exception:
        # Backups are best-effort; a backup failure must not block local writes.
        return


def _load_seed_store() -> Dict[str, Any]:
    if not SEED_FILE.exists():
        return _clone_store(STORE_TEMPLATE)
    try:
        content = SEED_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return _clone_store(STORE_TEMPLATE)
        normalized = _normalize_store(json.loads(content))
        return _clone_store(normalized)
    except Exception:
        return _clone_store(STORE_TEMPLATE)


def _merge_seed_examples(store: Dict[str, Any], seed_store: Dict[str, Any]) -> Dict[str, Any]:
    projects = [item for item in store.get("projects", []) if isinstance(item, dict)]
    seed_projects = [item for item in seed_store.get("projects", []) if isinstance(item, dict)]
    if not seed_projects:
        return store

    existing_ids = {str(item.get("id", "")).strip() for item in projects}
    missing_seed_projects: List[Dict[str, Any]] = []
    for seed_project in seed_projects:
        seed_id = str(seed_project.get("id", "")).strip()
        if not seed_id or seed_id in existing_ids:
            continue
        missing_seed_projects.append(_clone_store(seed_project))

    if not missing_seed_projects:
        return store

    public_projects_count = 0
    for item in projects:
        share = item.get("share", {}) if isinstance(item.get("share", {}), dict) else {}
        if bool(share.get("is_public", False)):
            public_projects_count += 1

    has_missing_system_examples = bool(SYSTEM_EXAMPLE_IDS.difference(existing_ids))
    if public_projects_count == 0 or has_missing_system_examples:
        merged = _clone_store(store)
        merged_projects = [item for item in merged.get("projects", []) if isinstance(item, dict)]
        merged_projects.extend(missing_seed_projects)
        merged["projects"] = merged_projects
        return merged

    return store


def load_store() -> Dict[str, Any]:
    _ensure_storage_dir()
    seed_store = _load_seed_store()
    initial_store = _clone_store(STORE_TEMPLATE) if _local_mode_enabled() else seed_store
    if not PROJECTS_FILE.exists():
        PROJECTS_FILE.write_text(json.dumps(initial_store, ensure_ascii=False, indent=2), encoding="utf-8")
        return initial_store

    try:
        content = PROJECTS_FILE.read_text(encoding="utf-8").strip()
        if not content:
            PROJECTS_FILE.write_text(json.dumps(initial_store, ensure_ascii=False, indent=2), encoding="utf-8")
            return initial_store
        normalized = _normalize_store(json.loads(content))
        if _local_mode_enabled():
            return normalized
        merged = _merge_seed_examples(normalized, seed_store)
        if merged != normalized:
            PROJECTS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged
    except Exception:
        return _clone_store(STORE_TEMPLATE)


def save_store(store: Dict[str, Any]) -> None:
    _ensure_storage_dir()
    payload = _normalize_store(store)
    # Use a unique temp file per write to avoid races under concurrent requests.
    tmp_file = DATA_DIR / f"{PROJECTS_FILE.name}.{uuid.uuid4().hex}.tmp"
    try:
        tmp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_backup()
        tmp_file.replace(PROJECTS_FILE)
    finally:
        if tmp_file.exists():
            tmp_file.unlink(missing_ok=True)


def load_projects() -> List[Dict[str, Any]]:
    return load_store().get("projects", [])


def save_projects(projects: List[Dict[str, Any]]) -> None:
    store = load_store()
    store["projects"] = projects if isinstance(projects, list) else []
    save_store(store)


def load_users() -> List[Dict[str, Any]]:
    return load_store().get("users", [])


def save_users(users: List[Dict[str, Any]]) -> None:
    store = load_store()
    store["users"] = users if isinstance(users, list) else []
    save_store(store)


def load_events() -> List[Dict[str, Any]]:
    return load_store().get("events", [])


def save_events(events: List[Dict[str, Any]]) -> None:
    store = load_store()
    store["events"] = events if isinstance(events, list) else []
    save_store(store)
