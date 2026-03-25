import json
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_FILE = DATA_DIR / "projects.json"


def _ensure_storage_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_projects() -> List[Dict[str, Any]]:
    _ensure_storage_dir()
    if not PROJECTS_FILE.exists():
        PROJECTS_FILE.write_text("[]", encoding="utf-8")
        return []

    try:
        content = PROJECTS_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return []
        raw = json.loads(content)
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]
    except Exception:
        return []


def save_projects(projects: List[Dict[str, Any]]) -> None:
    _ensure_storage_dir()
    payload = projects if isinstance(projects, list) else []
    tmp_file = PROJECTS_FILE.with_suffix(".json.tmp")
    tmp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_file.replace(PROJECTS_FILE)
