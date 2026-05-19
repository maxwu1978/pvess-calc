#!/usr/bin/env bash
set -euo pipefail

SRC="${PVESS_WEB_WORKDIR:-$HOME/.pvess/reelamate-web}"
DEST="${PVESS_BACKUP_DIR:-$HOME/.pvess/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DEST/pvess-web-$STAMP.tgz"

if [[ ! -d "$SRC" ]]; then
  echo "Missing PVESS web workdir: $SRC" >&2
  exit 1
fi

mkdir -p "$DEST"

tar \
  --exclude='*.log' \
  --exclude='*.err' \
  -czf "$OUT" \
  -C "$SRC" .

chmod 600 "$OUT"
echo "$OUT"
