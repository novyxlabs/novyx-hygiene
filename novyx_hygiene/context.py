"""
Context analysis — git state, session health scoring, drift detection.
"""

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


def get_git_context() -> Dict[str, Any]:
    """Capture rich git context for the current working directory."""
    result = {
        "branch": None,
        "dirty": False,
        "modified_files": [],
        "staged_files": [],
        "untracked_files": [],
        "recent_commits": [],
        "repo_root": None,
    }

    cwd = os.getcwd()

    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=cwd
        )
        if root.returncode != 0:
            return result
        result["repo_root"] = root.stdout.strip()

        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=cwd
        )
        if branch.returncode == 0:
            result["branch"] = branch.stdout.strip()

        # Staged files
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=cwd
        )
        if staged.returncode == 0 and staged.stdout.strip():
            result["staged_files"] = staged.stdout.strip().split("\n")[:20]

        # Modified (unstaged)
        modified = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, cwd=cwd
        )
        if modified.returncode == 0 and modified.stdout.strip():
            result["modified_files"] = modified.stdout.strip().split("\n")[:20]

        # Untracked
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, cwd=cwd
        )
        if untracked.returncode == 0 and untracked.stdout.strip():
            result["untracked_files"] = untracked.stdout.strip().split("\n")[:20]

        result["dirty"] = bool(
            result["modified_files"] or result["staged_files"] or result["untracked_files"]
        )

        # Recent commits
        log = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True, text=True, cwd=cwd
        )
        if log.returncode == 0 and log.stdout.strip():
            result["recent_commits"] = log.stdout.strip().split("\n")[:5]

    except (FileNotFoundError, OSError):
        pass

    return result


def get_session_context(task: str, decisions: List[str], status: str) -> Dict[str, Any]:
    """Build full session context snapshot."""
    git = get_git_context()

    return {
        "task": task,
        "timestamp": datetime.now().isoformat(),
        "working_directory": os.getcwd(),
        "git": git,
        "decisions": decisions,
        "status": status,
    }


def score_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Score context health. Returns score (0-100) and issues."""
    score = 100
    issues = []
    tips = []

    # Age check
    try:
        saved = datetime.fromisoformat(session.get("timestamp", ""))
        age_hours = (datetime.now() - saved).total_seconds() / 3600
        if age_hours > 24:
            score -= 20
            issues.append(f"Session is {age_hours:.0f}h old — context may be stale")
            tips.append("Run `hygiene save` to refresh")
        elif age_hours > 8:
            score -= 10
            issues.append(f"Session is {age_hours:.0f}h old")
    except (ValueError, TypeError):
        score -= 5
        issues.append("No timestamp — can't assess freshness")

    # File sprawl
    git = session.get("git", {})
    all_files = set(
        git.get("modified_files", [])
        + git.get("staged_files", [])
        + git.get("untracked_files", [])
    )
    if len(all_files) > 15:
        score -= 15
        issues.append(f"{len(all_files)} files in flight — high sprawl")
        tips.append("Consider committing completed work before continuing")
    elif len(all_files) > 8:
        score -= 5
        issues.append(f"{len(all_files)} files in flight")

    # Directory diversity (proxy for mixed concerns)
    if all_files:
        dirs = set()
        for f in all_files:
            parts = Path(f).parts
            if len(parts) > 1:
                dirs.add(parts[0])
        if len(dirs) > 4:
            score -= 10
            issues.append(f"Changes span {len(dirs)} top-level directories — possible mixed concerns")
            tips.append("Consider splitting into focused sessions")

    # Decision tracking
    decisions = session.get("decisions", [])
    if not decisions:
        score -= 5
        tips.append("Track decisions with `hygiene save -d 'reason for choice'`")

    # Status clarity
    status = session.get("status", "")
    if not status or status == "In progress":
        score -= 5
        tips.append("Use specific status: `hygiene save -s 'auth flow 70% done'`")

    score = max(0, min(100, score))

    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

    return {
        "score": score,
        "grade": grade,
        "issues": issues,
        "tips": tips,
    }
