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

    def test_short_and_full_name_near_identical_references_do_not_compete(self):
        profiles = {'Evaldo': {'face': [1, 0]}, 'Evaldo Full Name': {'face': [.99, .01]},
                    'Someone Else': {'face': [0, 1]}}
        result = identity.best_match([1, .01], profiles, 'face', .45)
        self.assertIn(result, ('Evaldo', 'Evaldo Full Name'))
        self.assertFalse(identity.same_face_profile('Evaldo', 'Someone Else', profiles))
        # A shared first name alone is insufficient to group different faces.
        profiles['Evaldo Full Name']['face'] = [0, 1]
        self.assertFalse(identity.same_face_profile('Evaldo', 'Evaldo Full Name', profiles))

    def test_register_requires_name_and_does_not_overwrite(self):
        with self.assertRaises(ValueError):
            identity.manage_identity("register", "")
        identity._save_profiles({"Evaldo": {"face": [1, 0], "voice": [1, 0]}})
        with self.assertRaises(ValueError):
            identity.manage_identity("register", "Evaldo")

    def test_registration_and_forgetting_store_no_photo_or_audio(self):
        with patch.object(identity, "recent_voice", side_effect=AssertionError("Voice must not be required")), \
                patch.object(identity, "face_embedding", return_value=np.array([1., 0.])), \
                patch.object(identity, "voice_embedding", return_value=np.array([0., 1.])):
            result = identity.manage_identity("register", "Evaldo")
        self.assertEqual(result["registered"], "Evaldo")
        self.assertEqual(set(self.profile_path.parent.iterdir()), {self.profile_path})
        self.assertEqual(set(identity.load_profiles()["Evaldo"]),
                         {"face", "face_model"})
        identity.manage_identity("forget", "Evaldo")
        self.assertEqual(identity.load_profiles(), {})

    def test_camera_match_does_not_require_matching_voice(self):
        identity._save_profiles({"Evaldo": {"face": [1, 0], "voice": [1, 0]},
                                 "Outro": {"face": [0, 1], "voice": [0, 1]}})
        with patch.object(identity, "recent_voice", side_effect=AssertionError("Voice must not be required")), \
                patch.object(identity, "face_embedding", return_value=np.array([1., 0.])), \
                patch.object(identity, "voice_embedding", return_value=np.array([0., 1.])):
            result = identity.manage_identity("identify")
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["name"], "Evaldo")

    def test_camera_identifies_without_recent_audio(self):
        identity._save_profiles({"Evaldo": {"face": [1, 0], "voice": [1, 0]}})
        with patch.object(identity, "recent_voice", side_effect=AssertionError("Voice must not be required")), \
                patch.object(identity, "face_embedding", return_value=np.array([1., 0.])), \
                patch.object(identity, "voice_embedding", return_value=np.array([1., 0.])):
            self.assertEqual(identity.manage_identity("identify")["name"], "Evaldo")

    def test_unknown_face_is_not_confirmed(self):
        identity._save_profiles({"Evaldo": {"face": [1, 0]}})
        with patch.object(identity, "face_embedding", return_value=np.array([0., 1.])):
            result = identity.manage_identity("identify")
        self.assertEqual(result["status"], "unverified")
        self.assertIsNone(result["name"])

    def test_face_models_do_not_require_speaker_model(self):
        with tempfile.TemporaryDirectory() as folder:
            models = Path(folder)
            (models / "yunet.onnx").touch()
            (models / "sface.onnx").touch()
            with patch.object(identity, "MODELS", models):
                identity._require_models()

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
