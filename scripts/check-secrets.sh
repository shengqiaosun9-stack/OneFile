#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-staged}"

fail() {
  echo "secret scan failed: $1" >&2
  exit 1
}

allow_placeholder_assignment() {
  local value="$1"
  # Trim common markdown/shell wrappers.
  value="${value#\`}"
  value="${value%\`}"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  value="${value%,}"
  value="${value%)}"

  case "$value" in
    "..."|"<your-secret>"|"<YOUR_SECRET>"|"your-secret"|"YOUR_SECRET"|"changeme"|"CHANGE_ME"|"placeholder"|"PLACEHOLDER")
      return 0
      ;;
  esac
  return 1
}

scan_lines() {
  local lines="$1"

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    # Skip secret-scanner source lines themselves to avoid self-matching.
    if [[ "$line" == *"[[:space:]]*="* ]] || [[ "$line" == *"git grep -nE"* ]]; then
      continue
    fi

    if [[ "$line" =~ sk-[A-Za-z0-9_-]{20,} ]]; then
      fail "detected OpenAI-style secret token pattern (sk-...) in content"
    fi

    if [[ "$line" =~ (HUNYUAN_API_KEY|OPENAI_API_KEY)[[:space:]]*=[[:space:]]*([^[:space:]#\"]+) ]]; then
      local value="${BASH_REMATCH[2]}"
      if ! allow_placeholder_assignment "$value"; then
        fail "detected non-placeholder assignment for ${BASH_REMATCH[1]}"
      fi
    fi

  done <<< "$lines"
}

if [[ "$MODE" == "staged" ]]; then
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    fail "not inside a git repository"
  fi
  staged_added_lines="$(git diff --cached --unified=0 --no-color | grep '^+' | grep -v '^+++ ' || true)"
  scan_lines "$staged_added_lines"
  echo "secret scan passed (staged changes)"
  exit 0
fi

if [[ "$MODE" == "repo" ]]; then
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    fail "not inside a git repository"
  fi
  repo_text="$(git grep -nE 'sk-[A-Za-z0-9_-]{20,}|(HUNYUAN_API_KEY|OPENAI_API_KEY)[[:space:]]*=[[:space:]]*[^[:space:]#]+' -- ':!README.md' ':!deploy/README.md' ':!backend/README.md' ':!.env.example' || true)"
  scan_lines "$repo_text"
  echo "secret scan passed (repository)"
  exit 0
fi

fail "unknown mode '$MODE' (use: staged|repo)"
