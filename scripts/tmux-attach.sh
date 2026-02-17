#!/bin/bash
# Clear Claude Code env vars so a fresh session can launch inside tmux
unset CLAUDECODE
unset CLAUDE_CODE_ENTRYPOINT
unset CLAUDE_CODE_ENTRY_VERSION
unset CLAUDE_CODE_ENV_VERSION

# UTF-8 locale for Unicode/emoji rendering
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

# Apple Silicon: /opt/homebrew/bin/tmux | Intel Mac: /usr/local/bin/tmux
TMUX_BIN=$(which tmux 2>/dev/null || echo "/opt/homebrew/bin/tmux")
exec "$TMUX_BIN" new-session -A -s claude -c "$HOME"
