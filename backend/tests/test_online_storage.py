from backend.config import reset_settings_cache
from backend.repository import JsonStoreRepository, PostgresStoreRepository, get_store_repository, reset_store_repository


def test_settings_reads_online_storage_env(monkeypatch):
    monkeypatch.setenv("ONEPITCH_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    reset_settings_cache()

    from backend.config import get_settings

    settings = get_settings()
    assert settings.storage_backend == "postgres"
    assert settings.database_url == "postgresql://example"


def test_repository_selects_postgres_only_when_configured(monkeypatch):
    monkeypatch.setenv("ONEPITCH_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    reset_store_repository()

    assert isinstance(get_store_repository(), PostgresStoreRepository)

    monkeypatch.delenv("ONEPITCH_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_store_repository()

    assert isinstance(get_store_repository(), JsonStoreRepository)
