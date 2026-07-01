"""
Session storage — local JSON + optional Novyx cloud sync.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List

# Try to import novyx for cloud mode
try:
    from novyx import Novyx

    NOVYX_AVAILABLE = True
except ImportError:
    NOVYX_AVAILABLE = False

CONFIG_DIR = Path.home() / ".novyx_hygiene"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
SESSION_TAG = "hygiene-session"


def get_config() -> Dict[str, str]:
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
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_client() -> Optional[Any]:
    if not NOVYX_AVAILABLE:
        return None
    config = get_config()
    api_key = config.get("api_key") or os.getenv("NOVYX_API_KEY")
    if not api_key:
        return None
    try:
        return Novyx(api_key=api_key)
    except Exception:
        return None


def save_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Save session to local storage and optionally to Novyx cloud."""
    result = {"local": False, "cloud": False, "session_id": session["session_id"]}

    # Always save locally
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = SESSIONS_DIR / f"{session['session_id']}.json"
    with open(filepath, "w") as f:
        json.dump(session, f, indent=2)
    result["local"] = True
    result["local_path"] = str(filepath)

    # Try cloud sync
    client = get_client()
    if client:
        try:
            r = client.remember(
                observation=json.dumps(session),
                tags=[SESSION_TAG, session["session_id"], "session-snapshot"],
                importance=8,
            )
            result["cloud"] = True
            if r and r.get("id"):
                result["memory_id"] = r["id"]
        except Exception:
            pass

    return result


def load_session(session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load a session by ID (or most recent)."""
    # Try cloud first
    client = get_client()
    if client:
        try:
            query = session_id or "session-snapshot"
            tags = [session_id] if session_id else [SESSION_TAG]
            r = client.recall(query=query, tags=tags, limit=1)
            memories = r.memories if hasattr(r, "memories") else []
            if memories:
                return json.loads(memories[0]["observation"])
        except Exception:
            pass

    # Fall back to local
    if not SESSIONS_DIR.exists():
        return None

    if session_id:
        filepath = SESSIONS_DIR / f"{session_id}.json"
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return None

    # Most recent
    files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if files:
        with open(files[0]) as f:
            return json.load(f)
    return None


def list_sessions(limit: int = 10) -> List[Dict[str, Any]]:
    """List saved sessions."""
    sessions = []

    # Try cloud
    client = get_client()
    if client:
        try:
            r = client.recall(query="session-snapshot", tags=[SESSION_TAG], limit=limit)
            results = r.memories if hasattr(r, "memories") else []
            for mem in results:
                try:
                    data = json.loads(mem["observation"])
                    sessions.append(data)
                except (json.JSONDecodeError, KeyError):
                    continue
        except Exception:
            pass

    if not sessions:
        if SESSIONS_DIR.exists():
            files = sorted(
                SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            for f in files[:limit]:
                try:
                    with open(f) as fp:
                        sessions.append(json.load(fp))
                except (json.JSONDecodeError, IOError):
                    continue

    return sessions


def delete_session(session_id: str) -> bool:
    """Delete a session by ID."""
    filepath = SESSIONS_DIR / f"{session_id}.json"
    if filepath.exists():
        filepath.unlink()
        return True
    return False
