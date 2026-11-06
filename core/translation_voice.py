"""Cancellable voices for captions; offline neural voice by default."""
from __future__ import annotations

import asyncio
import os
from contextlib import suppress


class NeuralVoice:
    def __init__(self, language):
        from providers.tts_piper import PiperTTS, installed, language_of
        preferred = os.getenv("JARVIS_TRANSLATION_VOICE", "pt_BR-faber-medium" if language == "pt" else "")
        available = installed()
        if preferred and language_of(preferred) != language:
            raise RuntimeError("A voz neural escolhida não corresponde ao idioma da tradução.")
        chosen = preferred or next((v for v in available if language_of(v) == language), "")
        if not chosen or chosen not in available:
            raise RuntimeError("Voz neural local não instalada. Execute python setup_translation.py --voice " +
                               (chosen or "NOME_DA_VOZ"))
        self.name = "Piper / " + chosen
        self.provider = PiperTTS({"voice": chosen, "follow_language": "0", "speed": 1.1})
        self.loop = asyncio.new_event_loop()
        # Only installed models are accepted; warmup cannot trigger a download.
        try:
            self.loop.run_until_complete(self._warmup())
        except Exception:
            self.close()
            raise

    async def _warmup(self):
        async for _ in self.provider.speak("."):
            pass

    def speak(self, text, cancelled):
        self.loop.run_until_complete(self._cancellable_play(text, cancelled))

    async def _cancellable_play(self, text, cancelled):
        if cancelled():
            return
        task = asyncio.create_task(self._play(text, cancelled))
        try:
            while not task.done():
                if cancelled():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    return
                await asyncio.wait({task}, timeout=0.05)
            await task
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def _play(self, text, cancelled):
        import sounddevice as sd
        from memory.config_manager import get_output_device
        from core.audio_devices import resolve
        stream = None
        audio = self.provider.speak(text)
        try:
            async for pcm in audio:
                if cancelled():
                    break
                if stream is None:
                    stream = sd.RawOutputStream(samplerate=24000, channels=1, dtype="int16",
                                                latency="low", device=resolve(get_output_device(), "output"))
                    stream.start()
                # The provider yields 50 ms pieces: stop never waits for a whole phrase.
                stream.write(pcm)
        finally:
            try:
                await audio.aclose()
            finally:
                if stream is not None:
                    if cancelled():
                        stream.abort()
                    else:
                        stream.stop()
                    stream.close()

    def close(self):
        if not self.loop.is_closed():
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.run_until_complete(self.loop.shutdown_default_executor())
            self.loop.close()


class GeminiSpeechProvider:
    def __init__(self, client, voice, model):
        self.client, self.voice, self.model = client, voice, model

    async def speak(self, text):
        from google.genai import types
        from providers.audio import chunk
        # Dedicated TTS reads the verbatim subtitle instead of conversing about it.
        voice_config = ({"voice": self.voice} if self.model.startswith("gemini-3.8") else
                        {"prebuilt_voice_config": {"voice_name": self.voice}})
        responses = await self.client.aio.models.generate_content_stream(
            model=self.model, contents=text,
            config=types.GenerateContentConfig(response_modalities=["AUDIO"],
                                                speech_config={"voice_config": voice_config}),
        )
        produced = False
        try:
            async for response in responses:
                for candidate in response.candidates or []:
                    for part in (getattr(candidate.content, "parts", None) or []):
                        blob = part.inline_data
                        if not blob or not blob.data:
                            continue
                        mime = (blob.mime_type or "").lower()
                        if not ("audio/l16" in mime or "audio/pcm" in mime):
                            raise RuntimeError("O Gemini retornou um formato de áudio inesperado: " + mime)
                        if "rate=" in mime and "rate=24000" not in mime:
                            raise RuntimeError("O Gemini retornou uma taxa de áudio inesperada: " + mime)
                        produced = True
                        for piece in chunk(blob.data):
                            yield piece
        finally:
            await responses.aclose()
        if not produced:
            raise RuntimeError("O Gemini não retornou áudio para a legenda.")


class GeminiVoice(NeuralVoice):
    def __init__(self, language):
        from google import genai
        from memory.config_manager import get_gemini_key, get_voice
        key = get_gemini_key()
        if not key:
            raise RuntimeError("Configure a chave do Gemini para usar a voz Charon na tradução.")
        model = os.getenv("JARVIS_TRANSLATION_TTS_MODEL", "gemini-3.8-flash-lite-tts")
        voice = get_voice()
        self.name = "Gemini / " + voice
        self.client = genai.Client(api_key=key, http_options={"timeout": 12000})
        self.provider = GeminiSpeechProvider(self.client, voice, model)
        self.loop = asyncio.new_event_loop()

    def close(self):
        try:
            if not self.loop.is_closed():
                self.loop.run_until_complete(self.client.aio.aclose())
            super().close()
        finally:
            self.client.close()


class SystemVoice:
    """Explicit compatibility option; never silently replaces a neural voice."""
    def __init__(self, language):
        import pythoncom
        import win32com.client
        from core.translation_speech import select_voice
        pythoncom.CoInitialize()
        self.voice = None
        try:
            self.voice = win32com.client.Dispatch("SAPI.SpVoice")
            self.name = select_voice(self.voice, language)
            self.voice.Rate = 3
        except Exception:
            self.close()
            raise

    def speak(self, text, cancelled):
        self.voice.Speak(text, 1 | 2 | 16)
        while not self.voice.WaitUntilDone(25):
            if cancelled():
                self.voice.Speak("", 1 | 2 | 16)
                break

    def close(self):
        import pythoncom
        try:
            if self.voice is not None:
                self.voice.Speak("", 1 | 2 | 16)
        finally:
            self.voice = None
            pythoncom.CoUninitialize()


def create_voice(language):
    engine = os.getenv("JARVIS_TRANSLATION_TTS", "piper").strip().lower()
    if engine == "gemini":
        return GeminiVoice(language)
    if engine == "system":
        return SystemVoice(language)
    if engine != "piper":
        raise ValueError("JARVIS_TRANSLATION_TTS deve ser gemini, piper ou system.")
    return NeuralVoice(language)
