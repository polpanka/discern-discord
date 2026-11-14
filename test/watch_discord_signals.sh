#!/usr/bin/env bash
# Diagnostic: watch ALL D-Bus signals related to Discord.
#
# Run this, then:
#   1. Wait for a Discord notification to arrive
#   2. Open Discord and read all messages
#   3. Look at the output — especially LauncherEntry lines
#
# This shows us exactly what Discord sends when it updates its badge,
# so we can tune the auto-reset logic.

set -euo pipefail

echo "=== Discord D-Bus Signal Watcher ==="
echo ""
echo "Watching for Discord-related D-Bus activity..."
echo "Steps to test:"
echo "  1. Have someone send you a Discord message → look for Notify"
echo "  2. Open Discord and read everything → look for LauncherEntry Update"
echo ""
echo "Press Ctrl+C to stop."
echo "──────────────────────────────────────────────"
echo ""

dbus-monitor --session 2>/dev/null \
  | grep --line-buffered -i -A 10 \
      -e 'discord' \
      -e 'LauncherEntry' \
      -e 'member=Notify' \
      -e 'StatusNotifier'
