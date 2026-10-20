"""Distinguish an actual answer from transcript/connection housekeeping."""
import numpy as np


class MicrophoneTurn:
    """A conservative local watchdog trigger, without changing server VAD/audio."""
    def __init__(self):
        self.started = None
        self.last_voice = 0.0
        self.voiced_seconds = 0.0

    def observe(self, pcm, now, rate=16000):
        samples = np.frombuffer(pcm, dtype=np.int16)
        if not samples.size:
            return
        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
        if rms >= 350:
            if self.started is None:
                self.started = now
            self.last_voice = now
            self.voiced_seconds += samples.size / rate

    def ended(self, now):
        if self.started is None or now - self.last_voice < 0.7:
            return None
        start = self.started
        voiced = self.voiced_seconds
        self.started = None
        self.voiced_seconds = 0.0
        return start if voiced >= 0.25 else None


def has_answer_progress(response):
    if getattr(response, "data", None) or getattr(response, "tool_call", None):
        return True
    content = getattr(response, "server_content", None)
    if content is None:
        return False
    transcript = getattr(content, "output_transcription", None)
    if (getattr(transcript, "text", None) or "").strip():
        return True
    turn = getattr(content, "model_turn", None)
    return any(getattr(part, "text", None) or getattr(part, "inline_data", None)
               for part in (getattr(turn, "parts", None) or []))
