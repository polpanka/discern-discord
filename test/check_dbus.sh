#!/usr/bin/env bash
# Test if D-Bus notification interception works on your system.
# Run this, then trigger a Discord notification (have someone send you a message).
# You should see output when the notification fires.

set -euo pipefail

echo "=== Discord D-Bus Notification Test ==="
echo ""
echo "Listening for Discord notifications on D-Bus..."
echo "Send yourself a Discord message now. Press Ctrl+C to stop."
echo ""

dbus-monitor --session "interface='org.freedesktop.Notifications',member='Notify'" \
  | grep --line-buffered -A 20 'member=Notify'
