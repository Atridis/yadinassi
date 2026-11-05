#!/usr/bin/env bash
# Separate DESIGNER-only bootstrap; never invokes the existing ENTERPRISE suites.
set -euo pipefail
umask 077
exec 2>/dev/null
[[ $# == 1 && "$1" =~ ^[0-9a-f]{32}$ ]]
mkdir -m 700 /tmp/home /tmp/runtime /tmp/demo-display
export XAUTHORITY=/tmp/demo-display/xauth
cookie=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
xauth -f "$XAUTHORITY" add "$DISPLAY" MIT-MAGIC-COOKIE-1 "$cookie" >/dev/null 2>&1
unset cookie
Xtigervnc "$DISPLAY" -geometry 1280x800 -depth 24 -rfbport -1 -nolisten tcp \
    -auth "$XAUTHORITY" >/tmp/demo-display/display.log 2>&1 &
x_pid=$!
trap 'kill "$x_pid" 2>/dev/null || true; wait "$x_pid" 2>/dev/null || true' EXIT
ready=false
for attempt in {1..40}; do
    kill -0 "$x_pid"
    if timeout 2s xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then ready=true; break; fi
    sleep 0.25
done
[ "$ready" = true ]
# Own a private session bus for the whole sequence; never use a host/session fallback.
# dbus-run-session retains the image's standard session policy and reaps its daemon.
[ -x /usr/bin/dbus-run-session ]
/usr/bin/dbus-run-session -- python3 -B /smoke/scripts/native_1c_demo_designer.py --inside-container "$1"
