import queue
import threading
import time
import unittest
from unittest.mock import patch

from core.live_translation import LiveTranslation, AudioSegmenter
from core.local_translation import audio_samples, language_code, LocalTranslator
from actions.live_translation import live_translation


class TranslationTests(unittest.TestCase):
    def test_stop_discards_inflight_reply(self):
        service = LiveTranslation()
        chunks = queue.Queue()
        chunks.put((time.monotonic(), b"audio", 16000, 1))
        entered, release = threading.Event(), threading.Event()
        output = []

        def slow(*args):
            entered.set()
            release.wait(2)
            return "late subtitle"

        with patch("core.live_translation.translate_audio", slow):
            worker = threading.Thread(target=service._translate,
                                      args=(service._stop, chunks, output.append, "pt"))
            worker.start()
            self.assertTrue(entered.wait(1))
            service.stop()
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(output, [])

    def test_backend_failure_stops_capture_and_reports_error(self):
        service = LiveTranslation()
        chunks = queue.Queue()
        chunks.put((time.monotonic(), b"audio", 16000, 1))
        output = []
        with patch("core.live_translation.translate_audio", side_effect=RuntimeError("quota")):
            service._translate(service._stop, chunks, output.append, "pt")
        self.assertTrue(service._stop.is_set())
        self.assertEqual(service.state, "error")
        self.assertIn("quota", output[0])

    def test_stale_audio_is_not_translated(self):
        service = LiveTranslation()
        chunks = queue.Queue()
        chunks.put((time.monotonic() - 30, b"old", 16000, 1))
        with patch("core.live_translation.translate_audio") as translate:
            worker = threading.Thread(target=service._translate,
                                      args=(service._stop, chunks, lambda text: None, "pt"))
            worker.start()
            time.sleep(0.05)
            service.stop()
            worker.join(1)
            translate.assert_not_called()

    def test_start_without_display(self):
        self.assertIn("não está disponível", live_translation({"action": "start"}))

    def test_audio_toggle_does_not_stop_captions(self):
        service = LiveTranslation()
        service.state = "running"
        service.set_audio(True)
        self.assertTrue(service.speech.enabled.is_set())
        service.set_audio(False)
        self.assertFalse(service.speech.enabled.is_set())
        self.assertFalse(service._stop.is_set())

    def test_stop_disables_narration_and_clears_pending_text(self):
        service = LiveTranslation()
        service.speech.set_enabled(True)
        service.speech.offer("old translation")
        service.stop()
        self.assertFalse(service.speech.enabled.is_set())
        self.assertTrue(service.speech.pending.empty())

    def test_resampling_stereo_48k_to_mono_16k(self):
        import numpy as np
        pcm = np.full((48000, 2), 16384, dtype=np.int16).tobytes()
        samples = audio_samples(pcm, 48000, 2)
        self.assertEqual(samples.shape, (16000,))
        self.assertAlmostEqual(float(samples[100:-100].mean()), 0.5, places=3)

    def test_segmentation_ignores_silence_and_ends_on_pause(self):
        import numpy as np
        segmenter = AudioSegmenter(16000, 1)
        silent = np.zeros(1600, dtype=np.int16).tobytes()
        speech = np.full(1600, 1000, dtype=np.int16).tobytes()
        for _ in range(30):
            self.assertIsNone(segmenter.feed(silent))
        for _ in range(5):
            self.assertIsNone(segmenter.feed(speech))
        self.assertIsNone(segmenter.feed(silent))
        self.assertIsNone(segmenter.feed(silent))
        self.assertIsNotNone(segmenter.feed(silent))
        self.assertEqual(segmenter.frames, [])

    def test_segmentation_bounds_continuous_audio(self):
        import numpy as np
        segmenter = AudioSegmenter(16000, 1)
        speech = np.full(1600, 1000, dtype=np.int16).tobytes()
        blocks = [segmenter.feed(speech) for _ in range(21)]
        self.assertEqual(sum(block is not None for block in blocks), 1)

    def test_language_aliases_and_invalid_names(self):
        self.assertEqual(language_code("Português brasileiro"), "pt")
        self.assertEqual(language_code("inglês"), "en")
        with self.assertRaises(ValueError):
            language_code("unsupported language name")

    def test_same_language_needs_no_translation_model(self):
        self.assertEqual(LocalTranslator().text_translation("Olá", "pt", "pt"), "Olá")

    def test_missing_pair_explains_setup_without_network(self):
        with patch("argostranslate.package.get_installed_packages", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "setup_translation.py --source en --target pt"):
                LocalTranslator().text_translation("Hello", "en", "pt")


if __name__ == "__main__":
    unittest.main()
