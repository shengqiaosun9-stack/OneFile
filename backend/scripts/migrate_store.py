import argparse
import json
from pathlib import Path

from backend.migrations import migrate_store_to_v3


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate OneFile JSON store to schema v3")
    parser.add_argument("--source", required=True, help="Path to data/projects.json")
    args = parser.parse_args()

    result = migrate_store_to_v3(Path(args.source))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
