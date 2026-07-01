"""Tests for novyx-hygiene v2 CLI."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from novyx_hygiene.cli import cli, _generate_session_id, _format_ago, _format_resume


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_dirs(tmp_path):
    """Redirect all storage to tmp and isolate config from the real environment."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    with (
        patch.dict(os.environ, {}, clear=False),
        patch("novyx_hygiene.storage.CONFIG_DIR", tmp_path),
        patch("novyx_hygiene.storage.CONFIG_FILE", tmp_path / "config.json"),
        patch("novyx_hygiene.storage.SESSIONS_DIR", sessions_dir),
        patch("novyx_hygiene.storage.NOVYX_AVAILABLE", False),
    ):
        # get_config() overlays NOVYX_API_KEY from the env; drop it so tests
        # never read (or leak) the developer's real key.
        os.environ.pop("NOVYX_API_KEY", None)
        yield tmp_path


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestGenerateSessionId:
    def test_basic(self):
        sid = _generate_session_id("Building auth flow")
        assert "building-auth-flow" in sid

    def test_truncates_to_four_words(self):
        sid = _generate_session_id("one two three four five six")
        parts = sid.rsplit("-", 1)
        assert len(parts[0].split("-")) <= 4

    def test_strips_special_chars(self):
        sid = _generate_session_id("Fix bug #123!")
        assert "#" not in sid
        assert "!" not in sid

    def test_appends_date(self):
        sid = _generate_session_id("test")
        today = datetime.now().strftime("%m%d")
        assert sid.endswith(today)


class TestFormatAgo:
    def test_just_now(self):
        assert _format_ago(datetime.now()) == "just now"

    def test_minutes(self):
        dt = datetime.now() - timedelta(minutes=5)
        assert "minute" in _format_ago(dt)

    def test_hours(self):
        dt = datetime.now() - timedelta(hours=3)
        assert "hour" in _format_ago(dt)

    def test_days(self):
        dt = datetime.now() - timedelta(days=2)
        assert _format_ago(dt) == "2 days ago"


class TestFormatResume:
    def test_basic(self):
        session = {
            "session_id": "test-session",
            "task": "Building a feature",
            "working_directory": "/tmp/project",
            "git": {
                "branch": "main",
                "modified_files": ["file.py"],
                "staged_files": [],
                "untracked_files": [],
            },
            "decisions": ["Use PostgreSQL"],
            "status": "In progress",
            "timestamp": "2026-03-09T12:00:00",
        }
        output = _format_resume(session)
        assert "test-session" in output
        assert "Building a feature" in output
        assert "main" in output
        assert "file.py" in output
        assert "Use PostgreSQL" in output

    def test_minimal(self):
        session = {"session_id": "minimal", "task": "Quick fix"}
        output = _format_resume(session)
        assert "minimal" in output
        assert "Quick fix" in output


# ---------------------------------------------------------------------------
# CLI integration tests (local mode)
# ---------------------------------------------------------------------------


class TestSave:
    def test_save_creates_session(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["save", "Test task"])
        assert result.exit_code == 0
        assert "Saved:" in result.output
        files = list((tmp_dirs / "sessions").glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["task"] == "Test task"

    def test_save_custom_id(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["save", "Test", "-i", "custom-id"])
        assert result.exit_code == 0
        assert (tmp_dirs / "sessions" / "custom-id.json").exists()

    def test_save_with_decisions(self, runner, tmp_dirs):
        result = runner.invoke(
            cli,
            [
                "save",
                "Auth flow",
                "-d",
                "Use JWT",
                "-d",
                "PostgreSQL",
            ],
        )
        assert result.exit_code == 0
        files = list((tmp_dirs / "sessions").glob("*.json"))
        data = json.loads(files[0].read_text())
        assert len(data["decisions"]) == 2

    def test_save_with_status(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["save", "Done", "-s", "Completed"])
        assert result.exit_code == 0
        files = list((tmp_dirs / "sessions").glob("*.json"))
        data = json.loads(files[0].read_text())
        assert data["status"] == "Completed"

    def test_save_no_task_errors(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["save"])
        assert result.exit_code != 0

    def test_save_writes_hygiene_md(self, runner, tmp_dirs):
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["save", "Test md write"])
            md_path = Path(td) / ".claude" / "hygiene.md"
            assert md_path.exists()
            content = md_path.read_text()
            assert "Test md write" in content

    def test_save_no_md_flag(self, runner, tmp_dirs):
        with runner.isolated_filesystem() as td:
            result = runner.invoke(cli, ["save", "Test", "--no-md"])
            assert result.exit_code == 0
            assert not (Path(td) / ".claude" / "hygiene.md").exists()

    def test_auto_save_uses_cwd(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["save", "--auto", "--quiet"])
        assert result.exit_code == 0


class TestResume:
    def test_resume_latest(self, runner, tmp_dirs):
        session = {
            "session_id": "test-resume",
            "task": "Resume me",
            "timestamp": datetime.now().isoformat(),
            "working_directory": "/tmp",
            "git": {
                "branch": "main",
                "modified_files": [],
                "staged_files": [],
                "untracked_files": [],
            },
            "decisions": [],
            "status": "In progress",
        }
        (tmp_dirs / "sessions" / "test-resume.json").write_text(json.dumps(session))

        result = runner.invoke(cli, ["resume"])
        assert result.exit_code == 0
        assert "Resume me" in result.output

    def test_resume_by_id(self, runner, tmp_dirs):
        session = {
            "session_id": "specific",
            "task": "Specific task",
            "git": {"modified_files": [], "staged_files": [], "untracked_files": []},
        }
        (tmp_dirs / "sessions" / "specific.json").write_text(json.dumps(session))

        result = runner.invoke(cli, ["resume", "specific"])
        assert result.exit_code == 0
        assert "Specific task" in result.output

    def test_resume_not_found(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["resume", "nonexistent"])
        assert result.exit_code != 0

    def test_resume_no_sessions(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["resume"])
        assert result.exit_code != 0


