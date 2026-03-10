# Novyx Hygiene

[![PyPI version](https://badge.fury.io/py/novyx-hygiene.svg)](https://badge.fury.io/py/novyx-hygiene)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Automatic context persistence for Claude Code.** One command to install, then it just works.

Your sessions survive `/compact`, `/clear`, and restarts — no export, no paste, no manual steps.

---

## How It Works

```bash
pip install novyx-hygiene
hygiene install
```

That's it. From now on:

1. **Before `/compact`**: Hygiene auto-saves your session (task, decisions, files, git state)
2. **After compact/clear/resume**: Hygiene injects your context back into Claude automatically
3. **On disk**: A `.claude/hygiene.md` file keeps Claude oriented between sessions

No commands to remember. No context to paste. Claude just knows where you left off.

---

## The Problem

Context fills up. You `/compact` or `/clear`. Now Claude has amnesia.

The manual workaround:
1. `/export` to copy everything
2. `/clear` to reset
3. Paste context back
4. Re-establish where you were
5. **Repeat every time**

Worse: if compaction hits automatically, you lose context without warning.

**Novyx Hygiene makes this automatic.**

---

## Commands

### `hygiene install`

Wire up Claude Code hooks. Run once per project (or `--user` for all projects).

```bash
hygiene install          # Project-level (.claude/settings.local.json)
hygiene install --user   # User-level (~/.claude/settings.json)
```

Installs hooks for:
- `PreCompact` — auto-save before context compaction
- `SessionStart` — auto-inject after compact, clear, or resume

### `hygiene save <task>`

Manually save session state. Also auto-writes `.claude/hygiene.md`.

```bash
hygiene save "Building auth flow - JWT login done, registration next"
hygiene save "Refactoring payments" -d "Use Stripe Intents API" -d "Keep backward compat"
hygiene save "Bug fix" -s "Root cause found, writing test"
```

Options:
- `-d` / `--decision` — Record a key decision (repeatable)
- `-s` / `--status` — Set status (default: "In progress")
- `-i` / `--session-id` — Custom session ID
- `--no-md` — Skip writing `.claude/hygiene.md`

### `hygiene resume [session-id]`

Print session context for pasting (useful without hooks installed).

```bash
hygiene resume                    # Most recent session
hygiene resume auth-flow-0309     # Specific session
```

### `hygiene inject`

Emit context to stdout — used by Claude Code hooks internally. You don't need to call this directly.

### `hygiene score [session-id]`

Check context health: freshness, file sprawl, decision tracking, mixed concerns.

```bash
$ hygiene score
Context Health: B (80/100)
========================================

Issues:
  - 12 files in flight
  - Changes span 5 top-level directories — possible mixed concerns

Tips:
  - Consider committing completed work before continuing
  - Consider splitting into focused sessions
```

### `hygiene list`

List all saved sessions.

```bash
hygiene list
hygiene list -n 5
```

### `hygiene uninstall`

Remove hooks.

```bash
hygiene uninstall
hygiene uninstall --user
```

### `hygiene config`

```bash
hygiene config set api_key nram_xxx    # Enable cloud sync
hygiene config show
```

---

## What Gets Saved

Every session snapshot captures:

- **Task description** — what you're working on
- **Key decisions** — architectural choices, tradeoffs
- **Status** — where you left off
- **Git state** — branch, modified/staged/untracked files, recent commits
- **Working directory** — so you resume in the right place
- **Timestamp** — for freshness scoring

---

## Cloud Sync (Optional)

By default, sessions are saved locally to `~/.novyx_hygiene/sessions/`.

Add a [Novyx](https://novyxlabs.com) API key for cloud persistence, semantic search across sessions, and cross-machine sync:

```bash
pip install novyx-hygiene[novyx]
hygiene config set api_key nram_your_key_here
```

---

## How Hooks Work

After `hygiene install`, your `.claude/settings.local.json` gets:

```json
{
  "hooks": {
    "PreCompact": [
      { "hooks": [{ "type": "command", "command": "hygiene save --auto --quiet", "timeout": 10 }] }
    ],
    "SessionStart": [
      { "matcher": "compact", "hooks": [{ "type": "command", "command": "hygiene inject", "timeout": 5 }] },
      { "matcher": "clear", "hooks": [{ "type": "command", "command": "hygiene inject", "timeout": 5 }] },
      { "matcher": "resume", "hooks": [{ "type": "command", "command": "hygiene inject", "timeout": 5 }] }
    ]
  }
}
```

- **PreCompact hook** runs `hygiene save --auto` before compaction, capturing your current state
- **SessionStart hooks** run `hygiene inject` which outputs your last session context to stdout — Claude reads this automatically
- Hooks are additive: they won't overwrite your existing Claude Code hooks

---

## License

MIT

---

**Built by [Novyx Labs](https://novyxlabs.com). Stop exporting and start shipping.**
