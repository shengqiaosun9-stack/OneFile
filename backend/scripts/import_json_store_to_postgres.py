import argparse
import json
import os
from pathlib import Path

import storage
from backend.repository import PostgresStoreRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Import local OnePitch JSON store into Postgres JSONB storage.")
    parser.add_argument("--source", default="data/projects.json", help="Path to local projects.json")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""), help="Postgres connection string")
    parser.add_argument("--store-id", default="default", help="onepitch_store row id")
    args = parser.parse_args()

    database_url = str(args.database_url or "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required. Pass --database-url or set DATABASE_URL.")

    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"source file not found: {source}")

    raw = json.loads(source.read_text(encoding="utf-8"))
    payload = storage._normalize_store(raw)  # type: ignore[attr-defined]
    repo = PostgresStoreRepository(database_url=database_url, store_id=str(args.store_id or "default"))
    repo.save_store(payload)

    print(
        json.dumps(
            {
                "ok": True,
                "store_id": args.store_id,
                "schema_version": payload.get("schema_version"),
                "projects": len(payload.get("projects", [])),
                "bp_projects": len(payload.get("bp_projects", [])),
                "ops_people": len(payload.get("ops_people", [])),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
