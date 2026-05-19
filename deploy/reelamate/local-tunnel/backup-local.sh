#!/usr/bin/env bash
set -euo pipefail

SRC="${PVESS_WEB_WORKDIR:-$HOME/.pvess/reelamate-web}"
DEST="${PVESS_BACKUP_DIR:-$HOME/.pvess/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DEST/pvess-web-$STAMP.tgz"
TMP="$(mktemp -d)"

if [[ ! -d "$SRC" ]]; then
  echo "Missing PVESS web workdir: $SRC" >&2
  exit 1
fi

mkdir -p "$DEST"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/data"
rsync -a \
  --exclude='*.log' \
  --exclude='*.err' \
  --exclude='web-jobs.sqlite3-wal' \
  --exclude='web-jobs.sqlite3-shm' \
  "$SRC/" "$TMP/data/"

if [[ -f "$SRC/web-jobs.sqlite3" ]] && command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$SRC/web-jobs.sqlite3" ".backup '$TMP/data/web-jobs.sqlite3'"
fi

tar -czf "$OUT" -C "$TMP/data" .

chmod 600 "$OUT"
echo "$OUT"
