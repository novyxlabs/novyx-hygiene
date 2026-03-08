#!/usr/bin/env python3
"""
Novyx Hygiene CLI
Context hygiene for agentic coding sessions.
"""

import os
import sys
import json
import subprocess
import click
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Try to import novyx, fallback to mock for dev
try:
    from novyx_ram import NovyxRAMClient
    NOVYX_AVAILABLE = True
except ImportError:
    NOVYX_AVAILABLE = False

from . import __version__

# Config file location
CONFIG_DIR = Path.home() / ".novyx_hygiene"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Tags for session memories
SESSION_TAG = "hygiene-session"

# Keep reference to built-in list before it's shadowed by our command
_list = list


def get_config() -> Dict[str, str]:
    """Load config from file or env."""
    config = {}
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    if os.getenv("NOVYX_API_KEY"):
        config["api_key"] = os.getenv("NOVYX_API_KEY")
    
    return config


def save_config(config: Dict[str, str]):
    """Save config to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_client() -> Optional[Any]:
    """Get Novyx client if available."""
    if not NOVYX_AVAILABLE:
        return None
    
    config = get_config()
    api_key = config.get("api_key") or os.getenv("NOVYX_API_KEY")
    
    if not api_key:
        return None
    
    return NovyxRAMClient(api_key=api_key)


def generate_session_id(description: str) -> str:
    """Generate URL-safe session ID from description."""
    import re
    words = description.lower().split()[:4]
    slug = "-".join(words)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    timestamp = datetime.now().strftime("%m%d")
    return f"{slug}-{timestamp}"


def get_git_status() -> Dict[str, Any]:
    """Get current git status."""
    result = {
        "branch": "unknown",
        "dirty": False,
        "modified_files": [],
        "recent_commits": []
    }
    
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            check=True,
            cwd=os.getcwd()
        )
        
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        if branch.returncode == 0:
            result["branch"] = branch.stdout.strip()
        
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        if status.returncode == 0:
            lines = status.stdout.strip().split("\n")
            result["modified_files"] = [
                line[3:] for line in lines 
                if line and len(line) > 3
            ][:20]
            result["dirty"] = len(result["modified_files"]) > 0
        
        log = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        if log.returncode == 0:
            result["recent_commits"] = [
                line.strip() for line in log.stdout.strip().split("\n")
                if line.strip()
            ][:3]
            
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return result


def format_resume_output(session: Dict[str, Any]) -> str:
    """Format session for display/pasting."""
    lines = [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📋 SESSION CONTEXT: {session.get('session_id', 'unknown')}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🎯 Task: {session.get('task', 'No description')}",
    ]
    
    if session.get('working_directory'):
        lines.append(f"📂 Directory: {session['working_directory']}")
    
    if session.get('git', {}).get('branch'):
        lines.append(f"🌿 Branch: {session['git']['branch']}")
    
    if session.get('decisions'):
        lines.extend(["", "📝 Key Decisions:"])
        for i, decision in enumerate(session['decisions'][:5], 1):
            lines.append(f"  {i}. {decision}")
    
    if session.get('git', {}).get('modified_files'):
        lines.extend(["", "📁 Files in Flight:"])
        for f in session['git']['modified_files'][:10]:
            lines.append(f"  • {f}")
    
    if session.get('status'):
        lines.append(f"\n⚡ Status: {session['status']}")
    
    lines.extend([
        "",
        f"💾 Session ID: {session.get('session_id', 'unknown')}",
        f"   Saved: {session.get('timestamp', 'unknown')}",
        "",
        "Paste this into your Claude/Codex session to continue.",
        ""
    ])
    
    return "\n".join(lines)


@click.group()
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx):
    """Novyx Hygiene - Context hygiene for agentic coding."""
    # Ensure context object exists
    ctx.ensure_object(dict)


@cli.command()
@click.argument("task")
@click.option("--decision", "-d", multiple=True, help="Add a key decision")
@click.option("--status", "-s", default="In progress", help="Current status")
@click.option("--session-id", "-i", help="Custom session ID (auto-generated if not provided)")
def save(task, decision, status, session_id):
    """Save current session state to Novyx Core."""
    if not session_id:
        session_id = generate_session_id(task)
    
    git_info = get_git_status()
    
    session = {
        "session_id": session_id,
        "task": task,
        "timestamp": datetime.now().isoformat(),
        "working_directory": os.getcwd(),
        "git": git_info,
        "decisions": _list(decision),
        "status": status
    }
    
    client = get_client()
    
    if client:
        try:
            result = client.store(
                observation=json.dumps(session),
                tags=[SESSION_TAG, session_id],
                importance=8,
                metadata={
                    "session_id": session_id,
                    "task": task,
                    "timestamp": session["timestamp"],
                    "type": "session-snapshot"
                }
            )
            
            click.echo(f"✓ Session saved: {session_id}")
            click.echo(f"  Task: {task}")
            click.echo(f"  Files touched: {len(git_info.get('modified_files', []))}")
            click.echo(f"  Decisions: {len(decision)}")
            if result and result.get('memory_id'):
                click.echo(f"  Memory ID: {result['memory_id']}")
                
        except Exception as e:
            click.echo(f"✗ Failed to save to Novyx: {e}", err=True)
            _save_local(session)
    else:
        _save_local(session)


def _save_local(session):
    """Save session locally if Novyx unavailable."""
    local_dir = CONFIG_DIR / "sessions"
    local_dir.mkdir(parents=True, exist_ok=True)
    
    filepath = local_dir / f"{session['session_id']}.json"
    with open(filepath, "w") as f:
        json.dump(session, f, indent=2)
    
    click.echo(f"✓ Session saved locally: {session['session_id']}")
    click.echo(f"  Location: {filepath}")
    click.echo(f"  (Set NOVYX_API_KEY to enable cloud persistence)")


@cli.command()
@click.argument("session_id", required=False)
def resume(session_id):
    """Resume a session. Prints formatted context to paste."""
    
    client = get_client()
    
    if client and not session_id:
        try:
            results = client.search(
                query="session-snapshot",
                tags=[SESSION_TAG],
                limit=1
            )
            if results:
                session_data = json.loads(results[0]['observation'])
                click.echo(format_resume_output(session_data))
                return
        except Exception as e:
            click.echo(f"⚠ Novyx search failed: {e}", err=True)
    
    if client and session_id:
        try:
            results = client.search(
                query=session_id,
                tags=[session_id],
                limit=1
            )
            if results:
                session_data = json.loads(results[0]['observation'])
                click.echo(format_resume_output(session_data))
                return
        except Exception as e:
            click.echo(f"⚠ Novyx search failed: {e}", err=True)
    
    _resume_local(session_id)


def _resume_local(session_id):
    """Resume from local storage."""
    local_dir = CONFIG_DIR / "sessions"
    
    if not local_dir.exists():
        click.echo("✗ No sessions found locally.")
        return
    
    if session_id:
        filepath = local_dir / f"{session_id}.json"
        if filepath.exists():
            with open(filepath) as f:
                session = json.load(f)
            click.echo(format_resume_output(session))
            return
        else:
            click.echo(f"✗ Session not found: {session_id}")
            return
    
    files = sorted(local_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        with open(files[0]) as f:
            session = json.load(f)
        click.echo(format_resume_output(session))
    else:
        click.echo("✗ No sessions found.")


@cli.command(name="list")
@click.option("--limit", "-n", default=10, help="Number of sessions to show")
def list_sessions(limit):
    """List all saved sessions."""
    
    client = get_client()
    sessions = []
    
    if client:
        try:
            results = client.search(
                query="session-snapshot",
                tags=[SESSION_TAG],
                limit=limit
            )
            for r in results:
                try:
                    data = json.loads(r['observation'])
                    sessions.append({
                        'id': data.get('session_id', 'unknown'),
                        'task': data.get('task', 'No description'),
                        'timestamp': data.get('timestamp', ''),
                        'status': data.get('status', 'Unknown')
                    })
                except (json.JSONDecodeError, KeyError):
                    continue
        except Exception as e:
            click.echo(f"⚠ Novyx search failed: {e}", err=True)
    
    if not sessions:
        local_dir = CONFIG_DIR / "sessions"
        if local_dir.exists():
            files = sorted(local_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for f in files[:limit]:
                try:
                    with open(f) as fp:
                        data = json.load(fp)
                    sessions.append({
                        'id': data.get('session_id', f.stem),
                        'task': data.get('task', 'No description'),
                        'timestamp': data.get('timestamp', ''),
                        'status': data.get('status', 'Unknown')
                    })
                except (json.JSONDecodeError, IOError):
                    continue
    
    if not sessions:
        click.echo("No sessions found.")
        return
    
    click.echo("\nSESSIONS")
    click.echo("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    for s in sessions:
        click.echo(f"\n{s['id']}")
        click.echo(f"  {s['task'][:60]}{'...' if len(s['task']) > 60 else ''}")
        
        try:
            dt = datetime.fromisoformat(s['timestamp'])
            ago = _format_ago(dt)
            click.echo(f"  Saved: {ago}")
        except:
            pass
        
        click.echo(f"  Status: {s['status']}")


def _format_ago(dt):
    """Format datetime as human-readable 'ago'."""
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
    click.echo(f"✓ Set {key}")


@config.command(name="show")
def config_show():
    """Show current configuration."""
    cfg = get_config()
    
    click.echo("Configuration:")
    click.echo("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    for key, value in cfg.items():
        if "key" in key.lower() or "secret" in key.lower() or "password" in key.lower():
            masked = value[:8] + "..." if len(value) > 12 else "***"
            click.echo(f"  {key}: {masked}")
        else:
            click.echo(f"  {key}: {value}")
    
    if not cfg:
        click.echo("  (empty)")


if __name__ == "__main__":
    cli()
