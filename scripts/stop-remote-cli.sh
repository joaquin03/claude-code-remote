#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"

echo "Stopping remote CLI services..."

# Stop ttyd
if [ -f "$LOG_DIR/ttyd.pid" ]; then
    kill "$(cat "$LOG_DIR/ttyd.pid")" 2>/dev/null && echo "ttyd stopped" || echo "ttyd was not running"
    rm -f "$LOG_DIR/ttyd.pid"
else
    pkill -f "ttyd" 2>/dev/null && echo "ttyd stopped" || echo "ttyd was not running"
fi

# Stop voice wrapper
if [ -f "$LOG_DIR/voice-wrapper.pid" ]; then
    kill "$(cat "$LOG_DIR/voice-wrapper.pid")" 2>/dev/null && echo "voice wrapper stopped" || echo "voice wrapper was not running"
    rm -f "$LOG_DIR/voice-wrapper.pid"
else
    pkill -f "voice-wrapper" 2>/dev/null && echo "voice wrapper stopped" || echo "voice wrapper was not running"
fi

# Stop caffeinate
if [ -f "$LOG_DIR/caffeinate.pid" ]; then
    kill "$(cat "$LOG_DIR/caffeinate.pid")" 2>/dev/null && echo "caffeinate stopped" || echo "caffeinate was not running"
    rm -f "$LOG_DIR/caffeinate.pid"
else
    pkill -f "caffeinate" 2>/dev/null && echo "caffeinate stopped" || echo "caffeinate was not running"
fi

echo ""
echo "Services stopped. tmux session 'claude' is still alive."
echo "To kill it too: tmux kill-session -t claude"
