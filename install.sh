#!/bin/bash
set -e

echo "==> Installing GoodIdea sync"

mkdir -p logs

pip3 install anthropic --quiet

# Read ANTHROPIC_API_KEY from .env or environment
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [[ "$(uname)" == "Darwin" ]]; then
  PLIST="launchd/com.goodidea.sync.plist"
  DEST="$HOME/Library/LaunchAgents/com.goodidea.sync.plist"
  if [ -f "$PLIST" ]; then
    SCRIPT_DIR="$(pwd)"
    sed "s|SCRIPT_DIR|$SCRIPT_DIR|g; s|REPLACE_WITH_YOUR_KEY|${ANTHROPIC_API_KEY}|g" \
      "$PLIST" > "$DEST"
    launchctl unload "$DEST" 2>/dev/null || true
    launchctl load "$DEST"
    echo "==> LaunchAgent installed (runs every Monday 09:00)"
  fi
fi

echo "==> Done. Test with: python3 sync/sync_goodidea.py"
