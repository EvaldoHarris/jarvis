import ast
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch

import numpy as np

from core import person_identity as identity
from core.voice_activation import VoiceActivationGate, RecentConversation, is_addressed_to_jarvis


class VoiceActivationTests(unittest.TestCase):
    def setUp(self):
        self.gate = VoiceActivationGate(Mock())
        self.gate._model = Mock()
        self.pcm = np.full(16000, 1000, dtype=np.int16).tobytes()

    def transcript(self, text):
        self.gate._model.transcribe.return_value = ([SimpleNamespace(text=text)], None)

    def test_keyword_and_owner_are_both_required(self):
        for text, owner, expected in [("Jarvis", "Evaldo", "Evaldo"),
                                      ("JARVIS abra a agenda", "Evaldo", "Evaldo"),
                                      ("abra a agenda", "Evaldo", None),
                                      ("jarvisiano", "Evaldo", None),
                                      ("Jarvis", None, None)]:
            with self.subTest(text=text, owner=owner):
                self.transcript(text)
                with patch.object(identity, "verify_voice_owner", return_value=owner):
                    self.assertEqual(self.gate.authorize(self.pcm), expected)

    def test_voice_only_profiles_do_not_break_camera_matching(self):
        self.assertEqual(identity.best_match([1, 0], {"Voice": {"voice": [1, 0]},
                         "Face": {"face": [1, 0]}}, "face", .45), "Face")

    def test_nearby_conversation_is_silent_until_authorized_question(self):
        self.gate._running = True
        self.transcript("Estamos decidindo entre viajar de carro ou de ônibus.")
        self.gate._process_utterance(self.pcm, self.gate._generation)
        self.gate._on_detect.assert_not_called()
        self.transcript("Eu prefiro o ônibus porque custa menos.")
        self.gate._process_utterance(self.pcm, self.gate._generation)
        self.gate._on_detect.assert_not_called()
        self.transcript("Jarvis, o que acha disso?")
        with patch.object(identity, "verify_voice_owner", return_value="Evaldo"):
            self.gate._process_utterance(self.pcm, self.gate._generation)
        self.gate._on_detect.assert_called_once()
        request = self.gate._on_detect.call_args.args[2]
        self.assertIn("ônibus", request)
        self.assertIn("Jarvis, o que acha disso?", request)
        self.assertIn("untrusted transcript", request)

    def test_unauthorized_question_never_sends_context(self):
        self.gate._running = True
        self.gate._conversation.add("Contexto de uma conversa próxima")
        self.transcript("Jarvis, me responda")
        with patch.object(identity, "verify_voice_owner", return_value=None):
            self.gate._process_utterance(self.pcm, self.gate._generation)
        self.gate._on_detect.assert_not_called()

    def test_context_expires_and_is_bounded(self):
        now = [0]
        context = RecentConversation(clock=lambda: now[0])
        context.add("antigo")
        now[0] = 121
        self.assertEqual(context.snapshot(), "")
        for _ in range(100):
            context.add("x" * 3000)
        self.assertLessEqual(len(context.lines), 60)
        self.assertLessEqual(len(context.snapshot()), 12000)

    def test_mute_reset_clears_context_but_playback_reset_preserves_it(self):
        self.gate._conversation.add("conversa")
        self.gate.reset()
        self.assertEqual(self.gate._conversation.snapshot(), "conversa")
        self.gate.reset(clear_context=True)
        self.assertEqual(self.gate._conversation.snapshot(), "")

    def test_oversized_speech_can_only_be_passive_context(self):
        self.gate._running = True
        self.transcript("Jarvis, isto faz parte de uma fala longa")
        with patch.object(identity, "verify_voice_owner", return_value="Evaldo"):
            self.gate._process_utterance(self.pcm, self.gate._generation, allow_reply=False)
        self.gate._on_detect.assert_not_called()
        self.assertIn("fala longa", self.gate._conversation.snapshot())

    def test_direct_calls_and_transcription_variants(self):
        for text in ("Jarvis!", "Oi, Jarvis, abra a agenda", "Olá, Járvis!",
                     "Ei Jarves, me ajude", "Hey Jarviz", "Por favor, Jarvis, veja isso"):
            with self.subTest(text=text):
                self.assertTrue(is_addressed_to_jarvis(text))
        for text in ("Eu estava falando do Jarvis", "O Jarvis respondeu ontem",
                     "Você conhece Jarvis?", "Ontem falei: Jarvis, abra a agenda",
                     "jarvisiano", "já vi isso", "Jardins", "", "abra a agenda"):
            with self.subTest(text=text):
                self.assertFalse(is_addressed_to_jarvis(text))

    def test_mention_does_not_even_request_voice_authorization(self):
        self.transcript("Eu contei ao Jarvis o que aconteceu")
        with patch.object(identity, "verify_voice_owner") as verify:
            self.assertIsNone(self.gate.authorize(self.pcm))
            verify.assert_not_called()

    def test_uncertain_transcription_cannot_activate(self):
        for quality in ({"no_speech_prob": .9, "avg_logprob": -1.1}, {"avg_logprob": -1.6}):
            self.gate._model.transcribe.return_value = ([SimpleNamespace(text="Jarvis", **quality)], None)
            with patch.object(identity, "verify_voice_owner") as verify:
                self.assertIsNone(self.gate.authorize(self.pcm))
                verify.assert_not_called()

    def test_confident_keyword_is_not_rejected_by_no_speech_score_alone(self):
        self.gate._model.transcribe.return_value = ([SimpleNamespace(
            text="Jarvis, que horas são?", no_speech_prob=.8, avg_logprob=-.2)], None)
        with patch.object(identity, "verify_voice_owner", return_value="Evaldo"):
            self.assertEqual(self.gate.authorize(self.pcm), "Evaldo")

    def test_voice_rejection_is_reported_without_reply_or_transcript(self):
        self.transcript("Jarvis, que horas são?")
        self.gate._notify = Mock()
        with patch.object(identity, "verify_voice_owner", return_value=None):
            self.assertIsNone(self.gate.authorize(self.pcm))
            self.assertIsNone(self.gate.authorize(self.pcm))
        self.gate._notify.assert_called_once()
        self.gate._on_detect.assert_not_called()

    def test_neural_vad_ends_utterance_despite_background_above_old_threshold(self):
        gate = VoiceActivationGate(Mock(), logger=Mock())
        gate._running = True
        gate._vad = Mock(side_effect=[np.array([.9]), np.array([.01])])
        speech = np.full(8000, 1000, dtype=np.int16)
        background = np.full(10000, 700, dtype=np.int16)
        gate.feed(speech)
        gate.feed(background)
        gate._queue.put(None)
        with patch.object(gate, "authorize", return_value="Evaldo"):
            gate._loop()
        gate._on_detect.assert_called_once()

    def test_preroll_preserves_quiet_first_syllable(self):
        gate = VoiceActivationGate(Mock(), logger=Mock())
        gate._running = True
        quiet = np.full(1600, 100, dtype=np.int16)
        loud = np.full(8000, 1000, dtype=np.int16)
        silence = np.zeros(10000, dtype=np.int16)
        for frame in (quiet, loud, silence):
            gate.feed(frame)
        gate._queue.put(None)
        with patch.object(gate, "authorize", return_value="Evaldo"):
            gate._loop()
        gate._on_detect.assert_called_once_with(quiet.tobytes() + loud.tobytes() + silence.tobytes(), "Evaldo")

    def test_only_selected_owner_is_accepted(self):
        profiles = {"Evaldo": {"voice": [1, 0]}, "Other": {"voice": [0, 1]}}
        with patch("memory.config_manager.load_api_keys", return_value={"voice_owner": "Evaldo"}), \
                patch.object(identity, "load_profiles", return_value=profiles), \
                patch.object(identity, "voice_embedding", return_value=[0, 1]):
            self.assertIsNone(identity.verify_voice_owner(np.ones(16000)))
        with patch("memory.config_manager.load_api_keys", return_value={"voice_owner": "Evaldo"}), \
                patch.object(identity, "load_profiles", return_value=profiles), \
                patch.object(identity, "voice_embedding", return_value=[1, 0]):
            self.assertEqual(identity.verify_voice_owner(np.ones(16000)), "Evaldo")

    def test_no_owner_or_no_enrollment_fails_closed(self):
        for config in ({}, {"voice_owner": "Missing"}):
            with patch("memory.config_manager.load_api_keys", return_value=config), \
                    patch.object(identity, "load_profiles", return_value={}), \
                    patch.object(identity, "voice_embedding") as embedding:
                self.assertIsNone(identity.verify_voice_owner(np.ones(16000)))
                embedding.assert_not_called()

    def test_explicit_voice_enrollment_preserves_face_and_selects_owner(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(identity, "PROFILES", Path(folder) / "profiles.json"), \
                patch.object(identity, "recent_voice", return_value=np.ones(48000)), \
                patch.object(identity, "voice_embedding", return_value=np.array([1., 0.])), \
                patch("memory.config_manager.save_voice_owner") as save_owner:
            identity._save_profiles({"Evaldo": {"face": [0, 1]}})
            identity.manage_identity("register_voice", "Evaldo")
            self.assertEqual(identity.load_profiles()["Evaldo"]["face"], [0, 1])
            save_owner.assert_called_once_with("Evaldo")
            with self.assertRaises(ValueError):
                identity.manage_identity("register_voice", "Evaldo")

    def test_worker_rejects_unknown_then_accepts_owner(self):
        gate = VoiceActivationGate(Mock(), logger=Mock())
        gate._running = True
        speech = np.full(8000, 1000, dtype=np.int16)
        silence = np.zeros(10000, dtype=np.int16)
        for _ in range(2):
            gate.feed(speech)
            gate.feed(silence)
        gate._queue.put(None)
        with patch.object(gate, "authorize", side_effect=[None, "Evaldo"]):
            gate._loop()
        gate._on_detect.assert_called_once_with(speech.tobytes() + silence.tobytes(), "Evaldo")

    def test_reset_invalidates_queued_audio(self):
        self.gate._running = True
        self.gate.feed(np.full(16000, 1000, dtype=np.int16))
        self.gate.reset()
        self.gate.feed(np.zeros(16000, dtype=np.int16))
        self.gate._queue.put(None)
        with patch.object(self.gate, "authorize") as authorize:
            self.gate._loop()
        authorize.assert_not_called()

    def test_verified_phrase_reaches_audio_queue_without_truncation(self):
        # Exercise the real main.py method without importing its desktop UI.
        tree = ast.parse((Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "JarvisLive")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_send_verified_utterance")
        from core.audio_playback import offer_latest_audio
        namespace = {"SEND_SAMPLE_RATE": 16000, "offer_latest_audio": offer_latest_audio,
                     "voice_health": Mock()}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "main.py", "exec"), namespace)
        app = SimpleNamespace(session=True, ui=SimpleNamespace(muted=False), _phone_active=False,
                              _ptt_enabled=False, _wake_enabled=True, _is_speaking=False,
                              _tail_active=lambda: False, wake=Mock(), out_queue=asyncio.Queue(maxsize=200))
        pcm = self.pcm * 15
        namespace[method.name](app, pcm, "Evaldo")
        chunks = []
        while not app.out_queue.empty():
            chunks.append(app.out_queue.get_nowait()["data"])
        self.assertEqual(b"".join(chunks), pcm)
        app.ui.muted = True
        namespace[method.name](app, pcm, "Evaldo")
        self.assertTrue(app.out_queue.empty())

    def test_startup_keeps_proactive_speech_enabled_with_microphone_gate(self):
        tree = ast.parse((Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "JarvisLive")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_start_listening_session")
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "main.py", "exec"), namespace)
        for enabled, models_ready in [(True, True), (True, False), (False, False)]:
            with self.subTest(enabled=enabled, models_ready=models_ready):
                app = SimpleNamespace(_wake_enabled=enabled, _awake=False, ui=Mock(),
                                      _ensure_wake_detector=Mock(return_value=models_ready))
                namespace[method.name](app)
                self.assertTrue(app._awake)
                self.assertEqual(app._wake_enabled, enabled)
                app.ui.set_state.assert_called_once_with("LISTENING")
                self.assertEqual(app._ensure_wake_detector.call_count, int(enabled))

    def test_authorized_context_and_question_create_exactly_one_turn(self):
        tree = ast.parse((Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "JarvisLive")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_send_verified_utterance")
        import json
        namespace = {"voice_health": Mock(), "asyncio": asyncio, "json": json}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "main.py", "exec"), namespace)

        async def check():
            session = SimpleNamespace(send_client_content=AsyncMock())
            app = SimpleNamespace(session=session, ui=Mock(muted=False), _phone_active=False,
                                  _ptt_enabled=False, _wake_enabled=True, _is_speaking=False,
                                  _tail_active=lambda: False, wake=Mock(), _arm_stall=Mock(),
                                  out_queue=asyncio.Queue())
            request = "overheard_conversation: viagem; direct_request: Jarvis, o que acha disso?"
            namespace[method.name](app, self.pcm, "Evaldo", request)
            await asyncio.sleep(0)
            session.send_client_content.assert_awaited_once_with(
                turns={"role": "user", "parts": [{"text": request}]}, turn_complete=True)
            self.assertTrue(app.out_queue.empty())  # No second audio-triggered response.
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
