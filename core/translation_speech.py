"""Bounded, cancellable neural narration for translated captions."""
from __future__ import annotations

import locale
import queue
import threading
import time

_speaking = threading.Event()
_assistant = threading.Event()
_tail_until = 0.0


def voice_active():
    """Microphone guard, including a short acoustic playback tail."""
    return _speaking.is_set() or time.monotonic() < _tail_until


def assistant_speaking(active):
    _assistant.set() if active else _assistant.clear()


def select_voice(voice, language):
    for token in voice.GetVoices():
        for code in token.GetAttribute("Language").split(";"):
            try:
                name = locale.windows_locale.get(int(code, 16), "")
            except ValueError:
                continue
            if name.split("_")[0] == language:
                voice.Voice = token
                return token.GetDescription()
    raise RuntimeError(f"Não há voz local do Windows para {language}. Instale uma voz desse idioma nas configurações de fala.")


class TranslationSpeech:
    def __init__(self):
        self.enabled = threading.Event()
        self.pending = queue.Queue(maxsize=1)
        self.error = ""
        self.voice_name = ""
        self.ready = threading.Event()
        self._generation = 0
        self._lock = threading.RLock()

    def set_enabled(self, enabled):
        with self._lock:
            if bool(enabled) == self.enabled.is_set():
                return
            self._generation += 1
            self.enabled.set() if enabled else self.enabled.clear()
            while True:
                try:
                    self.pending.get_nowait()
                except queue.Empty:
                    break

    def offer(self, text):
        with self._lock:
            if not self.enabled.is_set():
                return
            item = (time.monotonic(), self._generation, text)
            if self.pending.full():
                try:
                    self.pending.get_nowait()
                except queue.Empty:
                    pass  # Narrator may have consumed it after full() returned.
            self.pending.put_nowait(item)

    def run(self, stop, language, report):
        global _tail_until
        voice = None
        try:
            from core.translation_voice import create_voice
            if self.enabled.is_set() and not stop.is_set():
                try:
                    voice = create_voice(language)
                    self.voice_name = voice.name
                except Exception as exc:
                    self.error = str(exc)[:300]
                    self.set_enabled(False)
                    if not stop.is_set():
                        report("Áudio da tradução desativado: " + self.error + ". As legendas continuam.")
            self.ready.set()
            while not stop.is_set():
                try:
                    created, generation, text = self.pending.get(timeout=0.1)
                except queue.Empty:
                    continue
                while _assistant.is_set() and not stop.wait(0.05):
                    if time.monotonic() - created > 4:
                        break
                if (stop.is_set() or not self.enabled.is_set() or generation != self._generation
                        or time.monotonic() - created > 4 or _assistant.is_set()):
                    continue
                try:
                    if voice is None:
                        voice = create_voice(language)
                        self.voice_name = voice.name
                    self.error = ""
                    if stop.is_set() or not self.enabled.is_set() or generation != self._generation:
                        continue
                    _speaking.set()
                    voice.speak(text, lambda: stop.is_set() or not self.enabled.is_set()
                                or generation != self._generation or _assistant.is_set())
                except Exception as exc:
                    self.error = str(exc)[:300]
                    self.set_enabled(False)
                    if voice is not None:
                        try:
                            voice.close()
                        except Exception:
                            pass
                        voice = None
                    if not stop.is_set():
                        report("Áudio da tradução desativado: " + self.error + ". As legendas continuam.")
                finally:
                    _tail_until = time.monotonic() + 0.35
                    _speaking.clear()
        except Exception as exc:
            self.error = str(exc)[:300]
            self.set_enabled(False)
            if not stop.is_set():
                report("Áudio da tradução desativado: " + self.error + ". As legendas continuam.")
        finally:
            self.ready.set()
            if voice is not None:
                try:
                    voice.close()
                except Exception:
                    pass
                finally:
                    voice = None
            _speaking.clear()
