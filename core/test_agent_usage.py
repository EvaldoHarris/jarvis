import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core import agent_usage as usage
from scripts.claude_usage_statusline import capture, install


class AgentUsageTests(unittest.TestCase):
    def test_account_usage_works_without_statusline_and_never_caches_credentials(self):
        import httpx
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(usage, "claude_root", return_value=Path(tmp)), \
                patch.object(usage, "_claude_retry_at", 0):
            (Path(tmp) / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
                "accessToken": "PRIVATE-ACCESS", "refreshToken": "PRIVATE-REFRESH"}}))
            response = Mock(status_code=200)
            response.json.return_value = {"five_hour": {"utilization": 17, "resets_at": "2030-01-01T12:00:00Z"},
                                          "seven_day": {"utilization": 42, "resets_at": "2030-01-07T12:00:00Z"},
                                          "extra_secret": "PRIVATE-DATA"}
            with patch.object(httpx, "get", return_value=response) as get:
                result = usage.refresh_claude_usage()
                self.assertEqual([w["remaining"] for w in result["windows"]], [83, 58])
                self.assertEqual(usage.refresh_claude_usage()["windows"], result["windows"])
                get.assert_called_once()
                self.assertFalse(get.call_args.kwargs["follow_redirects"])
            cache = (Path(tmp) / "jarvis-usage.json").read_text()
            self.assertNotIn("PRIVATE", cache)
            self.assertNotIn("PRIVATE", json.dumps(result))
            # An extension's statusLine callback without quota fields must not
            # erase valid account data received by the independent reader.
            capture('{"model": {"display_name": "Claude"}}', Path(tmp) / "jarvis-usage.json")
            self.assertEqual(usage.claude_usage()["windows"], result["windows"])

    def test_rate_limit_backs_off_without_retrying_on_every_dashboard_tick(self):
        import httpx
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(usage, "claude_root", return_value=Path(tmp)), \
                patch.object(usage, "_claude_retry_at", 0):
            (Path(tmp) / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": "PRIVATE"}}))
            response = Mock(status_code=429, headers={"retry-after": "0"})
            with patch.object(httpx, "get", return_value=response) as get:
                result = usage.refresh_claude_usage()
                usage.refresh_claude_usage()
                get.assert_called_once()
            self.assertGreater(usage._claude_retry_at, usage.time.time() + 590)
            self.assertFalse(result["windows"])
            self.assertIn("limitou", result["error"])

    def test_expired_login_never_refreshes_or_changes_credentials(self):
        import httpx
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(usage, "claude_root", return_value=Path(tmp)), \
                patch.object(usage, "_claude_retry_at", 0), \
                patch.object(httpx, "get") as get:
            path = Path(tmp) / ".credentials.json"
            original = json.dumps({"claudeAiOauth": {"accessToken": "PRIVATE", "expiresAt": 1}})
            path.write_text(original)
            self.assertIn("expirado", usage.refresh_claude_usage()["error"])
            get.assert_not_called()
            self.assertEqual(path.read_text(), original)

    def test_missing_invalid_and_zero_usage(self):
        self.assertIsNone(usage.window({}, "used", "reset", "5h"))
        self.assertIsNone(usage.window({"used": float('nan')}, "used", "reset", "5h"))
        self.assertEqual(usage.window({"used": 0}, "used", "reset", "5h")["remaining"], 100)
        self.assertEqual(usage.window({"used": 100}, "used", "reset", "5h")["remaining"], 0)

    def test_expired_window_not_assumed_refilled(self):
        text, _ = usage.display({"windows": [{"label": "5h", "remaining": 27, "resets_at": 100}]}, now=101)
        self.assertEqual(text, "5h --")

    def test_capture_saves_only_limits_and_formats_remaining(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "jarvis-usage.json"
            capture(json.dumps({"secret": "PRIVATE", "rate_limits": {
                "five_hour": {"used_percentage": 75, "resets_at": 9999999999, "private": "PRIVATE"}}}), cache)
            self.assertNotIn("PRIVATE", cache.read_text())
            with patch.object(usage, "claude_root", return_value=Path(tmp)):
                snapshot = usage.claude_usage()
            self.assertEqual(snapshot["windows"][0]["remaining"], 25)
            self.assertIn("5h 25%", usage.display(snapshot)[0])

    def test_installer_preserves_settings_and_previous_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = {"permissions": {"allow": ["Read"]}, "statusLine": {"type": "command", "command": "echo custom", "padding": 2}}
            (root / "settings.json").write_text(json.dumps(original), encoding="utf-8")
            install(root)
            saved = json.loads((root / "settings.json").read_text())
            self.assertEqual(saved["permissions"], original["permissions"])
            self.assertEqual(saved["statusLine"]["padding"], 2)
            self.assertIn("--previous", saved["statusLine"]["command"])
            backups = list(root.glob("settings.jarvis-backup-*.json"))
            self.assertEqual(json.loads(backups[0].read_text()), original)
            install(root)
            self.assertEqual(len(list(root.glob("settings.jarvis-backup-*.json"))), 1)

    def test_codex_rpc_handshake_and_cleanup(self):
        import io
        from unittest.mock import Mock
        proc = Mock()
        proc.stdout = io.StringIO('\n'.join(json.dumps(x) for x in [
            {"id": 1, "result": {}}, {"method": "notification"},
            {"id": 2, "result": {"rateLimits": {"primary": {
                "usedPercent": 30, "windowDurationMins": 300, "resetsAt": 9999999999}}}}]))
        proc.stdin = Mock()
        proc.poll.return_value = None
        with patch.object(usage, "executable", return_value="codex.exe"), patch.object(usage.subprocess, "Popen", return_value=proc):
            result = usage.codex_usage()
        self.assertEqual(result["windows"][0]["remaining"], 70)
        sent = [json.loads(c.args[0]) for c in proc.stdin.write.call_args_list]
        self.assertEqual([m["method"] for m in sent], ["initialize", "initialized", "account/rateLimits/read"])
        proc.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
