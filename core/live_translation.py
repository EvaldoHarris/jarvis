"""Bounded Windows loopback capture and translated captions, without microphone use."""
from __future__ import annotations

import queue
import sys
import threading
import time
from core.local_translation import backend, language_code
from core.translation_speech import TranslationSpeech


def translate_audio(pcm, rate, channels, language):
    return backend.translate(pcm, rate, channels, language)


class AudioSegmenter:
    """End on a short pause, with a two-second latency ceiling and no silent chunks."""
    def __init__(self, rate, channels):
        self.rate, self.channels = rate, channels
        self.frames, self.duration, self.silence = [], 0.0, 0.0

    def feed(self, block):
        import numpy as np
        samples = np.frombuffer(block, dtype="<i2").astype(np.float32)
        duration = len(samples) / self.channels / self.rate
        voiced = bool(samples.size and np.sqrt(np.mean(samples * samples)) >= 100)
        if not self.frames and not voiced:
            return None
        self.frames.append(block)
        self.duration += duration
        self.silence = 0.0 if voiced else self.silence + duration
        if self.duration >= 2.0 or (self.duration >= 0.6 and self.silence >= 0.3):
            pcm = b"".join(self.frames)
            self.frames, self.duration, self.silence = [], 0.0, 0.0
            return pcm
        return None


class LiveTranslation:
    def __init__(self):
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._threads = []
        self.state = "stopped"
        self.error = ""
        self.speech = TranslationSpeech()

    def start(self, emit, language="português brasileiro", source_language="auto", audio=True):
        with self._lock:
            if any(t.is_alive() for t in self._threads):
                if self.state == "running":
                    return self.set_audio(audio)
                return "A tradução está iniciando ou encerrando."
            if sys.platform != "win32":
                return "A captura de áudio para tradução está disponível no Windows."
            try:
                import faster_whisper  # noqa: F401
                import argostranslate  # noqa: F401
                import scipy  # noqa: F401
            except ImportError:
                return "Instale a tradução local: python -m pip install -r requirements-translation.txt"
            try:
                language = language_code(language)
                source = None if source_language == "auto" else language_code(source_language)
            except ValueError as exc:
                return str(exc)
            self._stop = threading.Event()
            stop = self._stop
            chunks = queue.Queue(maxsize=1)
            self.state, self.error = "starting", ""
            self.speech = TranslationSpeech()
            self.speech.set_enabled(audio)
            self._threads = [threading.Thread(target=self._run,
                            args=(stop, chunks, emit, language, source), daemon=True)]
            emit("Carregando tradução local… Voz neural local por padrão, sem enviar áudio ou texto ao Gemini.")
            for thread in self._threads:
                thread.start()
            return ("Iniciando tradução local em " + language + (" com áudio e legendas." if audio else " com legendas.") +
                    " A voz do Jarvis será excluída da captura.")

    def _run(self, stop, chunks, emit, language, source):
        capture = None
        speaker = None
        try:
            backend.prepare()
            if stop.is_set():
                return
            backend.source = source
            # Validate an explicitly requested language pair before opening capture.
            if source and source != language:
                backend.text_translation("", source, language)
            speaker = threading.Thread(target=self.speech.run, args=(stop, language, emit), daemon=True)
            speaker.start()
            while not self.speech.ready.wait(0.1):
                if stop.is_set():
                    return
            with self._lock:
                if stop.is_set():
                    return
                emit(f"Tradução local pronta ({backend.model_name}, {backend.device}). Aguardando áudio…")
                capture = threading.Thread(target=self._capture, args=(stop, chunks, emit), daemon=True)
                capture.start()
            self._translate(stop, chunks, emit, language)
        except Exception as exc:
            self._fail(stop, emit, exc)
        finally:
            stop.set()
            self.speech.set_enabled(False)
            if speaker:
                speaker.join(timeout=3)
                if speaker.is_alive():
                    with self._lock:
                        self._threads.append(speaker)
            if capture:
                capture.join(timeout=3)
                # Prevent a restart while a driver is still closing its stream.
                if capture.is_alive():
                    with self._lock:
                        self._threads.append(capture)

    def stop(self):
        with self._lock:
            self._stop.set()
            self.state = "stopped"
            self.speech.set_enabled(False)
        return "Tradução encerrada."

    def set_audio(self, enabled):
        if self.state not in ("starting", "running"):
            return "Inicie a tradução antes de alterar o áudio."
        self.speech.set_enabled(bool(enabled))
        return "Áudio da tradução ativado." if enabled else "Áudio da tradução desativado; legendas continuam."

    def _fail(self, stop, emit, exc):
        with self._lock:
            if stop.is_set():
                return
            self.error = str(exc)[:300]
            self.state = "error"
            emit("Tradução interrompida: " + self.error)
            stop.set()

    def _capture(self, stop, chunks, emit):
        try:
            from core.process_loopback import ProcessLoopback
            with ProcessLoopback() as stream:
                rate, channels = stream.rate, stream.channels
                with self._lock:
                    if stop.is_set():
                        return
                    self.state = "running"
                segmenter = AudioSegmenter(rate, channels)
                for block in stream.packets(stop):
                    pcm = segmenter.feed(block)
                    if pcm is None:
                        continue
                    item = (time.monotonic(), pcm, rate, channels)
                    try:
                        chunks.put_nowait(item)
                    except queue.Full:
                        try:
                            chunks.get_nowait()
                        except queue.Empty:
                            pass
                        chunks.put_nowait(item)
        except Exception as exc:
            self._fail(stop, emit, exc)

    def _translate(self, stop, chunks, emit, language):
        try:
            while not stop.is_set():
                try:
                    created, pcm, rate, channels = chunks.get(timeout=0.2)
                except queue.Empty:
                    continue
                if time.monotonic() - created > 4:
                    continue
                text = translate_audio(pcm, rate, channels, language)
                with self._lock:
                    if not stop.is_set() and text:
                        emit(text)
                        self.speech.offer(text)
        except Exception as exc:
            self._fail(stop, emit, exc)


translation = LiveTranslation()
