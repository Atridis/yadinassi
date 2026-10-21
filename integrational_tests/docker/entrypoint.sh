#!/usr/bin/env bash
set -euo pipefail

export DISPLAY=:1

: "${VNC_PASSWORD:?VNC_PASSWORD is required}"

VNC_GEOMETRY="${VNC_GEOMETRY:-1600x900}"

mkdir -p "$HOME/.vnc"

export XDG_RUNTIME_DIR="/tmp/runtime-onec"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# Поддержка разных версий Ubuntu
if command -v tigervncpasswd >/dev/null 2>&1; then
    VNC_PASSWD_CMD=tigervncpasswd
elif command -v vncpasswd >/dev/null 2>&1; then
    VNC_PASSWD_CMD=vncpasswd
else
    echo "ERROR: VNC password utility not found"
    exit 1
fi

# Устанавливаем пароль VNC
printf '%s\n' "$VNC_PASSWORD" \
    | "$VNC_PASSWD_CMD" -f > "$HOME/.vnc/passwd"


chmod 600 "$HOME/.vnc/passwd"
unset VNC_PASSWORD

echo "Starting VNC server..."

Xtigervnc :1 \
    -geometry "$VNC_GEOMETRY" \
    -depth 24 \
    -rfbport 5901 \
    -SecurityTypes VncAuth \
    -PasswordFile "$HOME/.vnc/passwd" \
    -localhost=0 \
    -AlwaysShared \
    > "$HOME/.vnc/server.log" 2>&1 &

VNC_PID=$!

cleanup() {
    trap - EXIT INT TERM
    kill "${XFCE_PID:-}" "$VNC_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

# Ожидаем готовности X-сервера
for i in {1..40}; do
    if [ -S /tmp/.X11-unix/X1 ]; then
        break
    fi

    if ! kill -0 "$VNC_PID" 2>/dev/null; then
        cat "$HOME/.vnc/server.log"
        exit 1
    fi

    sleep 0.25
done

if [ ! -S /tmp/.X11-unix/X1 ]; then
    echo "X server failed to start"
    cat "$HOME/.vnc/server.log"
    exit 1
fi

echo "Starting XFCE..."

dbus-run-session -- startxfce4 \
    > "$HOME/.vnc/xfce.log" 2>&1 &

XFCE_PID=$!

echo "Desktop ready on VNC port 5901"

wait "$VNC_PID"
