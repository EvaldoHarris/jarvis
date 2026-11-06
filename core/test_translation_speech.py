import queue
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from core.translation_speech import TranslationSpeech, assistant_speaking, select_voice


class TranslationSpeechTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"JARVIS_TRANSLATION_TTS": "system"})
        self.env.start()

    def tearDown(self):
        assistant_speaking(False)
        self.env.stop()

    def test_latest_caption_replaces_backlog(self):
        speech = TranslationSpeech()
        speech.set_enabled(True)
        speech.offer("old")
        speech.offer("new")
        self.assertEqual(speech.pending.qsize(), 1)
        self.assertEqual(speech.pending.get_nowait()[2], "new")

    def test_offer_tolerates_consumer_draining_between_full_and_replace(self):
        speech = TranslationSpeech()
        speech.set_enabled(True)
        speech.pending = MagicMock()
        speech.pending.full.return_value = True
        speech.pending.get_nowait.side_effect = queue.Empty
        speech.offer("new")
        speech.pending.put_nowait.assert_called_once()

    def test_disabling_discards_pending_and_invalidates_current_generation(self):
        speech = TranslationSpeech()
        speech.set_enabled(True)
        generation = speech._generation
        speech.offer("old")
        speech.set_enabled(False)
        self.assertTrue(speech.pending.empty())
        self.assertNotEqual(generation, speech._generation)
        speech.offer("ignored")
        self.assertTrue(speech.pending.empty())

    def test_repeating_audio_on_does_not_cancel_current_speech(self):
        speech = TranslationSpeech()
        speech.set_enabled(True)
        generation = speech._generation
        speech.offer("current")
        speech.set_enabled(True)
        self.assertEqual(generation, speech._generation)
        self.assertFalse(speech.pending.empty())

    def test_voice_matches_target_language(self):
        english, portuguese = MagicMock(), MagicMock()
        english.GetAttribute.return_value = "409"
        portuguese.GetAttribute.return_value = "416"
        portuguese.GetDescription.return_value = "Portuguese voice"
        voice = MagicMock()
        voice.GetVoices.return_value = [english, portuguese]
        self.assertEqual(select_voice(voice, "pt"), "Portuguese voice")
        self.assertIs(voice.Voice, portuguese)

    def test_missing_voice_reports_install_instructions(self):
        voice = MagicMock()
        voice.GetVoices.return_value = []
        with self.assertRaisesRegex(RuntimeError, "Instale uma voz"):
            select_voice(voice, "pt")

    def test_stop_cancels_speech_and_treats_text_as_plain_text(self):
        speech, stop, entered = TranslationSpeech(), threading.Event(), threading.Event()
        speech.set_enabled(True)
        speech.offer("<video text>")
        voice = MagicMock()

        def speaking(timeout):
            entered.set()
            time.sleep(.01)
            return False

        voice.WaitUntilDone.side_effect = speaking
        with patch("win32com.client.Dispatch", return_value=voice), \
                patch("core.translation_speech.select_voice", return_value="pt voice"):
            worker = threading.Thread(target=speech.run, args=(stop, "pt", lambda text: None))
            worker.start()
            self.assertTrue(entered.wait(2))
            stop.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        voice.Speak.assert_any_call("<video text>", 19)
        voice.Speak.assert_any_call("", 19)

    def test_narration_waits_for_assistant_without_stopping_caption_queue(self):
        speech, stop = TranslationSpeech(), threading.Event()
        speech.set_enabled(True)
        speech.offer("caption")
        assistant_speaking(True)
        with patch("core.translation_voice.create_voice") as create:
            worker = threading.Thread(target=speech.run, args=(stop, "pt", lambda text: None))
            worker.start()
            time.sleep(.1)
            stop.set()
            worker.join(2)
            create.return_value.speak.assert_not_called()
        self.assertFalse(worker.is_alive())


if __name__ == "__main__":
    unittest.main()
