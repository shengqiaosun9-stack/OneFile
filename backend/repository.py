from typing import Any, Dict, Optional, Protocol

from backend.config import get_settings, reset_settings_cache
import storage


class StoreRepository(Protocol):
    def load_store(self) -> Dict[str, Any]:
        ...

    def save_store(self, store: Dict[str, Any]) -> None:
        ...

    def find_latest_event_by_payload(self, event_type: str, payload_key: str, payload_value: str) -> Optional[Dict[str, Any]]:
        ...


class JsonStoreRepository:
    def load_store(self) -> Dict[str, Any]:
        return storage.load_store()

    def save_store(self, store: Dict[str, Any]) -> None:
        storage.save_store(store)

    def find_latest_event_by_payload(self, event_type: str, payload_key: str, payload_value: str) -> Optional[Dict[str, Any]]:
        safe_type = str(event_type or "").strip().lower()
        safe_key = str(payload_key or "").strip()
        safe_value = str(payload_value or "").strip()
        if not safe_type or not safe_key or not safe_value:
            return None

        matched: Optional[Dict[str, Any]] = None
        for event in storage.load_events():
            if not isinstance(event, dict):
                continue
            current_type = str(event.get("event_type", "")).strip().lower()
            if current_type != safe_type:
                continue
            payload = event.get("payload", {})
            if not isinstance(payload, dict):
                continue
            current_value = str(payload.get(safe_key, "")).strip()
            if current_value != safe_value:
                continue
            matched = event
        return matched


class PostgresStoreRepository:
    def __init__(self, database_url: str, store_id: str = "default") -> None:
        self.database_url = database_url
        self.store_id = store_id

    def _connect(self) -> Any:
        try:
            import psycopg  # type: ignore
        except Exception as exc:
            raise RuntimeError("Postgres 存储需要安装 psycopg[binary]。") from exc
        return psycopg.connect(self.database_url)

    def _ensure_table(self, conn: Any) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists onepitch_store (
                    id text primary key,
                    schema_version integer not null,
                    payload jsonb not null,
                    updated_at timestamptz not null default now()
                )
                """
            )
        conn.commit()

    def load_store(self) -> Dict[str, Any]:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL 未配置，无法使用 Postgres 存储。")
        with self._connect() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute("select payload from onepitch_store where id = %s", (self.store_id,))
                row = cur.fetchone()
                if row:
                    payload = row[0]
                    if isinstance(payload, str):
                        import json

                        payload = json.loads(payload)
                    if isinstance(payload, dict):
                        return storage._normalize_store(payload)  # type: ignore[attr-defined]

                initial_store = storage._normalize_store({})  # type: ignore[attr-defined]
                self._save_store_with_connection(conn, initial_store)
                return initial_store

    def _save_store_with_connection(self, conn: Any, store: Dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb  # type: ignore

        payload = storage._normalize_store(store)  # type: ignore[attr-defined]
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into onepitch_store (id, schema_version, payload, updated_at)
                values (%s, %s, %s, now())
                on conflict (id) do update
                set schema_version = excluded.schema_version,
                    payload = excluded.payload,
                    updated_at = now()
                """,
                (self.store_id, int(payload.get("schema_version", storage.SCHEMA_VERSION)), Jsonb(payload)),
            )
        conn.commit()

    def save_store(self, store: Dict[str, Any]) -> None:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL 未配置，无法使用 Postgres 存储。")
        with self._connect() as conn:
            self._ensure_table(conn)
            self._save_store_with_connection(conn, store)

    def find_latest_event_by_payload(self, event_type: str, payload_key: str, payload_value: str) -> Optional[Dict[str, Any]]:
        safe_type = str(event_type or "").strip().lower()
        safe_key = str(payload_key or "").strip()
        safe_value = str(payload_value or "").strip()
        if not safe_type or not safe_key or not safe_value:
            return None

        matched: Optional[Dict[str, Any]] = None
        for event in self.load_store().get("events", []):
            if not isinstance(event, dict):
                continue
            current_type = str(event.get("event_type", "")).strip().lower()
            payload = event.get("payload", {})
            if current_type == safe_type and isinstance(payload, dict) and str(payload.get(safe_key, "")).strip() == safe_value:
                matched = event
        return matched


_default_repository: Optional[StoreRepository] = None
_repository_override: Optional[StoreRepository] = None


def get_store_repository() -> StoreRepository:
    global _default_repository
    if _repository_override is not None:
        return _repository_override
    if _default_repository is not None:
        return _default_repository
    settings = get_settings()
    if settings.storage_backend == "postgres" and settings.database_url:
        _default_repository = PostgresStoreRepository(settings.database_url)
    else:
        _default_repository = JsonStoreRepository()
    return _default_repository


def set_store_repository(repository: StoreRepository) -> None:
    global _repository_override
    _repository_override = repository


def reset_store_repository() -> None:
    global _default_repository, _repository_override
    _default_repository = None
    _repository_override = None
    reset_settings_cache()
