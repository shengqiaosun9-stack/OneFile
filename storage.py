import json
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_FILE = DATA_DIR / "projects.json"
SCHEMA_VERSION = 2
STORE_TEMPLATE: Dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "users": [],
    "projects": [],
}


def _ensure_storage_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_store(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, list):
        # backward compatible: old format was pure project list
        return {
            "schema_version": SCHEMA_VERSION,
            "users": [],
            "projects": [item for item in raw if isinstance(item, dict)],
        }
    if not isinstance(raw, dict):
        return dict(STORE_TEMPLATE)

    users = raw.get("users", [])
    projects = raw.get("projects", [])
    normalized: Dict[str, Any] = {
        "schema_version": int(raw.get("schema_version", SCHEMA_VERSION)),
        "users": [item for item in users if isinstance(item, dict)],
        "projects": [item for item in projects if isinstance(item, dict)],
    }
    return normalized


def load_store() -> Dict[str, Any]:
    _ensure_storage_dir()
    if not PROJECTS_FILE.exists():
        PROJECTS_FILE.write_text(json.dumps(STORE_TEMPLATE, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(STORE_TEMPLATE)

    try:
        content = PROJECTS_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return dict(STORE_TEMPLATE)
        return _normalize_store(json.loads(content))
    except Exception:
        return dict(STORE_TEMPLATE)


def save_store(store: Dict[str, Any]) -> None:
    _ensure_storage_dir()
    payload = _normalize_store(store)
    tmp_file = PROJECTS_FILE.with_suffix(".json.tmp")
    tmp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_file.replace(PROJECTS_FILE)


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
