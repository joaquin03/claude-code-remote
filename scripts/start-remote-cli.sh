#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

# Load .env from project root if present
ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    # shellcheck disable=SC1090
    set -a; source "$ENV_FILE"; set +a
fi

# Port defaults (can be overridden in .env)
WRAPPER_PORT="${WRAPPER_PORT:-8888}"
TTYD_PORT="${TTYD_PORT:-7681}"

# Get Tailscale IP
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null)
if [ -z "$TAILSCALE_IP" ]; then
    echo "ERROR: Tailscale not running or no IPv4 address" >&2
    exit 1
fi

echo "Tailscale IP: $TAILSCALE_IP"

# Kill any existing ttyd processes
pkill -f "ttyd" 2>/dev/null || true
sleep 1

# Keep Mac awake (kill any existing caffeinate first)
pkill -f "caffeinate" 2>/dev/null || true
caffeinate -d -i -s &
CAFFEINATE_PID=$!
echo "caffeinate running (PID: $CAFFEINATE_PID)"

# Start ttyd bound to Tailscale IP only
# Uses tmux-attach.sh wrapper for clean argument handling
ttyd \
    --port "$TTYD_PORT" \
    --interface "$TAILSCALE_IP" \
    --writable \
    -t fontSize=14 \
    -t lineHeight=1.2 \
    -t cursorBlink=true \
    -t cursorStyle=block \
    -t scrollback=10000 \
    -t 'fontFamily="Menlo, Monaco, Consolas, monospace, Apple Color Emoji, Segoe UI Emoji"' \
    "$SCRIPT_DIR/tmux-attach.sh" \
    >> "$LOG_DIR/ttyd.log" 2>&1 &

TTYD_PID=$!
echo "ttyd running (PID: $TTYD_PID) on http://$TAILSCALE_IP:$TTYD_PORT"

# Start voice dictation wrapper
pkill -f "voice-wrapper" 2>/dev/null || true
WRAPPER_PORT="$WRAPPER_PORT" TTYD_PORT="$TTYD_PORT" \
    /Users/joaquinanduano/.pyenv/versions/3.9.16/bin/python3 "$SCRIPT_DIR/voice-wrapper.py" >> "$LOG_DIR/voice-wrapper.log" 2>&1 &
WRAPPER_PID=$!
echo "voice wrapper running (PID: $WRAPPER_PID) on http://$TAILSCALE_IP:$WRAPPER_PORT"

echo ""
echo "=== Remote CLI Ready ==="
echo "Terminal:  http://$TAILSCALE_IP:$TTYD_PORT"
echo "Voice UI:  http://$TAILSCALE_IP:$WRAPPER_PORT"
echo ""
echo "Open the Voice UI URL in Chrome on your iPhone (Tailscale must be active)."
echo "To stop: $SCRIPT_DIR/stop-remote-cli.sh"

# Save PIDs for stop script
echo "$TTYD_PID" > "$LOG_DIR/ttyd.pid"
echo "$CAFFEINATE_PID" > "$LOG_DIR/caffeinate.pid"
echo "$WRAPPER_PID" > "$LOG_DIR/voice-wrapper.pid"

# Watchdog: restart ttyd if it crashes, exit cleanly on SIGTERM
KEEP_RUNNING=true
trap 'KEEP_RUNNING=false; kill $TTYD_PID 2>/dev/null' TERM INT

while $KEEP_RUNNING; do
    wait $TTYD_PID 2>/dev/null || true
    if ! $KEEP_RUNNING; then
        break
    fi
    echo "[$(date)] ttyd exited, restarting in 5s..." >> "$LOG_DIR/ttyd.log"
    sleep 5
    ttyd \
        --port "$TTYD_PORT" \
        --interface "$TAILSCALE_IP" \
        --writable \
        -t fontSize=14 \
        -t lineHeight=1.2 \
        -t cursorBlink=true \
        -t cursorStyle=block \
        -t scrollback=10000 \
        "$SCRIPT_DIR/tmux-attach.sh" \
        >> "$LOG_DIR/ttyd.log" 2>&1 &
    TTYD_PID=$!
    echo "$TTYD_PID" > "$LOG_DIR/ttyd.pid"
    echo "[$(date)] ttyd restarted (PID: $TTYD_PID)" >> "$LOG_DIR/ttyd.log"
done
