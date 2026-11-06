"""Local-only Whisper + Argos backend. Model downloads belong to setup_translation.py."""
from __future__ import annotations

import os
from pathlib import Path
import threading
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
MODEL_ROOT = ROOT / "models" / "translation"
_DLL_HANDLES = []


def language_code(value):
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    aliases = {"portugues brasileiro": "pt", "portugues": "pt", "portuguese": "pt",
               "brazilian portuguese": "pt", "pt-br": "pt", "ingles": "en", "english": "en",
               "espanhol": "es", "spanish": "es", "frances": "fr", "french": "fr",
               "alemao": "de", "german": "de", "italiano": "it", "italian": "it",
               "japones": "ja", "japanese": "ja", "chines": "zh", "chinese": "zh",
               "coreano": "ko", "korean": "ko", "russo": "ru", "russian": "ru"}
    code = aliases.get(text, text)
    if not (len(code) in (2, 3) and code.isascii() and code.isalpha()):
        raise ValueError("Informe o idioma pelo nome ou código, como português, inglês, pt ou en.")
    return code


def register_cuda_dlls():
    """Keep Windows DLL search handles alive for pip-installed NVIDIA runtimes."""
    if os.name != "nt" or _DLL_HANDLES:
        return
    import sysconfig
    nvidia = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
    for folder in (nvidia / "cublas" / "bin", nvidia / "cudnn" / "bin", nvidia / "cuda_nvrtc" / "bin"):
        if folder.is_dir():
            _DLL_HANDLES.append(os.add_dll_directory(str(folder)))
            # CTranslate2 uses LoadLibrary, which also needs PATH on Windows.
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")


def audio_samples(pcm, rate, channels):
    import numpy as np
    from math import gcd
    from scipy.signal import resample_poly
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32).reshape(-1, channels)
    mono = samples.mean(axis=1) / 32768.0
    if rate != 16000:
        divisor = gcd(rate, 16000)
        mono = resample_poly(mono, 16000 // divisor, rate // divisor)
    return np.ascontiguousarray(mono, dtype=np.float32)


class LocalTranslator:
    def __init__(self):
        self.model = None
        self.device = ""
        self.model_name = ""
        self.source = None
        self.detected = ""
        self.last_seconds = 0.0
        self._translations = {}
        self._lock = threading.RLock()

    def prepare(self):
        with self._lock:
            if self.model is not None:
                return
            register_cuda_dlls()
            import ctranslate2
            from faster_whisper import WhisperModel
            device = os.getenv("JARVIS_TRANSLATION_DEVICE", "auto").lower()
            if device == "auto":
                device = "cuda" if ctranslate2.get_cuda_device_count() else "cpu"
            if device not in ("cuda", "cpu"):
                raise ValueError("JARVIS_TRANSLATION_DEVICE deve ser auto, cuda ou cpu.")
            name = os.getenv("JARVIS_TRANSLATION_MODEL", "small" if device == "cuda" else "base")
            path = MODEL_ROOT / name
            if not (path / "model.bin").is_file():
                raise RuntimeError(f"Modelo {name} ausente. Execute: python setup_translation.py --model {name}")
            try:
                model = WhisperModel(str(path), device=device,
                                     compute_type="float16" if device == "cuda" else "int8",
                                     cpu_threads=4, local_files_only=True)
                # Force lazy CUDA/cuDNN initialization before reporting ready.
                import numpy as np
                # Load the resampler/BLAS before opening WASAPI. Loading these
                # native libraries for the first time during capture can stall
                # the first caption for several seconds on Windows.
                audio_samples(np.zeros(88200, dtype=np.int16).tobytes(), 44100, 2)
                segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32),
                                               language="en", beam_size=1)
                list(segments)
                segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32),
                                               language="en", beam_size=1, vad_filter=True)
                list(segments)
            except Exception as exc:
                raise RuntimeError("Falha no reconhecimento local em " + device + ": " + str(exc)[:200] +
                                   ". Para usar CPU: JARVIS_TRANSLATION_DEVICE=cpu; "
                                   "prepare o modelo base com setup_translation.py.") from exc
            self.model, self.device, self.model_name = model, device, name

    def text_translation(self, text, source, target):
        if source == target:
            return text
        if not text:
            return ""
        import argostranslate.package as package
        installed = package.get_installed_packages()
        if not any(p.from_code == source and p.to_code == target for p in installed)                 and "en" not in (source, target):
            # No direct model (e.g. zh -> pt): pivot through English.
            return self._translate_hop(self._translate_hop(text, source, "en"), "en", target)
        return self._translate_hop(text, source, target)

    def _translate_hop(self, text, source, target):
        key = (source, target)
        if key not in self._translations:
            import argostranslate.package as package
            import ctranslate2
            pkg = next((p for p in package.get_installed_packages()
                        if p.from_code == source and p.to_code == target), None)
            if pkg is None:
                raise RuntimeError(f"Tradução local {source} → {target} não instalada. "
                                   f"Execute: python setup_translation.py --source {source} --target {target}")
            # Captions are already short segments. Decode Argos models directly,
            # avoiding its sentence splitter's lazy network downloads and startup cost.
            translator = ctranslate2.Translator(str(pkg.package_path / "model"),
                                                device="cpu", compute_type="int8",
                                                inter_threads=1, intra_threads=4)
            self._translations[key] = (pkg, translator)
        if not text:
            return ""
        pkg, translator = self._translations[key]
        results = translator.translate_batch(
            [pkg.tokenizer.encode(text)], beam_size=1, num_hypotheses=1,
            target_prefix=[[pkg.target_prefix]] if pkg.target_prefix else None,
            replace_unknowns=True, max_decoding_length=192,
        )
        result = pkg.tokenizer.decode(results[0].hypotheses[0]).strip()
        if pkg.target_prefix and result.startswith(pkg.target_prefix):
            result = result[len(pkg.target_prefix):].strip()
        return result

    def translate(self, pcm, rate, channels, target):
        import time
        with self._lock:
            self.prepare()
            started = time.monotonic()
            samples = audio_samples(pcm, rate, channels)
            segments, info = self.model.transcribe(
                samples, language=self.source, task="transcribe", beam_size=1,
                condition_on_previous_text=False, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.7).strip()
            self.detected = info.language
            result = self.text_translation(text, info.language, language_code(target)) if text else ""
            self.last_seconds = time.monotonic() - started
            return result[:1200]


backend = LocalTranslator()
