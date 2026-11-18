#!/usr/bin/env python3
"""
discern-discord — Colored notification indicator for Discord on Linux.

Tray icon that shows:
  Red  = DM or @mention
  Blue = generic channel message
  Grey = nothing unread

https://github.com/polpanka/discern-discord
"""

import json
import logging
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import dbus
import dbus.mainloop.glib
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3
except (ValueError, ImportError):
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3
    except (ValueError, ImportError):
        print(
            "ERROR: Install gir1.2-ayatanaappindicator3-0.1 or gir1.2-appindicator3-0.1",
            file=sys.stderr,
        )
        sys.exit(1)

logger = logging.getLogger("discern-discord")

ICON_DIR = Path(__file__).resolve().parent / "icons"
CONFIG_DIR = Path.home() / ".config" / "discern-discord"
STRING_RE = re.compile(r'^\s+string\s+"(.*)"$')

DEDUP_WINDOW_SECS = 2
FOCUS_CHECK_INTERVAL_SECS = 5
FOCUS_RESET_DELAY_SECS = 3
FOCUS_MAX_FAILURES = 5


class State:
    IDLE = "idle"
    GENERIC = "blue"
    DIRECT = "red"


class DiscordNotifier:
    def __init__(self, config: dict):
        self.config = config
        self.state = State.IDLE
        self.username = config.get("discord_username", "")
        self.mention_keywords = [k.lower() for k in config.get("mention_keywords", [])]

        self._last_notif_key = None
        self._last_notif_time = 0.0
        self._pending_messages: list[tuple[str, str, str]] = []  # (summary, body, type)
        self._discord_focused_since = None
        self._discord_is_focused = False
        self._focus_tool = None  # "xdotool", "xprop", or None
        self._focus_failures = 0

        self._build_indicator()
        self._start_monitor()

    # ── Tray icon ──────────────────────────────────────────────

    def _build_indicator(self):
        self.indicator = AppIndicator3.Indicator.new(
            "discern-discord",
            str(ICON_DIR / "discern-discord-idle.svg"),
            AppIndicator3.IndicatorCategory.COMMUNICATIONS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Discord: no new messages")

        menu = Gtk.Menu()

        clear_item = Gtk.MenuItem(label="Clear")
        clear_item.connect("activate", lambda *_: self._set_state(State.IDLE))
        menu.append(clear_item)

        sep = Gtk.SeparatorMenuItem()
        menu.append(sep)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def _set_state(self, new_state: str):
        if self.state == new_state:
            return
        self.state = new_state
        icon_path = str(ICON_DIR / f"discern-discord-{new_state}.svg")
        self.indicator.set_icon_full(icon_path, new_state)

        if new_state == State.IDLE:
            self._pending_messages.clear()
            self.indicator.set_title("Discord: no new messages")
        else:
            self.indicator.set_title(self._build_tooltip())
        logger.info("State → %s", new_state)

    def _build_tooltip(self) -> str:
        if not self._pending_messages:
            return "Discord: no new messages"
        lines = []
        for summary, body, ntype in self._pending_messages[-5:]:
            preview = body.split("\n")[0]
            if len(preview) > 80:
                preview = preview[:77] + "..."
            tag = "DM" if ntype == State.DIRECT and "#" not in summary else ""
            if tag:
                lines.append(f"[{tag}] {summary}: {preview}")
            else:
                lines.append(f"{summary}: {preview}")
        count = len(self._pending_messages)
        header = f"Discord: {count} unread message{'s' if count != 1 else ''}"
        if count > 5:
            lines.append(f"  ... and {count - 5} more")
        return header + "\n" + "\n".join(lines)

    # ── D-Bus monitoring ───────────────────────────────────────

    def _start_monitor(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()

        self._watch_launcher_entry()
        self._start_focus_watcher()

        if not self._try_eavesdrop():
            logger.info("Eavesdrop unavailable, falling back to dbus-monitor subprocess")
            self._start_dbus_monitor_subprocess()

    # ── LauncherEntry: badge clear detection ───────────────────

    def _watch_launcher_entry(self):
        self.bus.add_signal_receiver(
            self._on_launcher_entry_update,
            signal_name="Update",
            dbus_interface="com.canonical.Unity.LauncherEntry",
        )
        logger.info("Watching com.canonical.Unity.LauncherEntry for badge clear")

    def _on_launcher_entry_update(self, app_uri, properties):
        uri_lower = str(app_uri).lower()
        is_discord = "discord" in uri_lower

        count = properties.get("count", -1)
        count_visible = properties.get("count-visible", None)
        urgent = properties.get("urgent", None)

        if is_discord or logger.isEnabledFor(logging.DEBUG):
            logger.log(
                logging.INFO if is_discord else logging.DEBUG,
                "LauncherEntry: uri=%s count=%s visible=%s urgent=%s",
                app_uri, count, count_visible, urgent,
            )

        if not is_discord:
            return

        if count == 0 or (count_visible is not None and not count_visible):
            logger.info("Discord badge cleared (LauncherEntry) → idle")
            GLib.idle_add(self._set_state, State.IDLE)

    # ── Window focus: reset when user looks at Discord ─────────

    def _start_focus_watcher(self):
        self._detect_focus_tool()
        if self._focus_tool:
            thread = threading.Thread(target=self._focus_watcher_loop, daemon=True)
            thread.start()

    def _detect_focus_tool(self):
        for tool in ("xdotool", "xprop"):
            if subprocess.run(
                ["which", tool], capture_output=True
            ).returncode == 0:
                self._focus_tool = tool
                logger.info("Focus watcher: using %s, checking every %ds, reset after %ds",
                            tool, FOCUS_CHECK_INTERVAL_SECS, FOCUS_RESET_DELAY_SECS)
                return
        logger.info("Focus watcher: no tool available (install xdotool or xprop for auto-reset)")

    def _is_discord_focused(self) -> bool | None:
        if not self._focus_tool:
            return None
        try:
            if self._focus_tool == "xdotool":
                result = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowclassname"],
                    capture_output=True, text=True, timeout=2,
                )
                self._focus_failures = 0
                return "discord" in result.stdout.strip().lower()
            else:
                wid = subprocess.run(
                    ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                    capture_output=True, text=True, timeout=2,
                )
                parts = wid.stdout.strip().split()
                if not parts or parts[-1] == "0x0":
                    return False
                cls = subprocess.run(
                    ["xprop", "-id", parts[-1], "WM_CLASS"],
                    capture_output=True, text=True, timeout=2,
                )
                self._focus_failures = 0
                return "discord" in cls.stdout.lower()
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError,
                IndexError, ValueError):
            self._focus_failures += 1
            if self._focus_failures >= FOCUS_MAX_FAILURES:
                logger.warning("Focus detection failed %d times, disabling", self._focus_failures)
                self._focus_tool = None
            return None

    def _focus_watcher_loop(self):
        while self._focus_tool:
            time.sleep(FOCUS_CHECK_INTERVAL_SECS)

            focused = self._is_discord_focused()
            if focused is None:
                self._discord_is_focused = False
                continue

            self._discord_is_focused = focused

            if self.state == State.IDLE:
                self._discord_focused_since = None
                continue

            now = time.monotonic()
            if focused:
                if self._discord_focused_since is None:
                    self._discord_focused_since = now
                elif now - self._discord_focused_since >= FOCUS_RESET_DELAY_SECS:
                    logger.info("Discord focused for %ds → idle", FOCUS_RESET_DELAY_SECS)
                    GLib.idle_add(self._set_state, State.IDLE)
                    self._discord_focused_since = None
            else:
                self._discord_focused_since = None

    # ── Notification eavesdrop ─────────────────────────────────

    def _try_eavesdrop(self) -> bool:
        try:
            self.bus.add_match_string(
                "type='method_call',"
                "interface='org.freedesktop.Notifications',"
                "member='Notify',"
                "eavesdrop='true'"
            )
            self.bus.add_message_filter(self._dbus_filter)
            logger.info("Using D-Bus eavesdrop match rule")
            return True
        except dbus.exceptions.DBusException as exc:
            logger.debug("eavesdrop failed: %s", exc)
            return False

    def _dbus_filter(self, bus, message):
        if message.get_member() != "Notify":
            return dbus.lowlevel.HANDLER_RESULT_NOT_YET_HANDLED
        if message.get_type() != 1:  # 1 = METHOD_CALL, skip 2 = METHOD_RETURN
            return dbus.lowlevel.HANDLER_RESULT_NOT_YET_HANDLED
        try:
            args = message.get_args_list()
            app_name = str(args[0]) if args else ""
            if app_name.lower() == "discord":
                summary = str(args[3]) if len(args) > 3 else ""
                body = str(args[4]) if len(args) > 4 else ""
                GLib.idle_add(self._handle_notification, summary, body)
        except Exception as exc:
            logger.error("Error in filter: %s", exc)
        return dbus.lowlevel.HANDLER_RESULT_NOT_YET_HANDLED

    # ── dbus-monitor fallback ──────────────────────────────────

    def _start_dbus_monitor_subprocess(self):
        thread = threading.Thread(target=self._dbus_monitor_loop, daemon=True)
        thread.start()

    def _dbus_monitor_loop(self):
        while True:
            try:
                proc = subprocess.Popen(
                    [
                        "dbus-monitor",
                        "--session",
                        "interface='org.freedesktop.Notifications',member='Notify'",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
            except FileNotFoundError:
                logger.error("dbus-monitor not found — notification monitoring disabled")
                return

            in_notify = False
            strings: list[str] = []

            for raw_line in proc.stdout:
                line = raw_line.rstrip("\n")

                if "member=Notify" in line and "method call" in line:
                    in_notify = True
                    strings = []
                    continue

                if not in_notify:
                    continue

                m = STRING_RE.match(line)
                if m:
                    strings.append(m.group(1))
                    if len(strings) == 5:
                        if strings[0].lower() == "discord":
                            GLib.idle_add(self._handle_notification, strings[2], strings[3])
                        in_notify = False
                        strings = []
                    continue

                if line and not line.startswith(" ") and not line.startswith("\t"):
                    if len(strings) >= 4 and strings[0].lower() == "discord":
                        GLib.idle_add(self._handle_notification, strings[2], strings[3])
                    in_notify = False
                    strings = []

            proc.wait()
            logger.warning("dbus-monitor exited (code %s), restarting in 5s...", proc.returncode)
            time.sleep(5)

    # ── Classification ─────────────────────────────────────────

    def _handle_notification(self, summary: str, body: str):
        now = time.monotonic()
        key = (summary, body)
        if key == self._last_notif_key and (now - self._last_notif_time) < DEDUP_WINDOW_SECS:
            return
        self._last_notif_key = key
        self._last_notif_time = now

        ntype = self._classify(summary, body)

        self._pending_messages.append((summary, body, ntype))
        logger.info('notification: summary="%s" body="%s" → %s', summary, body, ntype)
        if ntype == State.DIRECT:
            self._set_state(State.DIRECT)
        elif self.state != State.DIRECT:
            self._set_state(State.GENERIC)
        else:
            self.indicator.set_title(self._build_tooltip())

    def _classify(self, summary: str, body: str) -> str:
        if "#" not in summary:
            return State.DIRECT

        body_lower = body.lower()

        if "@everyone" in body_lower or "@here" in body_lower:
            return State.DIRECT

        if self.username and f"@{self.username}".lower() in body_lower:
            return State.DIRECT

        for kw in self.mention_keywords:
            if kw in body_lower:
                return State.DIRECT

        return State.GENERIC


# ── Entry point ────────────────────────────────────────────────

def load_config() -> dict:
    config_file = CONFIG_DIR / "settings.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Invalid JSON in %s: %s — using defaults", config_file, exc)
    return {}


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    signal.signal(signal.SIGINT, lambda *_: Gtk.main_quit())
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())

    config = load_config()
    DiscordNotifier(config)

    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
