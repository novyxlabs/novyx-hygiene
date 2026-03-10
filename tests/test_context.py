"""Tests for context analysis and scoring."""

from datetime import datetime, timedelta

from novyx_hygiene.context import score_session


class TestScoreSession:
    def _make_session(self, **overrides):
        session = {
            "task": "Test task",
            "timestamp": datetime.now().isoformat(),
            "git": {
                "modified_files": ["a.py"],
                "staged_files": [],
                "untracked_files": [],
            },
            "decisions": ["Good decision"],
            "status": "Halfway done",
        }
        session.update(overrides)
        return session

    def test_healthy_session(self):
        result = score_session(self._make_session())
        assert result["score"] >= 80
        assert result["grade"] in ("A", "B")

    def test_stale_session(self):
        old = (datetime.now() - timedelta(hours=30)).isoformat()
        result = score_session(self._make_session(timestamp=old))
        assert result["score"] <= 80
        assert any("stale" in i.lower() or "old" in i.lower() for i in result["issues"])

    def test_file_sprawl(self):
        git = {
            "modified_files": [f"dir{i}/file{i}.py" for i in range(20)],
            "staged_files": [],
            "untracked_files": [],
        }
        result = score_session(self._make_session(git=git))
        assert result["score"] < 85
        assert any("sprawl" in i.lower() or "files" in i.lower() for i in result["issues"])

    def test_no_decisions_penalty(self):
        result = score_session(self._make_session(decisions=[]))
        clean = score_session(self._make_session(decisions=["A decision"]))
        assert result["score"] < clean["score"]

    def test_mixed_concerns(self):
        git = {
            "modified_files": [
                "src/auth/login.py",
                "tests/test_auth.py",
                "docs/readme.md",
                "config/settings.yaml",
                "scripts/deploy.sh",
            ],
            "staged_files": [],
            "untracked_files": [],
        }
        result = score_session(self._make_session(git=git))
        assert any("directories" in i or "concerns" in i for i in result["issues"])

    def test_grade_mapping(self):
        # Perfect session
        perfect = score_session(self._make_session(
            decisions=["decision"],
            status="Auth flow 70% done",
        ))
        assert perfect["grade"] in ("A", "B")

        # Terrible session
        terrible = score_session(self._make_session(
            timestamp=(datetime.now() - timedelta(hours=48)).isoformat(),
            decisions=[],
            status="In progress",
            git={
                "modified_files": [f"d{i}/f{i}.py" for i in range(20)],
                "staged_files": [],
                "untracked_files": [],
            },
        ))
        assert terrible["score"] < perfect["score"]
