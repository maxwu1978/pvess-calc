#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${PVESS_BACKUP_DIR:-$HOME/.pvess/backups}"
ARCHIVE="${1:-}"

if [[ -z "$ARCHIVE" ]]; then
  ARCHIVE="$(ls -t "$BACKUP_DIR"/pvess-web-*.tgz 2>/dev/null | head -1 || true)"
fi

if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "No backup archive found. Run backup-local.sh first." >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

tar -xzf "$ARCHIVE" -C "$TMP"

file_count="$(find "$TMP" -type f | wc -l | tr -d ' ')"
if [[ "$file_count" == "0" ]]; then
  echo "Backup archive is empty: $ARCHIVE" >&2
  exit 1
fi

if [[ -f "$TMP/web-jobs.sqlite3" ]]; then
  if command -v sqlite3 >/dev/null 2>&1; then
    integrity="$(sqlite3 "$TMP/web-jobs.sqlite3" 'PRAGMA integrity_check;')"
    if [[ "$integrity" != "ok" ]]; then
      echo "SQLite integrity check failed: $integrity" >&2
      exit 1
    fi
    echo "PASS sqlite integrity"
  else
    echo "WARN sqlite3 not found; skipped SQLite integrity check"
  fi
else
  echo "WARN web-jobs.sqlite3 not found in archive"
fi

echo "PASS restore drill archive=$ARCHIVE files=$file_count extract_dir=$TMP"
