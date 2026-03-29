import json
import os
from pathlib import Path
from typing import Any, Dict, List
import uuid

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("ONEFILE_DATA_DIR", str(BASE_DIR / "data"))).resolve()
PROJECTS_FILE = Path(os.getenv("ONEFILE_PROJECTS_FILE", str(DATA_DIR / "projects.json"))).resolve()
SEED_FILE = Path(os.getenv("ONEFILE_PROJECTS_SEED_FILE", str(PROJECTS_FILE.with_name("projects.seed.json")))).resolve()
SCHEMA_VERSION = 2
STORE_TEMPLATE: Dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "users": [],
    "projects": [],
    "events": [],
    "auth_challenges": [],
    "auth_sessions": [],
}


def _ensure_storage_dir() -> None:
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _clone_store(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Deep clone to avoid cross-request mutation of shared templates.
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _normalize_store(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, list):
        # backward compatible: old format was pure project list
        return {
            "schema_version": SCHEMA_VERSION,
            "users": [],
            "projects": [item for item in raw if isinstance(item, dict)],
            "events": [],
            "auth_challenges": [],
            "auth_sessions": [],
        }
    if not isinstance(raw, dict):
        return dict(STORE_TEMPLATE)

    users = raw.get("users", [])
    projects = raw.get("projects", [])
    events = raw.get("events", [])
    auth_challenges = raw.get("auth_challenges", [])
    auth_sessions = raw.get("auth_sessions", [])
    normalized: Dict[str, Any] = {
        "schema_version": int(raw.get("schema_version", SCHEMA_VERSION)),
        "users": [item for item in users if isinstance(item, dict)],
        "projects": [item for item in projects if isinstance(item, dict)],
        "events": [item for item in events if isinstance(item, dict)],
        "auth_challenges": [item for item in auth_challenges if isinstance(item, dict)],
        "auth_sessions": [item for item in auth_sessions if isinstance(item, dict)],
    }
    return normalized


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


def load_store() -> Dict[str, Any]:
    _ensure_storage_dir()
    if not PROJECTS_FILE.exists():
        seed = _load_seed_store()
        PROJECTS_FILE.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
        return seed

    try:
        content = PROJECTS_FILE.read_text(encoding="utf-8").strip()
        if not content:
            seed = _load_seed_store()
            PROJECTS_FILE.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
            return seed
        return _normalize_store(json.loads(content))
    except Exception:
        return _clone_store(STORE_TEMPLATE)


def save_store(store: Dict[str, Any]) -> None:
    _ensure_storage_dir()
    payload = _normalize_store(store)
    # Use a unique temp file per write to avoid races under concurrent requests.
    tmp_file = DATA_DIR / f"{PROJECTS_FILE.name}.{uuid.uuid4().hex}.tmp"
    try:
        tmp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
