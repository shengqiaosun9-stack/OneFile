import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import storage


def test_backend_settings_reads_env_and_clamps(monkeypatch):
    monkeypatch.setenv("ONEFILE_CTA_TOKEN_TTL_DAYS", "99")
    monkeypatch.setenv("ONEFILE_GROWTH_WINDOW_MAX_DAYS", "3")
    monkeypatch.setenv("ONEFILE_INTERVENTION_WINDOW_MAX_DAYS", "200")

    from backend import config

    config.reset_settings_cache()
    settings = config.get_settings()
    assert settings.cta_token_ttl_days == 30
    assert settings.growth_window_max_days == 7
    assert settings.intervention_window_max_days == 120


def test_migrate_store_to_v3_creates_backup_and_upgrades_payload(tmp_path):
    raw_store = {
        "schema_version": 2,
        "users": [{"id": "u1", "email": "owner@example.com"}],
        "projects": [{"id": "p1", "title": "Legacy", "owner_user_id": "u1"}],
        "events": [{"event_type": "project_created", "project_id": "p1"}],
    }
    source_file = tmp_path / "projects.json"
    source_file.write_text(json.dumps(raw_store, ensure_ascii=False), encoding="utf-8")

    from backend.migrations import migrate_store_to_v3

    result = migrate_store_to_v3(source_file)
    assert result["schema_version"] == 3
    assert result["backup_path"]
    backup_path = Path(result["backup_path"])
    assert backup_path.exists()

    migrated = json.loads(source_file.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 3
    assert isinstance(migrated["events"], list)
    assert migrated["events"][0]["id"]
    assert migrated["events"][0]["payload"] == {}
    assert migrated["projects"][0]["share"]["slug"] == "onefile-p1"


def test_migrate_store_to_v3_rejects_non_json_file(tmp_path):
    source_file = tmp_path / "broken.json"
    source_file.write_text("not a json", encoding="utf-8")

    from backend.migrations import migrate_store_to_v3

    with pytest.raises(ValueError):
        migrate_store_to_v3(source_file)


def test_save_store_handles_parallel_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "PROJECTS_FILE", tmp_path / "projects.json")

    def write_once(index: int) -> None:
        storage.save_store(
            {
                "schema_version": 2,
                "users": [{"id": f"u{index}", "email": f"u{index}@example.com"}],
                "projects": [{"id": f"p{index}", "title": f"Project {index}"}],
                "events": [{"event_type": "project_created", "project_id": f"p{index}"}],
            }
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write_once, range(40)))

    assert storage.PROJECTS_FILE.exists()
    loaded = json.loads(storage.PROJECTS_FILE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    assert loaded.get("schema_version") == 2


def test_load_store_backfills_seed_examples_into_existing_empty_store(tmp_path, monkeypatch):
    empty_store = {
        "schema_version": 2,
        "users": [],
        "projects": [],
        "events": [],
        "auth_challenges": [],
        "auth_sessions": [],
    }
    seed_store = {
        "schema_version": 2,
        "users": [],
        "projects": [
            {
                "id": "7451c54f",
                "title": "Seed Demo",
                "entity_type": "claimed_project",
                "claim_status": "claimed",
                "visible_in_library": True,
                "share": {"is_public": True, "slug": "seed-demo"},
            }
        ],
        "events": [],
        "auth_challenges": [],
        "auth_sessions": [],
    }

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    project_file = data_dir / "projects.json"
    seed_file = data_dir / "projects.seed.json"
    project_file.write_text(json.dumps(empty_store, ensure_ascii=False), encoding="utf-8")
    seed_file.write_text(json.dumps(seed_store, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "PROJECTS_FILE", project_file)
    monkeypatch.setattr(storage, "SEED_FILE", seed_file)

    loaded = storage.load_store()
    assert len(loaded.get("projects", [])) == 1
    assert loaded["projects"][0]["id"] == "7451c54f"

    persisted = json.loads(project_file.read_text(encoding="utf-8"))
    assert len(persisted.get("projects", [])) == 1
    assert persisted["projects"][0]["id"] == "7451c54f"


def test_load_store_seed_backfill_is_idempotent(tmp_path, monkeypatch):
    empty_store = {
        "schema_version": 2,
        "users": [],
        "projects": [],
        "events": [],
        "auth_challenges": [],
        "auth_sessions": [],
    }
    seed_store = {
        "schema_version": 2,
        "users": [],
        "projects": [
            {
                "id": "7451c54f",
                "title": "Seed Demo",
                "entity_type": "claimed_project",
                "claim_status": "claimed",
                "visible_in_library": True,
                "share": {"is_public": True, "slug": "seed-demo"},
            }
        ],
        "events": [],
        "auth_challenges": [],
        "auth_sessions": [],
    }

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    project_file = data_dir / "projects.json"
    seed_file = data_dir / "projects.seed.json"
    project_file.write_text(json.dumps(empty_store, ensure_ascii=False), encoding="utf-8")
    seed_file.write_text(json.dumps(seed_store, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "PROJECTS_FILE", project_file)
    monkeypatch.setattr(storage, "SEED_FILE", seed_file)

    first = storage.load_store()
    second = storage.load_store()

    assert len(first.get("projects", [])) == 1
    assert len(second.get("projects", [])) == 1
    assert first["projects"][0]["id"] == second["projects"][0]["id"] == "7451c54f"
