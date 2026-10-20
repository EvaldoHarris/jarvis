import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from core import camera_frames, person_identity as identity
from actions.person_identity import person_identity


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.profile_path = Path(self.folder.name) / "profiles.json"
        self.patcher = patch.object(identity, "PROFILES", self.profile_path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        with identity._audio_lock:
            identity._audio.clear()
            identity._last_speech = 0

    def test_silence_and_stale_voice_not_accepted(self):
        identity.feed_microphone(bytes(1024 * 2))
        with self.assertRaises(ValueError):
            identity.recent_voice()
        loud = np.full(1024, 1000, dtype=np.int16).tobytes()
        for _ in range(40):
            identity.feed_microphone(loud)
        self.assertEqual(identity.recent_voice().size, 40960)
        with patch.object(identity.time, "monotonic", return_value=identity._last_speech + 13):
            with self.assertRaises(ValueError):
                identity.recent_voice()

    def test_unknown_and_ambiguous_vectors_are_not_named(self):
        profiles = {"Evaldo": {"face": [1, 0]}, "Outra pessoa": {"face": [1, 0.01]}}
        self.assertIsNone(identity.best_match([0, 1], profiles, "face", .45))
        self.assertIsNone(identity.best_match([1, 0], profiles, "face", .45))

    def test_register_requires_name_and_does_not_overwrite(self):
        with self.assertRaises(ValueError):
            identity.manage_identity("register", "")
        identity._save_profiles({"Evaldo": {"face": [1, 0], "voice": [1, 0]}})
        with self.assertRaises(ValueError):
            identity.manage_identity("register", "Evaldo")

    def test_registration_and_forgetting_store_no_photo_or_audio(self):
        with patch.object(identity, "recent_voice", return_value=np.ones(32000)), \
                patch.object(identity, "face_embedding", return_value=np.array([1., 0.])), \
                patch.object(identity, "voice_embedding", return_value=np.array([0., 1.])):
            result = identity.manage_identity("register", "Evaldo")
        self.assertEqual(result["registered"], "Evaldo")
        self.assertEqual(set(self.profile_path.parent.iterdir()), {self.profile_path})
        self.assertEqual(set(identity.load_profiles()["Evaldo"]),
                         {"face", "voice", "face_model", "voice_model"})
        identity.manage_identity("forget", "Evaldo")
        self.assertEqual(identity.load_profiles(), {})

    def test_both_modalities_must_agree(self):
        identity._save_profiles({"Evaldo": {"face": [1, 0], "voice": [1, 0]},
                                 "Outro": {"face": [0, 1], "voice": [0, 1]}})
        with patch.object(identity, "recent_voice", return_value=np.ones(32000)), \
                patch.object(identity, "face_embedding", return_value=np.array([1., 0.])), \
                patch.object(identity, "voice_embedding", return_value=np.array([0., 1.])):
            result = identity.manage_identity("identify")
        self.assertEqual(result["status"], "unverified")
        self.assertIsNone(result["name"])

    def test_matching_face_and_voice_confirm_name(self):
        identity._save_profiles({"Evaldo": {"face": [1, 0], "voice": [1, 0]}})
        with patch.object(identity, "recent_voice", return_value=np.ones(32000)), \
                patch.object(identity, "face_embedding", return_value=np.array([1., 0.])), \
                patch.object(identity, "voice_embedding", return_value=np.array([1., 0.])):
            self.assertEqual(identity.manage_identity("identify")["name"], "Evaldo")

    def test_no_profiles_returns_actionable_tool_failure(self):
        result = json.loads(person_identity({"action": "identify"}))
        self.assertEqual(result["status"], "failed")
        self.assertIn("cadastrada", result["reason"])

    def test_preview_frames_expire_and_can_be_cleared(self):
        camera_frames.publish(b"image")
        self.assertEqual(camera_frames.latest(), b"image")
        with patch.object(camera_frames.time, "monotonic", return_value=camera_frames._at + 2):
            self.assertIsNone(camera_frames.latest())
        camera_frames.clear()
        self.assertIsNone(camera_frames.latest())


if __name__ == "__main__":
    unittest.main()
