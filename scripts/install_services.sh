#!/usr/bin/env bash
# Install Ringside Analytics systemd user units.
#
# One-time setup:
#   sudo loginctl enable-linger "$USER"   # so services run at boot without login
#
# After that, this script can be re-run without sudo to refresh units.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="$PROJECT_DIR/scripts/systemd"
UNIT_DST="$HOME/.config/systemd/user"

echo "=== Installing user systemd units to $UNIT_DST ==="
mkdir -p "$UNIT_DST"
cp -v "$UNIT_SRC"/*.service "$UNIT_SRC"/*.timer "$UNIT_DST/"

echo ""
echo "=== Enabling linger (requires sudo, one-time) ==="
if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
  echo "  Linger not enabled — enabling now (will prompt for sudo)..."
  sudo loginctl enable-linger "$USER"
else
  echo "  Linger already enabled"
fi

echo ""
echo "=== Stopping any nohup-started processes ==="
pkill -f "node dist/index.js" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
sleep 1

echo ""
echo "=== Reloading & enabling units ==="
systemctl --user daemon-reload
systemctl --user enable --now \
  ringside-api.service \
  ringside-frontend.service \
  ringside-ml.service \
  ringside-refresh.timer

echo ""
echo "=== Status ==="
systemctl --user --no-pager status \
  ringside-api.service \
  ringside-frontend.service \
  ringside-ml.service \
  ringside-refresh.timer \
  2>&1 | grep -E "●|Active:|Loaded:" | head -20

echo ""
echo "=== Next refresh run ==="
systemctl --user list-timers ringside-refresh.timer --no-pager 2>&1 | head -5

echo ""
echo "Done. Useful commands:"
echo "  systemctl --user status ringside-api"
echo "  systemctl --user restart ringside-frontend"
echo "  journalctl --user -u ringside-ml -f"
echo "  systemctl --user start ringside-refresh.service   # run refresh now"
