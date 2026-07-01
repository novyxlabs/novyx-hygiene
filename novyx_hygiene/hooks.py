"""
Claude Code hooks integration — auto-save and auto-inject session context.

Installs hooks into .claude/settings.local.json so that:
  - PreCompact: auto-saves session state before compaction
  - SessionStart (compact/clear/resume): injects last session context via stdout
"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional


HOOK_EVENTS: Dict[str, List[Dict[str, Any]]] = {
    "PreCompact": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "hygiene save --auto --quiet",
                    "timeout": 10,
                }
            ]
        }
    ],
    "SessionStart": [
        {
            "matcher": "compact",
            "hooks": [
                {
                    "type": "command",
                    "command": "hygiene inject",
                    "timeout": 5,
                }
            ],
        },
        {
            "matcher": "clear",
            "hooks": [
                {
                    "type": "command",
                    "command": "hygiene inject",
                    "timeout": 5,
                }
            ],
        },
        {
            "matcher": "resume",
            "hooks": [
                {
                    "type": "command",
                    "command": "hygiene inject",
                    "timeout": 5,
                }
            ],
        },
    ],
}


def install_hooks(project_dir: Optional[str] = None, scope: str = "project") -> Dict[str, Any]:
    """Install Claude Code hooks for auto-save and auto-inject.

    Args:
        project_dir: Project root. Defaults to cwd.
        scope: 'project' writes .claude/settings.local.json,
               'user' writes ~/.claude/settings.json.

    Returns:
        Dict with status info.
    """
    # Check that hygiene CLI is available
    hygiene_path = shutil.which("hygiene")
    if not hygiene_path:
        # Try python -m
        hygiene_path = f"{sys.executable} -m novyx_hygiene.cli"

    if scope == "user":
        settings_path = Path.home() / ".claude" / "settings.json"
    else:
        if not project_dir:
            project_dir = os.getcwd()
        settings_path = Path(project_dir) / ".claude" / "settings.local.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing settings
    existing = {}
    if settings_path.exists():
        try:
            with open(settings_path) as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Merge hooks (don't clobber existing hooks from other tools)
    hooks = existing.get("hooks", {})
    for event, event_hooks in HOOK_EVENTS.items():
        if event not in hooks:
            hooks[event] = []
        # Check if hygiene hooks already installed
        existing_commands = set()
        for h in hooks[event]:
            for inner in h.get("hooks", []):
                if inner.get("command"):
                    existing_commands.add(inner["command"])
        for new_hook in event_hooks:
            for inner in new_hook.get("hooks", []):
                if inner.get("command") not in existing_commands:
                    hooks[event].append(new_hook)
                    break

    existing["hooks"] = hooks
    with open(settings_path, "w") as f:
        json.dump(existing, f, indent=2)

    return {
        "settings_path": str(settings_path),
        "events_configured": list(HOOK_EVENTS.keys()),
        "scope": scope,
    }


def uninstall_hooks(project_dir: Optional[str] = None, scope: str = "project") -> bool:
    """Remove hygiene hooks from Claude Code settings."""
    if scope == "user":
        settings_path = Path.home() / ".claude" / "settings.json"
    else:
        if not project_dir:
            project_dir = os.getcwd()
        settings_path = Path(project_dir) / ".claude" / "settings.local.json"

    if not settings_path.exists():
        return False

    try:
        with open(settings_path) as f:
            settings = json.load(f)
    except (json.JSONDecodeError, IOError):
        return False

    hooks = settings.get("hooks", {})
    changed = False
    for event in list(hooks.keys()):
        original_len = len(hooks[event])
        hooks[event] = [
            h
            for h in hooks[event]
            if not any("hygiene" in inner.get("command", "") for inner in h.get("hooks", []))
        ]
        if len(hooks[event]) != original_len:
            changed = True
        if not hooks[event]:
            del hooks[event]

    if changed:
        settings["hooks"] = hooks
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)

    return changed