class TestInject:
    def test_inject_outputs_context(self, runner, tmp_dirs):
        session = {
            "session_id": "inject-test",
            "task": "Injected task",
            "timestamp": datetime.now().isoformat(),
            "working_directory": "/tmp",
            "git": {
                "branch": "dev",
                "modified_files": ["app.py"],
                "staged_files": [],
                "untracked_files": [],
            },
            "decisions": ["Use FastAPI"],
            "status": "WIP",
        }
        (tmp_dirs / "sessions" / "inject-test.json").write_text(json.dumps(session))

        result = runner.invoke(cli, ["inject"])
        assert result.exit_code == 0
        assert "Injected task" in result.output
        assert "FastAPI" in result.output

    def test_inject_silent_when_no_session(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["inject"])
        assert result.exit_code == 0
        assert result.output.strip() == ""


class TestScore:
    def test_score_existing_session(self, runner, tmp_dirs):
        session = {
            "session_id": "score-test",
            "task": "Score me",
            "timestamp": datetime.now().isoformat(),
            "working_directory": "/tmp",
            "git": {
                "branch": "main",
                "modified_files": ["a.py"],
                "staged_files": [],
                "untracked_files": [],
            },
            "decisions": ["Good choice"],
            "status": "Halfway done",
        }
        (tmp_dirs / "sessions" / "score-test.json").write_text(json.dumps(session))

        result = runner.invoke(cli, ["score", "score-test"])
        assert result.exit_code == 0
        assert "Context Health:" in result.output

    def test_score_current(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["score"])
        assert result.exit_code == 0
        assert "Context Health:" in result.output

    def test_stale_session_scores_lower(self, runner, tmp_dirs):
        old_session = {
            "session_id": "stale",
            "task": "Old task",
            "timestamp": (datetime.now() - timedelta(hours=30)).isoformat(),
            "git": {"modified_files": [], "staged_files": [], "untracked_files": []},
            "decisions": [],
            "status": "In progress",
        }
        (tmp_dirs / "sessions" / "stale.json").write_text(json.dumps(old_session))

        result = runner.invoke(cli, ["score", "stale"])
        assert result.exit_code == 0
        # Should mention staleness
        assert "stale" in result.output.lower() or "old" in result.output.lower()


class TestInstall:
    def test_install_project(self, runner, tmp_dirs):
        with runner.isolated_filesystem() as td:
            result = runner.invoke(cli, ["install"])
            assert result.exit_code == 0
            settings_path = Path(td) / ".claude" / "settings.local.json"
            assert settings_path.exists()
            settings = json.loads(settings_path.read_text())
            assert "hooks" in settings
            assert "PreCompact" in settings["hooks"]
            assert "SessionStart" in settings["hooks"]

    def test_install_user(self, runner, tmp_dirs):
        with patch("novyx_hygiene.hooks.Path.home", return_value=tmp_dirs):
            result = runner.invoke(cli, ["install", "--user"])
            assert result.exit_code == 0

    def test_install_idempotent(self, runner, tmp_dirs):
        with runner.isolated_filesystem():
            runner.invoke(cli, ["install"])
            runner.invoke(cli, ["install"])
            settings_path = Path(".claude") / "settings.local.json"
            settings = json.loads(settings_path.read_text())
            # Should not duplicate hooks
            pre_compact = settings["hooks"]["PreCompact"]
            hygiene_hooks = [
                h
                for h in pre_compact
                if any(
                    "hygiene" in inner.get("command", "")
                    for inner in h.get("hooks", [])
                )
            ]
            assert len(hygiene_hooks) == 1


class TestUninstall:
    def test_uninstall_removes_hooks(self, runner, tmp_dirs):
        with runner.isolated_filesystem():
            runner.invoke(cli, ["install"])
            result = runner.invoke(cli, ["uninstall"])
            assert result.exit_code == 0
            assert "removed" in result.output.lower()

    def test_uninstall_no_hooks(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["uninstall"])
        assert result.exit_code == 0
        assert "No hooks" in result.output


class TestList:
    def test_list_sessions(self, runner, tmp_dirs):
        for i in range(3):
            session = {
                "session_id": f"session-{i}",
                "task": f"Task {i}",
                "timestamp": datetime.now().isoformat(),
                "status": "In progress",
            }
            (tmp_dirs / "sessions" / f"session-{i}.json").write_text(
                json.dumps(session)
            )

        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "session-0" in result.output

    def test_list_empty(self, runner, tmp_dirs):
        # Clear any sessions
        for f in (tmp_dirs / "sessions").glob("*.json"):
            f.unlink()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No sessions" in result.output


class TestConfig:
    def test_set_and_show(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["config", "set", "api_key", "nram_test_key_123"])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "nram_tes..." in result.output

    def test_show_empty(self, runner, tmp_dirs):
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "(empty)" in result.output


class TestVersion:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "2.0.0" in result.output
