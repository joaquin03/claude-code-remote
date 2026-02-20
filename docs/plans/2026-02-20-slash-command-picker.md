# Slash-Command Picker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When the user types `/` in the mobile input bar, show a live-filtered tappable list of all Claude Code commands and installed skills.

**Architecture:** One new backend endpoint (`GET /commands`) reads skill dirs from disk and returns a JSON list. One new frontend dropdown panel (HTML/CSS/JS inside the existing `index()` string) triggers on input, filters live, and fills the input field on tap.

**Tech Stack:** Python stdlib (`glob`, `os`, `re`) for disk reading, FastAPI for the endpoint, vanilla JS + CSS (using safe DOM methods — no innerHTML) — no new dependencies.

---

## Background: File Locations

Before touching code, understand the two sources of skills on disk:

**Custom skills:** `~/.claude/skills/<skill-name>/SKILL.md`
```
---
name: frontend-dev
description: Build React components with TypeScript...
---
```
Command format: `/<skill-name>`

**Plugin skills:** `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md`
(and occasionally `.../<version>/.claude/skills/<skill>/SKILL.md` — voicemode uses this path)
```
---
name: brainstorming
description: "You MUST use this before any creative work..."
---
```
Command format: `/<plugin>:<skill-name>`

Multiple version directories exist for the same plugin — deduplicate by `(plugin_name, skill_name)`.

---

## Task 1: Add `GET /commands` Backend Endpoint

**File:** `scripts/voice-wrapper.py`

### Step 1: Add imports and helpers at the top of the file

After the existing imports (after `import shutil`), add:

```python
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
```

### Step 2: Add the `GET /commands` endpoint

Add this after the `@app.get("/stream")` block, before `@app.post("/send")`:

```python
@app.get("/commands")
async def get_commands():
    """Return all available Claude Code commands and installed skills."""
    return list(BUILTIN_COMMANDS) + _collect_skill_commands()
```

### Step 3: Smoke-test the endpoint manually

With the voice wrapper running, curl it:

```bash
curl -s http://100.67.193.38:8888/commands | python3 -c \
  "import json,sys; cmds=json.load(sys.stdin); print(len(cmds), 'commands'); [print(c['command']) for c in cmds]"
```

Expected: 25+ commands listed, starting with `/bug`, `/clear`, ..., followed by `/frontend-dev`, `/superpowers:brainstorming`, etc.

### Step 4: Commit

```bash
cd /Users/joaquinanduano/Sites/claude-code-remote
git add scripts/voice-wrapper.py
git commit -m "feat: add /commands endpoint that reads built-ins and installed skills"
```

---

## Task 2: Add the Dropdown Panel (CSS + JS)

**File:** `scripts/voice-wrapper.py` — inside the HTML string returned by `index()`

### Step 1: Add CSS for the command panel

Inside the `<style>` block, after `.status.disconnected { color: #a44; }`, add:

```css
        #cmd-panel {
            display: none;
            position: fixed;
            left: 0; right: 0;
            bottom: 0;
            max-height: 40vh;
            overflow-y: auto;
            background: #252525;
            border-top: 1px solid #444;
            z-index: 50;
            -webkit-overflow-scrolling: touch;
        }
        #cmd-panel.open { display: block; }
        .cmd-row {
            display: flex;
            align-items: baseline;
            gap: 10px;
            padding: 10px 14px;
            border-bottom: 1px solid #333;
            cursor: pointer;
        }
        .cmd-row:active { background: #333; }
        .cmd-name {
            font-family: 'Menlo', monospace;
            font-size: 14px;
            color: #7bf;
            white-space: nowrap;
            flex-shrink: 0;
        }
        .cmd-desc {
            font-size: 12px;
            color: #888;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
```

### Step 2: Add the panel `<div>` to the body

Add `<div id="cmd-panel"></div>` directly after the closing `</div>` of `.container`:

```html
    </div>
    <div id="cmd-panel"></div>
```

### Step 3: Add JS for the dropdown

In the `<script>` block, after the line `let autoScroll = true;`, add:

