#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.local/share/discern-discord"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/discern-discord"
AUTOSTART_DIR="$HOME/.config/autostart"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "=== discern-discord — Install ==="
echo ""

# ── Detect package manager ─────────────────────────────────────

detect_pm() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v pacman &>/dev/null; then
        echo "pacman"
    elif command -v zypper &>/dev/null; then
        echo "zypper"
    else
        echo "unknown"
    fi
}

PM="$(detect_pm)"
echo "Package manager: $PM"
echo ""

# ── Dependencies ───────────────────────────────────────────────
echo "[1/5] Checking dependencies..."

MISSING=()

check_python_import() {
    python3 -c "$1" 2>/dev/null
}

# python3-dbus
if ! check_python_import "import dbus"; then
    case "$PM" in
        apt)    MISSING+=(python3-dbus) ;;
        dnf)    MISSING+=(python3-dbus) ;;
        pacman) MISSING+=(python-dbus) ;;
        zypper) MISSING+=(python3-dbus-python) ;;
    esac
fi

# python3-gi (PyGObject)
if ! check_python_import "import gi"; then
    case "$PM" in
        apt)    MISSING+=(python3-gi) ;;
        dnf)    MISSING+=(python3-gobject) ;;
        pacman) MISSING+=(python-gobject) ;;
        zypper) MISSING+=(python3-gobject) ;;
    esac
fi

# AppIndicator3
if ! check_python_import "
import gi
try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3
except:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3
"; then
    case "$PM" in
        apt)    MISSING+=(gir1.2-ayatanaappindicator3-0.1) ;;
        dnf)    MISSING+=(libayatana-appindicator-gtk3) ;;
        pacman) MISSING+=(libayatana-appindicator) ;;
        zypper) MISSING+=(typelib-1_0-AyatanaAppIndicator3-0_1) ;;
    esac
fi

# xdotool (optional)
if ! command -v xdotool &>/dev/null; then
    echo "  Note: xdotool not found (optional — adds focus-based auto-reset)."
fi

# dbus-monitor
if ! command -v dbus-monitor &>/dev/null; then
    case "$PM" in
        apt)    MISSING+=(dbus) ;;
        dnf)    MISSING+=(dbus-tools) ;;
        pacman) MISSING+=(dbus) ;;
        zypper) MISSING+=(dbus-1) ;;
    esac
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "  Missing: ${MISSING[*]}"
    if [[ "$PM" == "unknown" ]]; then
        echo "  ERROR: Could not detect package manager."
        echo "  Please install these manually: ${MISSING[*]}"
        exit 1
    fi
    echo "  Installing..."
    case "$PM" in
        apt)    sudo apt-get update -qq && sudo apt-get install -y -qq "${MISSING[@]}" ;;
        dnf)    sudo dnf install -y "${MISSING[@]}" ;;
        pacman) sudo pacman -S --noconfirm "${MISSING[@]}" ;;
        zypper) sudo zypper install -y "${MISSING[@]}" ;;
    esac
    echo "  Done."
else
    echo "  All dependencies present."
fi

# ── Install files ──────────────────────────────────────────────
echo "[2/5] Installing discern-discord..."

mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/src/discern_discord/"* "$INSTALL_DIR/"

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/discern-discord" <<LAUNCHER
#!/usr/bin/env bash
exec python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('notifier', '$INSTALL_DIR/notifier.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.main()
" "\$@"
LAUNCHER
chmod +x "$BIN_DIR/discern-discord"

echo "  Installed to $INSTALL_DIR"

# ── Config ─────────────────────────────────────────────────────
echo "[3/5] Setting up config..."

mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_DIR/settings.json" ]]; then
    cp "$SCRIPT_DIR/config/settings.json" "$CONFIG_DIR/"
    echo "  Created $CONFIG_DIR/settings.json"
else
    echo "  Config already exists, not overwriting."
fi

# ── Autostart ──────────────────────────────────────────────────
echo "[4/5] Setting up autostart..."

mkdir -p "$AUTOSTART_DIR"
cp "$SCRIPT_DIR/config/discern-discord.desktop" "$AUTOSTART_DIR/"
echo "  XDG autostart entry created."

if command -v systemctl &>/dev/null; then
    mkdir -p "$SYSTEMD_DIR"
    cp "$SCRIPT_DIR/config/discern-discord.service" "$SYSTEMD_DIR/"
    systemctl --user daemon-reload
    echo "  systemd user service installed."
else
    echo "  systemd not found, using XDG autostart only."
fi

# ── PATH check ─────────────────────────────────────────────────
echo "[5/5] Checking PATH..."

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "  WARNING: $BIN_DIR is not in your PATH."
    SHELL_NAME="$(basename "${SHELL:-bash}")"
    case "$SHELL_NAME" in
        zsh)  RC="~/.zshrc" ;;
        fish) RC="~/.config/fish/config.fish" ;;
        *)    RC="~/.bashrc" ;;
    esac
    echo "  Add this to $RC:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "Quick start:"
echo "  1. Edit config:  nano ~/.config/discern-discord/settings.json"
echo "     Set \"discord_username\" to your Discord display name."
echo ""
echo "  2. Test:         discern-discord &"
echo "     Then:         python3 $SCRIPT_DIR/test/send_test_notification.py dm"
echo ""
if command -v systemctl &>/dev/null; then
    echo "  3. As service:   systemctl --user enable --now discern-discord"
fi
