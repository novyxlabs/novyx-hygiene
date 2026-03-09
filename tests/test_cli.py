"""Tests for novyx-hygiene CLI."""

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from novyx_hygiene.cli import (
    cli,
    generate_session_id,
    format_resume_output,
    get_config,
    save_config,
    _format_ago,
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_config(tmp_path):
    """Redirect config and sessions to tmp dir."""
    with patch("novyx_hygiene.cli.CONFIG_DIR", tmp_path), \
         patch("novyx_hygiene.cli.CONFIG_FILE", tmp_path / "config.json"):
        yield tmp_path


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestGenerateSessionId:
    def test_basic(self):
        sid = generate_session_id("Building auth flow")
        assert "building-auth-flow" in sid

    def test_truncates_to_four_words(self):
        sid = generate_session_id("one two three four five six")
        # Should only have first 4 words before the timestamp
        parts = sid.rsplit("-", 1)  # split off MMDD timestamp
        assert len(parts[0].split("-")) <= 4

    def test_strips_special_chars(self):
        sid = generate_session_id("Fix bug #123!")
        assert "#" not in sid
        assert "!" not in sid

    def test_appends_date(self):
        sid = generate_session_id("test")
        today = datetime.now().strftime("%m%d")
        assert sid.endswith(today)


class TestFormatResumeOutput:
    def test_basic_session(self):
        session = {
            "session_id": "test-session",
            "task": "Building a feature",
            "working_directory": "/tmp/project",
            "git": {"branch": "main", "modified_files": ["file.py"]},
            "decisions": ["Use PostgreSQL"],
            "status": "In progress",
            "timestamp": "2026-03-09T12:00:00",
        }
        output = format_resume_output(session)
        assert "test-session" in output
        assert "Building a feature" in output
        assert "/tmp/project" in output
        assert "main" in output
        assert "file.py" in output
        assert "Use PostgreSQL" in output
        assert "In progress" in output

    def test_minimal_session(self):
        session = {"session_id": "minimal", "task": "Quick fix"}
        output = format_resume_output(session)
        assert "minimal" in output
        assert "Quick fix" in output

    def test_empty_decisions(self):
        session = {"session_id": "x", "task": "y", "decisions": []}
        output = format_resume_output(session)
        assert "Key Decisions" not in output


class TestFormatAgo:
    def test_just_now(self):
        assert _format_ago(datetime.now()) == "just now"

    def test_minutes(self):
        from datetime import timedelta
        dt = datetime.now() - timedelta(minutes=5)
        result = _format_ago(dt)
        assert "minute" in result

    def test_hours(self):
        from datetime import timedelta
        dt = datetime.now() - timedelta(hours=3)
        result = _format_ago(dt)
        assert "hour" in result

    def test_days(self):
        from datetime import timedelta
        dt = datetime.now() - timedelta(days=2)
        result = _format_ago(dt)
        assert "2 days ago" == result


# ---------------------------------------------------------------------------
# CLI integration tests (local mode — no Novyx API)
# ---------------------------------------------------------------------------


class TestSaveLocal:
    def test_save_creates_session_file(self, runner, tmp_config):
        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, ["save", "Test task"])
        assert result.exit_code == 0
        assert "Session saved locally" in result.output
        sessions_dir = tmp_config / "sessions"
        files = list(sessions_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["task"] == "Test task"
        assert data["status"] == "In progress"

    def test_save_custom_session_id(self, runner, tmp_config):
        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, ["save", "Test", "-i", "my-custom-id"])
        assert result.exit_code == 0
        filepath = tmp_config / "sessions" / "my-custom-id.json"
        assert filepath.exists()

    def test_save_with_decisions(self, runner, tmp_config):
        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, [
                "save", "Building auth",
                "-d", "Use JWT",
                "-d", "PostgreSQL for users",
            ])
        assert result.exit_code == 0
        files = list((tmp_config / "sessions").glob("*.json"))
        data = json.loads(files[0].read_text())
        assert len(data["decisions"]) == 2
        assert "Use JWT" in data["decisions"]

    def test_save_with_status(self, runner, tmp_config):
        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, ["save", "Done task", "-s", "Completed"])
        assert result.exit_code == 0
        files = list((tmp_config / "sessions").glob("*.json"))
        data = json.loads(files[0].read_text())
        assert data["status"] == "Completed"


class TestResumeLocal:
    def test_resume_latest(self, runner, tmp_config):
        # Save a session first
        sessions_dir = tmp_config / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session = {
            "session_id": "test-resume",
            "task": "Resume me",
            "timestamp": datetime.now().isoformat(),
            "working_directory": "/tmp",
            "git": {"branch": "main", "modified_files": []},
            "decisions": [],
            "status": "In progress",
        }
        (sessions_dir / "test-resume.json").write_text(json.dumps(session))

        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, ["resume"])
        assert result.exit_code == 0
        assert "Resume me" in result.output
        assert "test-resume" in result.output

    def test_resume_by_id(self, runner, tmp_config):
        sessions_dir = tmp_config / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session = {"session_id": "specific", "task": "Specific task"}
        (sessions_dir / "specific.json").write_text(json.dumps(session))

        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, ["resume", "specific"])
        assert result.exit_code == 0
        assert "Specific task" in result.output

    def test_resume_not_found(self, runner, tmp_config):
        (tmp_config / "sessions").mkdir(parents=True, exist_ok=True)
        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, ["resume", "nonexistent"])
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_resume_no_sessions(self, runner, tmp_config):
        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, ["resume"])
        assert result.exit_code == 0
        assert "No sessions found" in result.output


class TestListLocal:
    def test_list_sessions(self, runner, tmp_config):
        sessions_dir = tmp_config / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            session = {
                "session_id": f"session-{i}",
                "task": f"Task {i}",
                "timestamp": datetime.now().isoformat(),
                "status": "In progress",
            }
            (sessions_dir / f"session-{i}.json").write_text(json.dumps(session))

        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "SESSIONS" in result.output
        assert "session-0" in result.output

    def test_list_empty(self, runner, tmp_config):
        with patch("novyx_hygiene.cli.NOVYX_AVAILABLE", False):
            result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No sessions found" in result.output


class TestConfig:
    def test_config_set_and_show(self, runner, tmp_config):
        result = runner.invoke(cli, ["config", "set", "api_key", "nram_test_key_123"])
        assert result.exit_code == 0
        assert "Set api_key" in result.output

        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        # API key should be masked
        assert "nram_tes..." in result.output

    def test_config_show_empty(self, runner, tmp_config):
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "(empty)" in result.output


class TestVersion:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output
