import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import rtsp_capture
from plugins import cameras_locais as cameras


class LocalCameraTests(unittest.TestCase):
    def setUp(self):
        self.camera = dict(host="192.168.15.73", username="test", password="p@ss&word",
                           vendor="icsee", channel=1, stream=1)

    def test_credentials_are_encoded_for_vendor_urls(self):
        url = rtsp_capture.build_url(self.camera)
        self.assertIn("password=p%40ss%26word", url)
        self.camera["vendor"] = "intelbras"
        url = rtsp_capture.build_url(self.camera)
        self.assertIn("test:p%40ss%26word@192.168.15.73", url)
        self.assertIn("channel=1&subtype=1", url)

    def test_missing_credentials_never_attempt_connection(self):
        self.camera["password"] = ""
        with patch.object(rtsp_capture.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                rtsp_capture.snapshot(self.camera)
        run.assert_not_called()

    def test_only_private_non_loopback_addresses_allowed(self):
        for host in ("8.8.8.8", "127.0.0.1", "0.0.0.0", "224.0.0.1", "example.com"):
            self.camera["host"] = host
            with self.subTest(host=host), self.assertRaises(ValueError):
                rtsp_capture.build_url(self.camera)

    def test_worker_credentials_use_stdin_not_arguments_and_stderr_discarded(self):
        with patch.object(rtsp_capture.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=b"\xff\xd8image")) as run:
            self.assertEqual(rtsp_capture.snapshot(self.camera), b"\xff\xd8image")
        args, options = run.call_args
        self.assertNotIn("p@ss", str(args))
        self.assertIn(b"p%40ss%26word", options["input"])
        self.assertEqual(options["stderr"], subprocess.DEVNULL)
        self.assertEqual(options["timeout"], 12)

    def test_native_failures_never_echo_url_or_password(self):
        with patch.object(rtsp_capture.subprocess, "run", return_value=SimpleNamespace(
                returncode=2, stdout=b"")):
            with self.assertRaises(RuntimeError) as error:
                rtsp_capture.snapshot(self.camera)
        self.assertNotIn("p@ss", str(error.exception))
        self.assertNotIn("rtsp://", str(error.exception))

    def test_preview_does_not_call_ai(self):
        player = Mock()
        with patch.object(cameras, "_cameras", return_value=[dict(self.camera, name="Entrada")]), \
                patch.object(cameras, "snapshot", return_value=b"image"), \
                patch("core.gemini.call") as ai:
            result = cameras.run({"action": "preview", "camera": "Entrada"}, player=player)
        ai.assert_not_called()
        player.show_camera_frame.assert_called_once_with(b"image")
        self.assertIn("sent_to_ai=false", result)

    def test_unknown_or_ambiguous_name_never_selects_another_camera(self):
        configs = [dict(self.camera, name="Entrada"), dict(self.camera, name="Entrada")]
        for name in ("Ent", "Entrada", "Outra"):
            with self.assertRaises(ValueError):
                cameras._resolve(name, configs)

    def test_list_contains_no_credentials(self):
        with patch.object(cameras, "_cameras", return_value=[dict(self.camera, name="Entrada")]):
            result = cameras.run({"action": "list"})
        self.assertIn("Entrada", result)
        self.assertNotIn(self.camera["password"], result)
        self.assertNotIn("username", result)

    def test_defaults_match_discovered_addresses_without_guessing_credentials(self):
        configs = cameras._cameras({})
        self.assertEqual([c["host"] for c in configs], ["192.168.15.73", "192.168.15.149"])
        self.assertTrue(all(not c["username"] and not c["password"] for c in configs))

    def test_unique_vendor_aliases_and_duplicate_vendor_rejection(self):
        devices = cameras._cameras({})
        for alias in ("Intelbras", "DVR Intelbras", "camera da Intelbras"):
            self.assertIs(cameras._resolve(alias, devices), devices[1])
        self.assertIs(cameras._resolve("iCSee", devices), devices[0])
        with self.assertRaises(ValueError):
            cameras._resolve("Intelbras", [devices[1], dict(devices[1], name="Outro DVR")])

    def test_intelbras_channel_twelve_routes_to_live_device(self):
        player = Mock()
        with patch.object(cameras, "_cameras", return_value=cameras._cameras({})):
            cameras.run({"action": "live", "camera": "Intelbras", "channel": 12}, player)
            selected = player.start_security_camera.call_args.args[0]
            self.assertEqual(selected["vendor"], "intelbras")
            self.assertEqual(selected["channel"], 12)
            cameras.run({"action": "live", "camera": "Intelbras canal 12"}, player)
            self.assertEqual(player.start_security_camera.call_args.args[0]["channel"], 12)

    def test_offline_camera_does_not_fail_other_device_test(self):
        devices = [dict(self.camera, name="Offline"), dict(self.camera, name="DVR")]
        with patch.object(cameras, "_cameras", return_value=devices), \
                patch.object(cameras, "snapshot", side_effect=[RuntimeError(), b"image"]) as capture:
            success, message = cameras._test({})
        self.assertTrue(success)
        self.assertIn("1/2", message)
        self.assertIn("DVR:", message)
        self.assertEqual(capture.call_count, 2)

    def test_dvr_channel_selection_uses_same_credentials_without_mutating_default(self):
        device = dict(self.camera, vendor="intelbras", name="DVR", channel_count="16")
        with patch.object(cameras, "_cameras", return_value=[device]), \
                patch.object(cameras, "snapshot", return_value=b"image") as capture:
            result = cameras.run({"action": "test", "camera": "DVR", "channel": 8})
        selected = capture.call_args.args[0]
        self.assertIn("channel=8&subtype=1", rtsp_capture.build_url(selected))
        self.assertEqual(selected["password"], device["password"])
        self.assertEqual(device["channel"], 1)
        self.assertIn("channel=8", result)

    def test_invalid_or_out_of_range_channel_does_not_connect(self):
        device = dict(self.camera, name="DVR", channel_count="8")
        for channel in (0, 9, 65, -1, True, 1.5, "2&subtype=0"):
            with self.subTest(channel=channel), \
                    patch.object(cameras, "_cameras", return_value=[device]), \
                    patch.object(cameras, "snapshot") as capture:
                cameras.run({"action": "preview", "camera": "DVR", "channel": channel})
                capture.assert_not_called()

    def test_unknown_channel_count_allows_explicit_channel_without_inventing_count(self):
        device = dict(self.camera, channel_count="")
        self.assertEqual(cameras._select_channel(device, 16)["channel"], 16)
        self.assertEqual(cameras._select_channel(device)["channel"], 1)


if __name__ == "__main__":
    unittest.main()
