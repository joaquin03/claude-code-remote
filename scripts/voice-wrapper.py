#!/usr/bin/env python3
"""Voice dictation wrapper for Claude Code on iPhone.

Serves a mobile-optimized page with:
- SSE-streamed tmux pane output (replaces ttyd iframe — more reliable on iOS Safari)
- Native text input for dictation
- Quick-key buttons for common terminal actions
Text is injected into the tmux session via `tmux send-keys`.
"""

import asyncio
import json
import subprocess
import shutil
import glob
import os
import re

HOME = os.path.expanduser("~")

BUILTIN_COMMANDS = [
    {"command": "/bug",               "description": "Report a Claude Code bug",          "takes_args": False},
    {"command": "/clear",             "description": "Clear conversation history",         "takes_args": False},
    {"command": "/compact",           "description": "Compact conversation with summary",  "takes_args": True},
    {"command": "/config",            "description": "Manage configuration",               "takes_args": True},
    {"command": "/cost",              "description": "Show token usage and cost",          "takes_args": False},
    {"command": "/doctor",            "description": "Check Claude Code installation",     "takes_args": False},
    {"command": "/exit",              "description": "Exit Claude Code",                   "takes_args": False},
    {"command": "/help",              "description": "Show help",                          "takes_args": True},
    {"command": "/ide",               "description": "Connect to IDE",                     "takes_args": False},
    {"command": "/init",              "description": "Initialize project with CLAUDE.md",  "takes_args": False},
    {"command": "/login",             "description": "Sign in to Claude",                  "takes_args": False},
    {"command": "/logout",            "description": "Sign out from Claude",               "takes_args": False},
    {"command": "/mcp",               "description": "Manage MCP servers",                 "takes_args": True},
    {"command": "/memory",            "description": "Edit memory (CLAUDE.md)",            "takes_args": False},
    {"command": "/migrate-installer", "description": "Migrate to latest installer",        "takes_args": False},
    {"command": "/model",             "description": "Set or show current AI model",       "takes_args": True},
    {"command": "/pr-comments",       "description": "View pull request comments",         "takes_args": False},
    {"command": "/reset",             "description": "Reset to empty project context",     "takes_args": False},
    {"command": "/resume",            "description": "Resume a previous conversation",     "takes_args": True},
    {"command": "/review",            "description": "Request code review",                "takes_args": False},
    {"command": "/status",            "description": "Show account and system status",     "takes_args": False},
    {"command": "/terminal",          "description": "Run a terminal command",             "takes_args": True},
    {"command": "/vim",               "description": "Enter vim mode",                     "takes_args": False},
]


