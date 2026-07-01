"""Tests for Claude Code hooks integration."""

import json

from novyx_hygiene.hooks import install_hooks, uninstall_hooks


class TestInstallHooks:
    def test_creates_settings_file(self, tmp_path):
        result = install_hooks(project_dir=str(tmp_path), scope="project")
        settings_path = tmp_path / ".claude" / "settings.local.json"
        assert settings_path.exists()
        assert "PreCompact" in result["events_configured"]
        assert "SessionStart" in result["events_configured"]

    def test_settings_structure(self, tmp_path):
        install_hooks(project_dir=str(tmp_path))
        settings = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
        assert "hooks" in settings

        # PreCompact should have one hook
        assert len(settings["hooks"]["PreCompact"]) >= 1

        # SessionStart should have compact, clear, resume matchers
        matchers = {h.get("matcher") for h in settings["hooks"]["SessionStart"]}
        assert "compact" in matchers
        assert "clear" in matchers
        assert "resume" in matchers

    def test_preserves_existing_settings(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {"some_setting": True, "hooks": {}}
        (claude_dir / "settings.local.json").write_text(json.dumps(existing))

        install_hooks(project_dir=str(tmp_path))
        settings = json.loads((claude_dir / "settings.local.json").read_text())
        assert settings["some_setting"] is True
        assert "PreCompact" in settings["hooks"]

    def test_idempotent(self, tmp_path):
        install_hooks(project_dir=str(tmp_path))
        install_hooks(project_dir=str(tmp_path))
        settings = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())

        # Count hygiene hooks in PreCompact
        hygiene_hooks = [
            h for h in settings["hooks"]["PreCompact"]
            if any("hygiene" in inner.get("command", "") for inner in h.get("hooks", []))
        ]
        assert len(hygiene_hooks) == 1

    def test_doesnt_clobber_other_hooks(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {
            "hooks": {
                "PreCompact": [
                    {"hooks": [{"type": "command", "command": "echo other-tool"}]}
                ]
            }
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(existing))

        install_hooks(project_dir=str(tmp_path))
        settings = json.loads((claude_dir / "settings.local.json").read_text())
        commands = []
        for h in settings["hooks"]["PreCompact"]:
            for inner in h.get("hooks", []):
                commands.append(inner.get("command", ""))
        assert "echo other-tool" in commands
        assert any("hygiene" in c for c in commands)


class TestUninstallHooks:
    def test_removes_hygiene_hooks(self, tmp_path):
        install_hooks(project_dir=str(tmp_path))
        removed = uninstall_hooks(project_dir=str(tmp_path))
        assert removed is True

        settings = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
        # No hooks should remain (all were hygiene)
        for event_hooks in settings.get("hooks", {}).values():
            for h in event_hooks:
                for inner in h.get("hooks", []):
                    assert "hygiene" not in inner.get("command", "")

    def test_preserves_other_hooks(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = {
            "hooks": {
                "PreCompact": [
                    {"hooks": [{"type": "command", "command": "echo keep-me"}]},
                    {"hooks": [{"type": "command", "command": "hygiene save --auto"}]},
                ]
            }
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(existing))

        uninstall_hooks(project_dir=str(tmp_path))
        settings = json.loads((claude_dir / "settings.local.json").read_text())
        remaining = settings["hooks"]["PreCompact"]
        assert len(remaining) == 1
        assert remaining[0]["hooks"][0]["command"] == "echo keep-me"

    def test_no_settings_file(self, tmp_path):
        removed = uninstall_hooks(project_dir=str(tmp_path))
        assert removed is False
