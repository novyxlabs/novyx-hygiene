# Novyx Hygiene

[![PyPI version](https://badge.fury.io/py/novyx-hygiene.svg)](https://badge.fury.io/py/novyx-hygiene)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Context hygiene for agentic coding. Because manually exporting/copying/pasting session state is bullshit.**

Novyx Hygiene automates the session persistence workflow that Claude Code and Codex users are doing manually: export context, clear the session, paste it back, and hope nothing got lost.

Built on [Novyx Core](https://novyxlabs.com) — persistent memory that survives session resets.

---

## The Problem

You're coding with Claude Code or Codex. Your context fills up. You need to:

1. Run `/export` to copy everything
2. Run `/clear` to reset the session  
3. Paste the context back
4. Re-establish where you were

**Every. Single. Time.**

Worse: if you forget to export before compaction hits, you lose context. If you mix missions in one session, the context gets contaminated.

Reddit is full of [workarounds](https://www.reddit.com/r/ClaudeAI/comments/1p05r7p/my_claude_code_context_window_strategy_200k_is/). Velvet Shark wrote a [whole guide](https://velvetshark.com/openclaw-memory-masterclass) on manual context management.

**This shouldn't be manual.**

---

## The Solution

Three commands. Zero friction.

```bash
# Save your current session state
hygiene save "Implementing auth flow"

# Later... resume where you left off
hygiene resume
# Paste the output into your new Claude/Codex session

# See all your saved sessions
hygiene list
```

---

## 30-Second Demo

```bash
# You're deep in a coding session
$ hygiene save "Refactoring payment module - Stripe integration halfway done"
✓ Session saved: refactoring-payment-module
  Task: Refactoring payment module - Stripe integration halfway done
  Files touched: src/payments/stripe.py, tests/test_payments.py
  Decisions: 3
  Timestamp: 2026-03-08T12:46:00Z

# Context fills up, you clear the session
$ /clear

# Resume with full context
$ hygiene resume
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 SESSION CONTEXT: refactoring-payment-module
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 Task: Refactoring payment module - Stripe integration halfway done

📝 Key Decisions:
  • Using Stripe's new Payment Intents API (not Charges)
  • Webhook handler goes in src/webhooks/stripe.py
  • Keeping backward compatibility for existing customers

📁 Files in Flight:
  • src/payments/stripe.py (lines 45-120 modified)
  • tests/test_payments.py (new test file)

⚡ Status: In progress - webhook handler pending

💾 Session ID: refactoring-payment-module
   Saved: 2026-03-08T12:46:00Z

Paste this into your Claude/Codex session to continue.
```

---

## Installation

```bash
pip install novyx-hygiene
```

Set your Novyx API key:

```bash
export NOVYX_API_KEY="nram_your_key_here"
```

Or use the config command:

```bash
hygiene config set api_key nram_your_key_here
```

---

## Commands

### `hygiene save <task-description>`

Save current session state to Novyx Core.

```bash
hygiene save "Building user auth flow"
```

Captures:
- Task description
- Working directory
- Recent git status
- Files you've touched (from git)
- Any decisions you flag

### `hygiene resume [session-id]`

Print formatted context to paste into a new session.

```bash
# Resume last session
hygiene resume

# Resume specific session
hygiene resume refactoring-payment-module
```

### `hygiene list`

List all saved sessions.

```bash
hygiene list
```

Output:
```
SESSIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

refactoring-payment-module
  Building payment module - Stripe integration
  Saved: 2 hours ago
  Status: In progress

api-redesign
  Migrating from REST to GraphQL
  Saved: 1 day ago
  Status: Completed
```

### `hygiene config`

Manage configuration.

```bash
hygiene config set api_key nram_xxx
hygiene config show
```

---

## Why Novyx Core?

Novyx Hygiene uses [Novyx Core](https://novyxlabs.com) for persistence:

- **Semantic search** — Find sessions by description, not just ID
- **Integrity verification** — SHA-256 every artifact
- **Rollback** — Accidentally overwrote a session? Roll back.
- **Audit trail** — Know when you saved what

Your session state survives compaction, session resets, even computer restarts.

---

## Workflow Integration

### With Claude Code

```bash
# Before your session gets heavy
hygiene save "Task description here"

# When context fills up
/compact

# Or start fresh
/clear
hygiene resume
```

### With Codex CLI

```bash
# Save before you hit rate limits
codex "implement feature"
hygiene save "Feature X halfway done"

# Later, resume
codex
# Paste hygiene resume output
```

---

## Roadmap

**v1.0 (Tonight):** Save, resume, list. The core workflow.

**v2.0 (Soon):**
- Auto-monitor context usage
- MCP token tracking
- Smart pruning suggestions

---

## License

MIT © Novyx Labs

---

**Built by developers, for developers. Stop exporting and start shipping.**
