#!/usr/bin/env python3
"""
Novyx Hygiene CLI — Context hygiene for agentic coding.

Commands:
  hygiene save       — Save session state (auto-writes .claude/hygiene.md)
  hygiene resume     — Print formatted context to paste (or read .claude/hygiene.md)
  hygiene inject     — Emit context to stdout (used by Claude Code hooks)
  hygiene score      — Check context health
  hygiene install    — Wire up Claude Code hooks for auto-save/inject
  hygiene uninstall  — Remove hooks
  hygiene list       — List saved sessions
  hygiene config     — Manage settings
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

import click

from . import __version__
from .storage import (
    save_session,
    load_session,
    list_sessions as storage_list_sessions,
    get_config,
    save_config,
)
from .context import get_git_context, score_session
from .writer import write_hygiene_md, render_hook_output
from .hooks import install_hooks, uninstall_hooks

# Keep reference to built-in list
_list = list


def _generate_session_id(description: str) -> str:
    words = description.lower().split()[:4]
    slug = "-".join(words)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    timestamp = datetime.now().strftime("%m%d")
    return f"{slug}-{timestamp}"


def _format_ago(dt: datetime) -> str:
    now = datetime.now()
    diff = now - dt
    if diff.days > 1:
        return f"{diff.days} days ago"
    elif diff.days == 1:
        return "1 day ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        mins = diff.seconds // 60
        return f"{mins} minute{'s' if mins > 1 else ''} ago"
    else:
        return "just now"


@click.group()
@click.version_option(version=__version__)
def cli():
    """Novyx Hygiene - Context hygiene for agentic coding."""
    pass


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("task", required=False)
@click.option("--decision", "-d", multiple=True, help="Key decision to record")
@click.option("--status", "-s", default="In progress", help="Current status")
@click.option("--session-id", "-i", help="Custom session ID")
@click.option("--auto", is_flag=True, hidden=True, help="Called by hook (uses last task or cwd)")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
@click.option("--no-md", is_flag=True, help="Skip writing .claude/hygiene.md")
def save(task, decision, status, session_id, auto, quiet, no_md):
    """Save current session state."""
    if not task and auto:
        # Auto-save: try to load last session's task, or use cwd basename
        last = load_session()
        if last:
            task = last.get("task", Path(os.getcwd()).name)
            if not session_id:
                session_id = last.get("session_id")
            # Carry forward decisions
            if not decision and last.get("decisions"):
                decision = tuple(last["decisions"])
        else:
            task = Path(os.getcwd()).name
    elif not task:
        click.echo("Error: task description required. Usage: hygiene save \"your task\"", err=True)
        raise SystemExit(1)

    if not session_id:
        session_id = _generate_session_id(task)

    git = get_git_context()

    session = {
        "session_id": session_id,
        "task": task,
        "timestamp": datetime.now().isoformat(),
        "working_directory": os.getcwd(),
        "git": git,
        "decisions": _list(decision),
        "status": status,
    }

    result = save_session(session)

    # Write .claude/hygiene.md
    md_path = None
    if not no_md:
        try:
            md_path = write_hygiene_md(session)
        except (OSError, PermissionError) as e:
            if not quiet:
                click.echo(f"  (could not write hygiene.md: {e})", err=True)

    if not quiet:
        click.echo(f"Saved: {session_id}")
        click.echo(f"  Task: {task}")
        all_files = set(
            git.get("modified_files", [])
            + git.get("staged_files", [])
            + git.get("untracked_files", [])
        )
        click.echo(f"  Files: {len(all_files)}")
        click.echo(f"  Decisions: {len(decision)}")
        if result.get("cloud"):
            click.echo("  Synced to Novyx Cloud")
        if md_path:
            click.echo(f"  Wrote {md_path}")


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("session_id", required=False)
def resume(session_id):
    """Resume a session. Prints formatted context to paste."""
    session = load_session(session_id)
    if not session:
        if session_id:
            click.echo(f"Session not found: {session_id}", err=True)
        else:
            click.echo("No sessions found.", err=True)
        raise SystemExit(1)

    click.echo(_format_resume(session))


# ---------------------------------------------------------------------------
# inject (for hooks — writes to stdout which Claude reads)
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("session_id", required=False)
def inject(session_id):
    """Emit session context to stdout for Claude Code hook injection."""
    session = load_session(session_id)
    if not session:
        # Silent — don't pollute Claude's context with errors
        return

    # Write to stdout (Claude reads this)
    sys.stdout.write(render_hook_output(session))
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("session_id", required=False)
def score(session_id):
    """Check context health score."""
    if session_id:
        session = load_session(session_id)
    else:
        # Score current state
        git = get_git_context()
        last = load_session()
        session = last or {
            "task": Path(os.getcwd()).name,
            "timestamp": datetime.now().isoformat(),
            "git": git,
            "decisions": [],
            "status": "Unknown",
        }
        # Update git to current state
        session["git"] = git

    result = score_session(session)

    click.echo(f"\nContext Health: {result['grade']} ({result['score']}/100)")
    click.echo("=" * 40)

    if result["issues"]:
        click.echo("\nIssues:")
        for issue in result["issues"]:
            click.echo(f"  - {issue}")

    if result["tips"]:
        click.echo("\nTips:")
        for tip in result["tips"]:
            click.echo(f"  - {tip}")

    if not result["issues"] and not result["tips"]:
        click.echo("\nContext looks clean.")


# ---------------------------------------------------------------------------
# install / uninstall
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--user", is_flag=True, help="Install to ~/.claude (all projects)")
def install(user):
    """Install Claude Code hooks for auto-save and auto-inject."""
    scope = "user" if user else "project"
    result = install_hooks(scope=scope)

    click.echo(f"Hooks installed: {result['settings_path']}")
    click.echo(f"  Events: {', '.join(result['events_configured'])}")
    click.echo()
    click.echo("What this does:")
    click.echo("  - Before /compact: auto-saves your session")
    click.echo("  - After compact/clear/resume: injects last context into Claude")
    click.echo()
    click.echo("Claude will now remember where you left off automatically.")


@cli.command()
@click.option("--user", is_flag=True, help="Uninstall from ~/.claude")
def uninstall(user):
    """Remove Claude Code hooks."""
    scope = "user" if user else "project"
    removed = uninstall_hooks(scope=scope)
    if removed:
        click.echo("Hooks removed.")
    else:
        click.echo("No hooks found to remove.")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@cli.command(name="list")
@click.option("--limit", "-n", default=10, help="Number of sessions to show")
def list_cmd(limit):
    """List saved sessions."""
    sessions = storage_list_sessions(limit=limit)

    if not sessions:
        click.echo("No sessions found.")
        return

    click.echo(f"\n{'ID':<30} {'Task':<40} {'Saved':<15} {'Status'}")
    click.echo("-" * 95)

    for s in sessions:
        sid = s.get("session_id", "unknown")[:28]
        task = s.get("task", "")[:38]
        status = s.get("status", "")[:15]
        try:
            dt = datetime.fromisoformat(s["timestamp"])
            ago = _format_ago(dt)
        except (ValueError, TypeError, KeyError):
            ago = "?"
        click.echo(f"  {sid:<28} {task:<40} {ago:<15} {status}")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@cli.group()
def config():
    """Manage configuration."""
    pass


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a config value."""
    cfg = get_config()
    cfg[key] = value
    save_config(cfg)
    click.echo(f"Set {key}")


