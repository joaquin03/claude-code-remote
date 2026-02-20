# Slash-Command Picker — Design Doc

**Date:** 2026-02-20
**Status:** Approved

## Problem

The mobile voice wrapper has no way to discover or quickly invoke Claude Code slash commands and installed skills. On the desktop CLI you type `/` and get an interactive picker. On mobile you have to remember every command name by heart.

## Goal

When the user types `/` in the input bar, show a tappable filtered list of all available commands (Claude Code built-ins + installed skills + plugin skills). Tapping a command fills the input with the command name followed by a trailing space and positions the cursor there, ready for arguments.

## Scope

**In scope:**
- New `GET /commands` backend endpoint
- Inline dropdown panel in the existing HTML/JS frontend
- Live filtering as user types after `/`
- Tap-to-fill with argument placeholder (trailing space)
- Dismiss on tap-outside or Esc

**Out of scope:**
- Full-screen picker
- Argument validation or autocomplete
- Persistent command chips bar
- Any changes to `/send`, `/key`, `/stream`, ttyd, or tmux setup

## Architecture

### Backend: `GET /commands`

Reads three sources at request time (no caching — cheap and always fresh):

| Source | Method |
|--------|--------|
| Built-in Claude Code commands | Hardcoded list in Python |
| Custom skills | Walk `~/.claude/skills/*/SKILL.md`, parse `name:` and `description:` |
| Plugin skills | Walk `~/.claude/plugins/cache/*/skills/*/SKILL.md`, same parsing |

**Response schema:**
```json
[
  {
    "command": "/exit",
    "description": "Exit Claude Code",
    "takes_args": false
  },
  {
    "command": "/superpowers:brainstorming",
    "description": "Turn ideas into designs through collaborative dialogue",
    "takes_args": true
  }
]
```

**Built-in command list (hardcoded):**
`/exit`, `/help`, `/clear`, `/memory`, `/model`, `/doctor`, `/review`, `/status`, `/bug`, `/compact`, `/config`, `/cost`, `/ide`, `/init`, `/login`, `/logout`, `/mcp`, `/migrate-installer`, `/pr-comments`, `/reset`, `/terminal`, `/vim`

### Frontend: Inline Dropdown

**Trigger:** `input` event on the text field. If `value.startsWith('/')` → fetch `/commands` (cached in JS after first fetch) → render panel. Otherwise → hide panel.

**Panel position:** Fixed, anchored directly above the quick-keys bar. Max height 40% of viewport with internal `overflow-y: scroll`.

**Panel row layout:**
```
/command-name    Short description text
```
Command name in monospace, description in smaller dimmer text, same line.

**Live filtering:** On each `input` event, filter the cached list where `command.includes(value)` (case-insensitive). Show all results if value is exactly `/`.

**Tap behavior:** Set `input.value = command + ' '`, move cursor to end, close panel. Does NOT send.

**Dismiss:** Tap anywhere outside the panel, or Esc keydown on the input.

**Styling:** Dark theme (#252525 background, #ccc text, #007aff accent on hover/active), monospace font for command name, `font-size: 13px` description.

## Files Changed

| File | Change |
|------|--------|
| `scripts/voice-wrapper.py` | Add `GET /commands` endpoint + update HTML/JS with dropdown panel |

That's the only file. No new dependencies — uses only Python stdlib (`os`, `glob`, `re`) plus existing FastAPI.

## Data Flow

```
User types "/" in input
    → JS: input event fires
    → JS: fetch /commands (or use cache)
    → Python: read disk, return JSON
    → JS: render filtered panel above input bar

User types "/bra"
    → JS: filter cached list to items containing "bra"
    → JS: re-render panel (3-4 matching items)

User taps "/superpowers:brainstorming"
    → JS: set input.value = "/superpowers:brainstorming "
    → JS: close panel

User types their prompt and hits Send
    → existing /send endpoint (unchanged)
```

## Testing

- Open `http://100.67.193.38:8888` on phone
- Type `/` → panel appears with full list
- Type `/mem` → only `/memory` and any skill with "mem" in name visible
- Tap a no-args command → fills input, ready to send
- Tap a skill command → fills input with trailing space, cursor positioned for args
- Tap outside → panel closes
- Press Esc → panel closes
- Install a new skill → reload page → new skill appears in list
