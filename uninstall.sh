#!/usr/bin/env bash
set -euo pipefail

echo "=== discern-discord — Uninstall ==="

# Stop service
systemctl --user disable --now discern-discord 2>/dev/null || true

# Remove old names too (upgrade from discord-notifier / discern)
systemctl --user disable --now discern 2>/dev/null || true
systemctl --user disable --now discord-notifier 2>/dev/null || true

rm -f "$HOME/.local/bin/discern-discord"
rm -f "$HOME/.local/bin/discern"
rm -f "$HOME/.local/bin/discord-notifier"
rm -rf "$HOME/.local/share/discern-discord"
rm -rf "$HOME/.local/share/discern"
rm -rf "$HOME/.local/share/discord-notifier"
rm -f "$HOME/.config/autostart/discern-discord.desktop"
rm -f "$HOME/.config/autostart/discern.desktop"
rm -f "$HOME/.config/autostart/discord-notifier.desktop"
rm -f "$HOME/.config/systemd/user/discern-discord.service"
rm -f "$HOME/.config/systemd/user/discern.service"
rm -f "$HOME/.config/systemd/user/discord-notifier.service"
systemctl --user daemon-reload 2>/dev/null || true

echo "Removed. Config kept at ~/.config/discern-discord/"
echo "To remove config too: rm -rf ~/.config/discern-discord"