@config.command(name="show")
def config_show():
    """Show current configuration."""
    cfg = get_config()
    if not cfg:
        click.echo("(empty)")
        return

    for key, value in cfg.items():
        if "key" in key.lower() or "secret" in key.lower():
            masked = value[:8] + "..." if len(value) > 12 else "***"
            click.echo(f"  {key}: {masked}")
        else:
            click.echo(f"  {key}: {value}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_resume(session: dict) -> str:
    """Format session for display."""
    lines = [
        "",
        "=" * 50,
        f"SESSION: {session.get('session_id', 'unknown')}",
        "=" * 50,
        "",
        f"Task: {session.get('task', 'No description')}",
        f"Status: {session.get('status', 'Unknown')}",
        f"Saved: {session.get('timestamp', 'unknown')}",
        f"Directory: {session.get('working_directory', 'unknown')}",
    ]

    git = session.get("git", {})
    if git.get("branch"):
        lines.append(f"Branch: {git['branch']}")

    decisions = session.get("decisions", [])
    if decisions:
        lines.extend(["", "Decisions:"])
        for i, d in enumerate(decisions[:10], 1):
            lines.append(f"  {i}. {d}")

    all_files = set(
        git.get("modified_files", [])
        + git.get("staged_files", [])
        + git.get("untracked_files", [])
    )
    if all_files:
        lines.extend(["", "Files in flight:"])
        for f in sorted(all_files)[:15]:
            lines.append(f"  - {f}")

    if git.get("recent_commits"):
        lines.extend(["", "Recent commits:"])
        for c in git["recent_commits"][:5]:
            lines.append(f"  - {c}")

    lines.extend(["", "Paste this into your new session to continue.", ""])
    return "\n".join(lines)


def main():
    cli()


if __name__ == "__main__":
    main()
