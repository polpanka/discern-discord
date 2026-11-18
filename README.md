# discern-discord

> *disc(ord) + discern* — distinguishes your Discord notifications by type.

Colored tray indicator for Discord on Linux.

![demo](https://i.imgur.com/kHyql2X.gif)

| Color | Meaning |
|-------|---------|
| Red | DM, @mention, @everyone, @here |
| Blue | Generic channel message |
| Grey | Nothing unread |

Resets to grey automatically when you open Discord and read your messages.

## Install

### From source (any distro)

```bash
git clone https://github.com/polpanka/discern-discord.git
cd discern-discord
bash install.sh
```

The script detects your package manager (apt/dnf/pacman/zypper) and installs dependencies automatically.

### From PyPI

```bash
pip install discern-discord
```

> **Note:** `dbus-python` and `PyGObject` require system libraries. If pip fails, install them via your package manager first (see [Dependencies](#dependencies)).

### From AUR (Arch/Manjaro)

```bash
yay -S discern-discord
```

## Configuration

Edit `~/.config/discern-discord/settings.json`:

```json
{
  "discord_username": "Paolo",
  "mention_keywords": ["urgente", "importante"]
}
```

- **discord_username** — your Discord display name, to detect `@Paolo` in channel messages
- **mention_keywords** — extra words that trigger the red indicator (case-insensitive)

## Usage

```bash
# Run directly
discern-discord

# Or as a systemd user service
systemctl --user enable --now discern-discord
```

### Test notifications

```bash
discern-discord &
python3 test/send_test_notification.py dm        # → red
python3 test/send_test_notification.py generic    # → blue
python3 test/send_test_notification.py mention    # → red
python3 test/send_test_notification.py clear      # → grey
```

## How it works

```
Discord (Electron)
    │
    │  org.freedesktop.Notifications.Notify
    ▼
D-Bus session bus ◄── discern-discord (eavesdrop / dbus-monitor fallback)
    │
    ├── title has no "#"?        → DM (red)
    ├── body has @you/@everyone? → mention (red)
    └── otherwise                → generic (blue)
```

**Auto-reset** when you read messages:
1. **LauncherEntry D-Bus** — Discord signals `count-visible: false` when its badge clears
2. **Window focus** — if Discord is focused for 3+ seconds (uses `xdotool` or `xprop`, optional)
3. **Manual** — right-click tray icon → Clear

## Dependencies

| | Ubuntu/Debian | Fedora | Arch | openSUSE |
|-|---------------|--------|------|----------|
| D-Bus Python | python3-dbus | python3-dbus | python-dbus | python3-dbus-python |
| PyGObject | python3-gi | python3-gobject | python-gobject | python3-gobject |
| AppIndicator | gir1.2-ayatanaappindicator3-0.1 | libayatana-appindicator-gtk3 | libayatana-appindicator | typelib-1_0-AyatanaAppIndicator3-0_1 |
| xdotool or xprop *(optional)* | xdotool | xdotool | xdotool | xdotool |

## Uninstall

```bash
bash uninstall.sh
# or
pip uninstall discern-discord
```

## License

MIT
