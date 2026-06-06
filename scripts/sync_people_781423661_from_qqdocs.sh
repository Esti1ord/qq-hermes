#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${QQ_HERMES_BASE_DIR:-/home/roxy/qq-hermes}"
if [ -f "$BASE_DIR/scripts/load_env.sh" ]; then
  # shellcheck source=/home/roxy/qq-hermes/scripts/load_env.sh
  source "$BASE_DIR/scripts/load_env.sh" "$BASE_DIR/.env"
fi
BASE_DIR="${QQ_HERMES_BASE_DIR:-$BASE_DIR}"

export QQ_DOCS_PEOPLE_DOC_URL="${QQ_DOCS_PEOPLE_DOC_URL:-https://docs.qq.com/markdown/DV2JWUGFEbUZKaVVD?}"
export QQ_DOCS_PEOPLE_TARGET="${QQ_DOCS_PEOPLE_TARGET:-$BASE_DIR/groups/781423661/people.md}"
export QQ_DOCS_PEOPLE_STATE="${QQ_DOCS_PEOPLE_STATE:-$BASE_DIR/groups/781423661/.people-doc-sync-state.json}"
export QQ_DOCS_PEOPLE_BACKUP_DIR="${QQ_DOCS_PEOPLE_BACKUP_DIR:-$BASE_DIR/groups/781423661/backups}"

cd "$BASE_DIR"
exec "${QQ_HERMES_PYTHON:-$BASE_DIR/venv/bin/python}" "$BASE_DIR/scripts/sync_people_from_qqdocs.py"
