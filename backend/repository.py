from typing import Any, Dict, Optional, Protocol

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


_default_repository: StoreRepository = JsonStoreRepository()


def get_store_repository() -> StoreRepository:
    return _default_repository


def set_store_repository(repository: StoreRepository) -> None:
    global _default_repository
    _default_repository = repository
