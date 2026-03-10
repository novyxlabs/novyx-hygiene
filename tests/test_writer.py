"""Tests for writer module."""

from datetime import datetime
from pathlib import Path

from novyx_hygiene.writer import write_hygiene_md, render_hook_output


def _make_session(**overrides):
    session = {
        "session_id": "test-session",
        "task": "Building auth flow",
        "timestamp": datetime.now().isoformat(),
        "working_directory": "/tmp/project",
        "git": {
            "branch": "feature/auth",
            "modified_files": ["src/auth.py", "tests/test_auth.py"],
            "staged_files": ["src/models.py"],
            "untracked_files": ["notes.txt"],
            "recent_commits": ["abc1234 add login endpoint", "def5678 init project"],
        },
        "decisions": ["Use JWT tokens", "PostgreSQL for users"],
        "status": "Login endpoint done, registration next",
    }
    session.update(overrides)
    return session


class TestWriteHygieneMd:
    def test_creates_file(self, tmp_path):
        session = _make_session(working_directory=str(tmp_path))
        path = write_hygiene_md(session, project_dir=str(tmp_path))
        assert Path(path).exists()
        assert path.endswith("hygiene.md")

    def test_content_has_task(self, tmp_path):
        session = _make_session()
        write_hygiene_md(session, project_dir=str(tmp_path))
        content = (tmp_path / ".claude" / "hygiene.md").read_text()
        assert "Building auth flow" in content

    def test_content_has_decisions(self, tmp_path):
        session = _make_session()
        write_hygiene_md(session, project_dir=str(tmp_path))
        content = (tmp_path / ".claude" / "hygiene.md").read_text()
        assert "JWT tokens" in content
        assert "PostgreSQL" in content

    def test_content_has_files(self, tmp_path):
        session = _make_session()
        write_hygiene_md(session, project_dir=str(tmp_path))
        content = (tmp_path / ".claude" / "hygiene.md").read_text()
        assert "src/auth.py" in content
        assert "(staged)" in content
        assert "(modified)" in content

    def test_content_has_commits(self, tmp_path):
        session = _make_session()
        write_hygiene_md(session, project_dir=str(tmp_path))
        content = (tmp_path / ".claude" / "hygiene.md").read_text()
        assert "add login endpoint" in content

    def test_creates_claude_dir(self, tmp_path):
        session = _make_session()
        write_hygiene_md(session, project_dir=str(tmp_path))
        assert (tmp_path / ".claude").is_dir()


class TestRenderHookOutput:
    def test_includes_task(self):
        output = render_hook_output(_make_session())
        assert "Building auth flow" in output

    def test_includes_decisions(self):
        output = render_hook_output(_make_session())
        assert "JWT tokens" in output

    def test_includes_files(self):
        output = render_hook_output(_make_session())
        assert "src/auth.py" in output

    def test_includes_branch(self):
        output = render_hook_output(_make_session())
        assert "feature/auth" in output

    def test_includes_commits(self):
        output = render_hook_output(_make_session())
        assert "add login endpoint" in output

    def test_minimal_session(self):
        session = {"session_id": "min", "task": "Quick fix",
                    "git": {"modified_files": [], "staged_files": [],
                            "untracked_files": [], "recent_commits": []}}
        output = render_hook_output(session)
        assert "Quick fix" in output

    def test_ends_with_instruction(self):
        output = render_hook_output(_make_session())
        assert "Continue from where" in output
