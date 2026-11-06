import asyncio
import threading
import time
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

from core.translation_voice import NeuralVoice, GeminiSpeechProvider, create_voice


class NeuralPlaybackTests(unittest.TestCase):
    def test_cancel_interrupts_wait_for_network_before_any_audio(self):
        voice = NeuralVoice.__new__(NeuralVoice)
        voice.loop = asyncio.new_event_loop()
        voice.provider = MagicMock()
        stop = threading.Event()

        async def stalled(text):
            await asyncio.sleep(30)
            yield b"\0" * 2400

        voice.provider.speak.side_effect = stalled
        timer = threading.Timer(.1, stop.set)
        timer.start()
        start = time.monotonic()
        try:
            voice.speak("caption", stop.is_set)
            self.assertLess(time.monotonic() - start, 1)
        finally:
            timer.cancel()
            voice.close()

    def test_default_voice_is_local_without_cloud_fallback(self):
        with patch.dict("os.environ", {}, clear=True), \
                patch("core.translation_voice.NeuralVoice") as local, \
                patch("core.translation_voice.GeminiVoice") as cloud:
            self.assertIs(create_voice("pt"), local.return_value)
            cloud.assert_not_called()

    def test_explicit_gemini_option_uses_jarvis_adapter(self):
        with patch.dict("os.environ", {"JARVIS_TRANSLATION_TTS": "gemini"}), \
                patch("core.translation_voice.GeminiVoice") as voice:
            self.assertIs(create_voice("pt"), voice.return_value)
            voice.assert_called_once_with("pt")

    def test_gemini_sends_only_verbatim_translated_text_and_chosen_voice(self):
        from google.genai import types
        client = MagicMock()

        async def stream():
            yield types.GenerateContentResponse(candidates=[types.Candidate(
                content=types.Content(parts=[types.Part.from_bytes(
                    data=b"\0" * 4800, mime_type="audio/L16;codec=pcm;rate=24000")]))])

        client.aio.models.generate_content_stream = AsyncMock(return_value=stream())
        provider = GeminiSpeechProvider(client, "Charon", "gemini-3.8-flash-lite-tts")

        async def collect():
            return b"".join([pcm async for pcm in provider.speak("Olá")])

        self.assertEqual(len(asyncio.run(collect())), 4800)
        args = client.aio.models.generate_content_stream.call_args.kwargs
        self.assertEqual(args["contents"], "Olá")
        self.assertEqual(args["config"].speech_config.voice_config.voice, "Charon")

    def test_cancel_aborts_only_translation_stream_and_stops_writing(self):
        voice = NeuralVoice.__new__(NeuralVoice)
        voice.loop = asyncio.new_event_loop()
        voice.provider = MagicMock()
        cancelled = [False]

        async def chunks(text):
            yield b"\0" * 2400
            cancelled[0] = True
            yield b"\0" * 2400

        voice.provider.speak.side_effect = chunks
        stream = MagicMock()
        try:
            with patch("sounddevice.RawOutputStream", return_value=stream), \
                    patch("core.audio_devices.resolve", return_value=None):
                voice.speak("caption", lambda: cancelled[0])
            stream.write.assert_called_once()
            stream.abort.assert_called_once()
            stream.close.assert_called_once()
            stream.stop.assert_not_called()
        finally:
            voice.close()

    def test_cancelled_before_first_audio_does_not_open_output(self):
        voice = NeuralVoice.__new__(NeuralVoice)
        voice.loop = asyncio.new_event_loop()
        voice.provider = MagicMock()

        async def chunks(text):
            yield b"\0" * 2400

        voice.provider.speak.side_effect = chunks
        try:
            with patch("sounddevice.RawOutputStream") as output:
                voice.speak("caption", lambda: True)
                output.assert_not_called()
        finally:
            voice.close()

    def test_missing_model_does_not_download_during_translation(self):
        with patch("providers.tts_piper.installed", return_value=[]), \
                patch("providers.tts_piper.download") as download:
            with self.assertRaisesRegex(RuntimeError, "setup_translation.py --voice"):
                NeuralVoice("pt")
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