```javascript
        // Slash-command picker — uses safe DOM methods, no innerHTML
        let cmdCache = null;
        const panel = document.getElementById('cmd-panel');

        async function loadCommands() {
            if (cmdCache) return cmdCache;
            const r = await fetch('/commands');
            cmdCache = await r.json();
            return cmdCache;
        }

        function positionPanel() {
            const inputBar = document.querySelector('.input-bar');
            const quickKeys = document.querySelector('.quick-keys');
            panel.style.bottom = (inputBar.offsetHeight + quickKeys.offsetHeight) + 'px';
        }

        function renderPanel(commands) {
            while (panel.firstChild) panel.removeChild(panel.firstChild);
            commands.forEach(c => {
                const row = document.createElement('div');
                row.className = 'cmd-row';

                const nameSpan = document.createElement('span');
                nameSpan.className = 'cmd-name';
                nameSpan.textContent = c.command;

                const descSpan = document.createElement('span');
                descSpan.className = 'cmd-desc';
                descSpan.textContent = c.description;

                row.appendChild(nameSpan);
                row.appendChild(descSpan);

                const handler = () => pickCmd(c.command);
                row.addEventListener('click', handler);
                row.addEventListener('touchend', (e) => { e.preventDefault(); handler(); });

                panel.appendChild(row);
            });
        }

        async function onInputChange() {
            const val = input.value;
            if (!val.startsWith('/')) {
                panel.classList.remove('open');
                return;
            }
            const cmds = await loadCommands();
            const lower = val.toLowerCase();
            const filtered = cmds.filter(c => c.command.toLowerCase().includes(lower));
            if (filtered.length === 0) {
                panel.classList.remove('open');
                return;
            }
            positionPanel();
            renderPanel(filtered);
            panel.classList.add('open');
        }

        function pickCmd(command) {
            input.value = command + ' ';
            const len = input.value.length;
            input.setSelectionRange(len, len);
            input.focus();
            panel.classList.remove('open');
        }

        document.addEventListener('touchstart', (e) => {
            if (!panel.contains(e.target) && e.target !== input) {
                panel.classList.remove('open');
            }
        });
```

### Step 4: Update the keydown listener to handle Esc

Find this existing block in the script:

```javascript
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendText();
            }
        });
```

Replace it with:

```javascript
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendText();
            }
            if (e.key === 'Escape') {
                panel.classList.remove('open');
            }
        });
```

### Step 5: Wire up the input event

Add this line immediately before `connect();`:

```javascript
        input.addEventListener('input', onInputChange);
```

### Step 6: Manual test in browser

Restart the voice wrapper (see Task 1 Step 4 for the restart command), then open `http://100.67.193.38:8888` and verify:

- [ ] Type `/` → panel appears above input bar with full command list
- [ ] Type `/mem` → list filters to `/memory` only (or any skill with "mem")
- [ ] Type `/sup` → shows `/superpowers:brainstorming` and siblings
- [ ] Click any command → input fills with `command ` (trailing space), panel closes
- [ ] Delete input back to empty → panel disappears
- [ ] Type `/nomatch` → panel disappears (no results)
- [ ] Press Esc → panel closes
- [ ] Click outside panel → panel closes

### Step 7: Test on phone

Open `http://100.67.193.38:8888` on iPhone (hard-reload: close tab and reopen).

- [ ] Tap the input → keyboard appears
- [ ] Type `/` → panel appears above the keyboard
- [ ] Scroll the panel — all commands are reachable
- [ ] Tap `/superpowers:brainstorming` → input fills with `/superpowers:brainstorming `, panel closes
- [ ] Type an idea and hit Send → sends correctly

### Step 8: Copy to installed location and restart

```bash
cp /Users/joaquinanduano/Sites/claude-code-remote/scripts/voice-wrapper.py \
   /Users/joaquinanduano/.local/bin/remote-cli/voice-wrapper.py

pkill -f voice-wrapper 2>/dev/null || true
sleep 1
/Users/joaquinanduano/.pyenv/versions/3.9.16/bin/python3 \
  /Users/joaquinanduano/.local/bin/remote-cli/voice-wrapper.py \
  >> /Users/joaquinanduano/.local/bin/logs/voice-wrapper.log 2>&1 &
sleep 2 && lsof -i :8888 | grep LISTEN
```

Expected: `python3.9 ... TCP ... :ddi-tcp-1 (LISTEN)`

### Step 9: Commit

```bash
cd /Users/joaquinanduano/Sites/claude-code-remote
git add scripts/voice-wrapper.py
git commit -m "feat: add slash-command picker dropdown to mobile voice UI"
```

---

## Done

The feature is complete when:
- `GET /commands` returns 25+ commands including builtins and all installed skills
- Typing `/` on phone shows a scrollable panel above the keyboard
- Tapping a command fills the input with the command and a trailing space
- The panel filters live as the user types and closes on outside tap or Esc
