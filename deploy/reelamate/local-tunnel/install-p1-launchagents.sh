#!/usr/bin/env bash
set -euo pipefail

SERVICE_ROOT="${PVESS_SERVICE_ROOT:-$HOME/Services/pvess-calc}"
AGENT_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="${PVESS_WEB_WORKDIR:-$HOME/.pvess/reelamate-web}"
BACKUP_PLIST="$AGENT_DIR/com.tge.pvess-backup.plist"
HEALTH_PLIST="$AGENT_DIR/com.tge.pvess-healthcheck.plist"

mkdir -p "$AGENT_DIR" "$LOG_DIR"

cat > "$BACKUP_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.tge.pvess-backup</string>
  <key>ProgramArguments</key>
  <array>
    <string>$SERVICE_ROOT/deploy/reelamate/local-tunnel/backup-local.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>2</integer>
    <key>Minute</key><integer>15</integer>
  </dict>
  <key>StandardOutPath</key><string>$LOG_DIR/backup.launchd.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/backup.launchd.err</string>
</dict>
</plist>
PLIST

cat > "$HEALTH_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.tge.pvess-healthcheck</string>
  <key>ProgramArguments</key>
  <array>
    <string>$SERVICE_ROOT/deploy/reelamate/local-tunnel/health-check-curl.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>300</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/healthcheck.launchd.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/healthcheck.launchd.err</string>
</dict>
</plist>
PLIST

chmod 600 "$BACKUP_PLIST" "$HEALTH_PLIST"
plutil -lint "$BACKUP_PLIST" "$HEALTH_PLIST"

launchctl bootout "gui/$UID" "$BACKUP_PLIST" >/dev/null 2>&1 || true
launchctl bootout "gui/$UID" "$HEALTH_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID" "$BACKUP_PLIST"
launchctl bootstrap "gui/$UID" "$HEALTH_PLIST"
launchctl enable "gui/$UID/com.tge.pvess-backup"
launchctl enable "gui/$UID/com.tge.pvess-healthcheck"
launchctl kickstart -k "gui/$UID/com.tge.pvess-healthcheck"

echo "Installed $BACKUP_PLIST"
echo "Installed $HEALTH_PLIST"
