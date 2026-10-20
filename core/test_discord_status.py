import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from plugins import discord_status as discord


class DiscordStatusTests(unittest.TestCase):
    def test_only_fixed_local_scripts_are_executed(self):
        for action in ("almoco", "voltei"):
            with self.subTest(action=action), patch.object(discord.platform, "system", return_value="Windows"), \
                    patch.object(discord.Path, "is_file", return_value=True), \
                    patch.object(discord.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                result = discord.run({"action": action})
            self.assertEqual(run.call_args.args[0][-1], str(discord.SCRIPTS[action]))
            self.assertIn("status=unverified", result)
            self.assertIn("windows_return_timer=false", result)
            self.assertEqual(run.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)

    def test_unknown_commands_are_rejected(self):
        with patch.object(discord.subprocess, "run") as run:
            self.assertIn("status=failed", discord.run({"action": "almoco; shutdown"}))
        run.assert_not_called()

    def test_script_failure_is_reported(self):
        with patch.object(discord.Path, "is_file", return_value=True), \
                patch.object(discord.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            self.assertIn("status=failed", discord.run({"action": "almoco"}))

    def test_concurrent_request_is_rejected(self):
        discord._lock.acquire()
        try:
            with patch.object(discord.Path, "is_file", return_value=True), \
                    patch.object(discord.subprocess, "run") as run:
                self.assertIn("status=failed", discord.run({"action": "voltei"}))
            run.assert_not_called()
        finally:
            discord._lock.release()


if __name__ == "__main__":
    unittest.main()
