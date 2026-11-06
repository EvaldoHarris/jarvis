from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
from actions import cloud_cli as cloud
from core.action_loader import _validate


class CloudCliTests(unittest.TestCase):
    def test_list_projects_without_folder_shows_complete_compact_list(self):
        data = [{"id": str(i), "name": f"Projeto {i}", "irrelevant": "x" * 5000,
                 "services": {"edges": [{"node": {"name": "backend"}}]}} for i in range(8)]
        player = Mock()
        with patch.object(cloud, "executable", return_value="railway.exe"), \
                patch.object(cloud.subprocess, "run", return_value=Mock(
                    returncode=0, stdout=json.dumps(data), stderr="")) as run:
            result = cloud.cloud_cli({"provider": "railway", "action": "projects",
                                      "project_path": "a-folder-that-does-not-exist"}, player=player)
        self.assertIn("project_count=8", result)
        self.assertIn("Projeto 0", result)
        self.assertIn("Projeto 7", result)
        self.assertNotIn("truncated", result)
        self.assertEqual(run.call_args.args[0], ["railway.exe", "list", "--json"])
        self.assertEqual(run.call_args.kwargs["cwd"], Path.home())
        player.show_content.assert_called_once()

    def test_discoverable(self):
        self.assertTrue(_validate(cloud, "cloud_cli.py").valid)

    def test_deploy_cannot_execute_before_hud_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(cloud, "executable", return_value="railway.exe"), \
                patch.object(cloud.confirm, "pending_title", return_value=""), \
                patch.object(cloud.confirm, "request", return_value="PENDING") as gate, \
                patch.object(cloud, "_run") as run:
            response = cloud.cloud_cli({"provider": "railway", "action": "deploy", "project_path": tmp, "service": "backend"})
            self.assertEqual(response, "PENDING")
            gate.assert_called_once()
            run.assert_not_called()

    def test_netlify_draft_production_and_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "dist").mkdir()
            p = {"project_path": tmp, "project": "site-id", "directory": "dist"}
            args = cloud.build_args("netlify", "deploy", p)
            self.assertNotIn("--prod", args)
            self.assertIn("--no-build", args)
            self.assertIn("--prod", cloud.build_args("netlify", "deploy", {**p, "production": True}))
            with self.assertRaises(ValueError):
                cloud.build_args("netlify", "deploy", {**p, "directory": ".."})

    def test_shell_metacharacters_and_option_injection_rejected(self):
        for value in ("--help", "backend & whoami", "$(whoami)", "x%PATH%"):
            with self.assertRaises(ValueError):
                cloud.build_args("railway", "deploy", {"service": value})

    def test_logs_bounded_and_missing_cli_actionable(self):
        self.assertEqual(cloud.build_args("railway", "logs", {}), ["logs", "--lines", "100"])
        with patch.object(cloud, "executable", return_value=None):
            self.assertIn("npm install -g netlify-cli", cloud.cloud_cli({"provider": "netlify"}))


if __name__ == "__main__":
    unittest.main()