def _parse_skill_md(path: str):
    """Return (name, description) from a SKILL.md frontmatter, or (None, '') on failure."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        m = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not m:
            return None, ""
        fm = m.group(1)
        name_m = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
        desc_m = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
        name = name_m.group(1).strip().strip('"') if name_m else None
        desc = desc_m.group(1).strip().strip('"') if desc_m else ""
        return name, desc
    except Exception:
        return None, ""


def _collect_skill_commands() -> list:
    """Read ~/.claude/skills/ and ~/.claude/plugins/cache/ and return command dicts."""
    commands = []
    seen: set = set()

    # 1. Custom skills: ~/.claude/skills/<skill-name>/SKILL.md
    for path in glob.glob(f"{HOME}/.claude/skills/*/SKILL.md"):
        name, desc = _parse_skill_md(path)
        if name and name not in seen:
            seen.add(name)
            commands.append({"command": f"/{name}", "description": desc, "takes_args": True})

    # 2. Plugin skills (recursive glob catches both path variants)
    for path in glob.glob(f"{HOME}/.claude/plugins/cache/**/SKILL.md", recursive=True):
        parts = path.split(os.sep)
        try:
            cache_idx = parts.index("cache")
            plugin_name = parts[cache_idx + 2]   # marketplace / plugin / version / ...
        except (ValueError, IndexError):
            continue
        name, desc = _parse_skill_md(path)
        if not name:
            continue
        key = (plugin_name, name)
        if key in seen:
            continue
        seen.add(key)
        cmd = f"/{plugin_name}:{name}" if plugin_name != name else f"/{name}"
        commands.append({"command": cmd, "description": desc, "takes_args": True})

    return sorted(commands, key=lambda c: c["command"])

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

TMUX = shutil.which("tmux") or "/opt/homebrew/bin/tmux"
TAILSCALE = shutil.which("tailscale") or "/usr/local/bin/tailscale"
WRAPPER_PORT = 8888
TMUX_SESSION = "claude"


app = FastAPI()


def get_tailscale_ip():
    result = subprocess.run(
        [TAILSCALE, "ip", "-4"], capture_output=True, text=True
    )
    return result.stdout.strip()


class TextInput(BaseModel):
    text: str


class KeyInput(BaseModel):
    key: str


@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Claude Code Remote</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body {
            height: 100%;
            background: #1a1a1a;
            overflow: hidden;
            font-family: -apple-system, system-ui, sans-serif;
            touch-action: manipulation;
        }
        .container {
            display: flex;
            flex-direction: column;
            height: 100vh;
            height: 100dvh;
        }
        #terminal {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
            background: #0d0d0d;
            -webkit-overflow-scrolling: touch;
        }
        #terminal pre {
            font-family: 'Menlo', 'Monaco', 'Consolas', monospace;
            font-size: 12px;
            line-height: 1.4;
            color: #e0e0e0;
            white-space: pre-wrap;
            word-break: break-all;
        }
        .quick-keys {
            display: flex;
            gap: 4px;
            padding: 4px 6px;
            background: #252525;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            flex-shrink: 0;
        }
        .quick-keys button {
            padding: 8px 14px;
            font-size: 14px;
            font-family: 'Menlo', monospace;
            border: 1px solid #555;
            border-radius: 4px;
            background: #333;
            color: #ccc;
            cursor: pointer;
            white-space: nowrap;
            flex-shrink: 0;
        }
        .quick-keys button:active { background: #555; }
        .input-bar {
            display: flex;
            gap: 6px;
            padding: 6px;
            background: #2d2d2d;
            border-top: 1px solid #444;
            flex-shrink: 0;
        }
        .input-bar input {
            flex: 1;
            padding: 10px 12px;
            font-size: 16px;
            border: 1px solid #555;
            border-radius: 8px;
            background: #1a1a1a;
            color: #fff;
            outline: none;
        }
        .input-bar input:focus { border-color: #007aff; }
        .input-bar button {
            padding: 10px 18px;
            font-size: 16px;
            font-weight: 600;
            border: none;
            border-radius: 8px;
            background: #007aff;
            color: #fff;
            cursor: pointer;
            white-space: nowrap;
        }
        .input-bar button:active { background: #005bb5; }
        .status {
            font-size: 11px;
            color: #555;
            text-align: right;
            padding: 2px 8px;
            background: #1a1a1a;
            flex-shrink: 0;
        }
        .status.connected { color: #4a9; }
        .status.disconnected { color: #a44; }
    </style>
</head>
<body>
    <div class="container">
        <div id="terminal"><pre id="output">Connecting...</pre></div>
        <div class="status disconnected" id="status">disconnected</div>
        <div class="quick-keys">
            <button onclick="sendKey('Up')">&#9650;</button>
            <button onclick="sendKey('Down')">&#9660;</button>
            <button onclick="sendKey('Tab')">Tab</button>
            <button onclick="sendKey('Escape')">Esc</button>
            <button onclick="sendKey('C-c')">Ctrl+C</button>
            <button onclick="sendKey('Enter')">Enter</button>
            <button onclick="sendKey('C-l')">Clear</button>
            <button onclick="newSession()">New</button>
            <button onclick="resumeSession()">Resume</button>
        </div>
        <div class="input-bar">
            <input type="text" id="cmd"
                   placeholder="Dictate or type here..."
                   autocomplete="off"
                   autocorrect="on"
                   enterkeyhint="send" />
            <button onclick="sendText()">Send</button>
        </div>
    </div>
    <script>
        const input = document.getElementById('cmd');
        const output = document.getElementById('output');
        const terminal = document.getElementById('terminal');
        const statusEl = document.getElementById('status');
        let autoScroll = true;

        // SSE stream for terminal output
        function connect() {
            const es = new EventSource('/stream');
            es.onopen = () => {
                statusEl.textContent = 'connected';
                statusEl.className = 'status connected';
            };
            es.onmessage = (e) => {
                const text = JSON.parse(e.data);
                output.textContent = text;
                if (autoScroll) {
                    terminal.scrollTop = terminal.scrollHeight;
                }
            };
            es.onerror = () => {
                statusEl.textContent = 'reconnecting...';
                statusEl.className = 'status disconnected';
                es.close();
                setTimeout(connect, 2000);
            };
        }

        // Pause auto-scroll when user scrolls up
        terminal.addEventListener('scroll', () => {
            const atBottom = terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 40;
            autoScroll = atBottom;
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendText();
            }
        });

        async function sendText(override) {
            const text = override || input.value.trim();
            if (!text) return;
            try {
                await fetch('/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                if (!override) {
                    input.value = '';
                    input.focus();
                }
            } catch (err) {
                console.error('Send failed:', err);
            }
        }

        async function sendKey(key) {
            try {
                await fetch('/key', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key })
                });
            } catch (err) {
                console.error('Key send failed:', err);
            }
        }

        async function newSession() {
            await sendText('/exit');
            setTimeout(() => sendText('claude'), 1500);
        }

        async function resumeSession() {
            await sendText('/exit');
            setTimeout(() => sendText('claude --resume'), 1500);
        }

        connect();
        input.focus();
    </script>
</body>
</html>"""


@app.get("/stream")
async def stream_output():
    """Stream tmux pane content via Server-Sent Events."""
    async def event_generator():
        prev = None
        while True:
            try:
                result = subprocess.run(
                    [TMUX, "capture-pane", "-t", TMUX_SESSION, "-p", "-S", "-200"],
                    capture_output=True, text=True, timeout=5,
                )
                current = result.stdout
                if current != prev:
                    yield f"data: {json.dumps(current)}\n\n"
                    prev = current
            except Exception:
                pass
            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/commands")
async def get_commands():
    """Return all available Claude Code commands and installed skills."""
    return list(BUILTIN_COMMANDS) + _collect_skill_commands()


@app.post("/send")
async def send_text(payload: TextInput):
    """Send literal text to tmux, then press Enter."""
    subprocess.run(
        [TMUX, "send-keys", "-t", TMUX_SESSION, "-l", payload.text],
        timeout=5,
    )
    subprocess.run(
        [TMUX, "send-keys", "-t", TMUX_SESSION, "Enter"],
        timeout=5,
    )
    return {"status": "sent"}


@app.post("/key")
async def send_key(payload: KeyInput):
    """Send a special key (Escape, C-c, Enter, etc.) to tmux."""
    subprocess.run(
        [TMUX, "send-keys", "-t", TMUX_SESSION, payload.key],
        timeout=5,
    )
    return {"status": "sent"}


if __name__ == "__main__":
    ip = get_tailscale_ip()
    print(f"Voice wrapper: http://{ip}:{WRAPPER_PORT}")
    uvicorn.run(app, host=ip, port=WRAPPER_PORT)
