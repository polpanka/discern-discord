#!/usr/bin/env python3
"""Send fake Discord-style notifications to test the notifier.

Usage:
    python3 send_test_notification.py dm       # Simulates a DM         → red
    python3 send_test_notification.py mention   # Simulates an @mention  → red
    python3 send_test_notification.py generic   # Simulates a generic    → blue
    python3 send_test_notification.py everyone  # Simulates an @everyone → red
    python3 send_test_notification.py clear     # Simulates badge clear  → grey
"""

import sys
import time
import dbus

notifications = {
    "dm": ("Mario Rossi", "Ciao! Come stai?"),
    "mention": ("Server Amici (#generale)", "@Paolo guarda questo link"),
    "generic": ("Server Amici (#generale)", "Luigi: qualcuno ha visto il film?"),
    "everyone": ("Server Lavoro (#annunci)", "Boss: @everyone riunione alle 15"),
}

kind = sys.argv[1] if len(sys.argv) > 1 else "generic"

if kind == "clear":
    import subprocess
    result = subprocess.run(
        [
            "gdbus", "emit",
            "--session",
            "--object-path", "/discord_notifier_test",
            "--signal", "com.canonical.Unity.LauncherEntry.Update",
            "\"application://discord\"",
            "{'count': <int64 0>, 'count-visible': <false>}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    print("Sent LauncherEntry badge clear → notifier should reset to grey")
    sys.exit(0)

if kind not in notifications:
    print(f"Usage: {sys.argv[0]} [{' | '.join(notifications)} | clear]")
    sys.exit(1)

summary, body = notifications[kind]

bus = dbus.SessionBus()

for attempt in range(3):
    try:
        notify = dbus.Interface(
            bus.get_object(
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
            ),
            "org.freedesktop.Notifications",
        )
        notify.Notify(
            "Discord",
            dbus.UInt32(0),
            "discord",
            summary,
            body,
            [],
            {},
            dbus.Int32(5000),
        )
        print(f"Sent '{kind}' notification: {summary} — {body}")
        break
    except dbus.exceptions.DBusException as exc:
        if attempt < 2 and "UnknownMethod" in str(exc):
            print(f"Notification daemon not ready, retrying ({attempt + 1}/3)...")
            time.sleep(2)
        else:
            print(
                f"ERROR: {exc}\n\n"
                "The notification daemon is not running. This usually means\n"
                "GNOME Shell hasn't registered org.freedesktop.Notifications yet.\n"
                "Try again in a few seconds, or check: "
                "gdbus call --session -d org.freedesktop.Notifications "
                "-o /org/freedesktop/Notifications "
                "-m org.freedesktop.Notifications.GetServerInformation",
                file=sys.stderr,
            )
            sys.exit(1)
