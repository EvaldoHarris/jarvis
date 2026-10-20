"""Opt-in local face and speaker embeddings; no biometric data sent to an API."""
import json
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import numpy as np

from memory.config_manager import get_base_dir

ROOT = get_base_dir()
MODELS = ROOT / "models" / "identity"
PROFILES = ROOT / "memory" / "identities" / "profiles.json"
_audio_lock = threading.Lock()
_model_lock = threading.RLock()
_audio = deque(maxlen=125)  # <= 8 seconds of 1024-sample PCM16 mic blocks
_last_speech = 0.0
_face_models = None
_voice_model = None


def feed_microphone(pcm, sample_rate=16000):
    """Called only for unmuted local user audio, never the assistant's output."""
    global _last_speech
    if sample_rate != 16000:
        return
    samples = np.frombuffer(pcm, dtype=np.int16)
    if not samples.size or np.sqrt(np.mean(samples.astype(np.float32) ** 2)) < 180:
        return
    now = time.monotonic()
    with _audio_lock:
        if now - _last_speech > 1.25:
            _audio.clear()
        _last_speech = now
        _audio.append(bytes(pcm))


def recent_voice():
    with _audio_lock:
        if time.monotonic() - _last_speech > 12:
            raise ValueError("Não há voz recente. Fale uma frase de pelo menos 3 segundos e tente novamente.")
        samples = np.frombuffer(b"".join(_audio), dtype=np.int16).astype(np.float32) / 32768
    if samples.size < 32000:
        raise ValueError("A fala foi curta. Diga uma frase de pelo menos 3 segundos para reconhecer a voz.")
    return samples


def load_profiles():
    if not PROFILES.exists():
        return {}
    return json.loads(PROFILES.read_text(encoding="utf-8"))


def _save_profiles(profiles):
    PROFILES.parent.mkdir(parents=True, exist_ok=True)
    temporary = PROFILES.with_name(f"profiles-{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
        temporary.replace(PROFILES)
    finally:
        temporary.unlink(missing_ok=True)


def _unit(vector):
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = np.linalg.norm(vector)
    if not np.isfinite(vector).all() or norm <= 0:
        raise ValueError("Amostra inválida para reconhecimento.")
    return vector / norm


def best_match(vector, profiles, kind, threshold):
    scores = []
    vector = _unit(vector)
    for name, profile in profiles.items():
        candidate = _unit(profile[kind])
        if candidate.shape == vector.shape:
            scores.append((float(vector @ candidate), name))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < threshold:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.08:
        return None
    return scores[0][1]


def _require_models():
    expected = ("yunet.onnx", "sface.onnx", "speaker.onnx")
    if any(not (MODELS / name).is_file() for name in expected):
        raise ValueError("Modelos ausentes. Execute: python setup_identity.py")


def face_embedding():
    global _face_models
    import cv2
    from actions.screen_processor import _capture_camera

    _require_models()
    image, _ = _capture_camera()
    frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("A câmera não retornou uma imagem válida.")
    height, width = frame.shape[:2]
    with _model_lock:
        if _face_models is None:
            detector = cv2.FaceDetectorYN.create(str(MODELS / "yunet.onnx"), "", (width, height), 0.85)
            recognizer = cv2.FaceRecognizerSF.create(str(MODELS / "sface.onnx"), "")
            _face_models = detector, recognizer
        detector, recognizer = _face_models
        detector.setInputSize((width, height))
        _, faces = detector.detect(frame)
        if faces is None or len(faces) != 1:
            raise ValueError("Preciso de exatamente uma pessoa visível na câmera para associar rosto e voz.")
        aligned = recognizer.alignCrop(frame, faces[0])
        return _unit(recognizer.feature(aligned))


def voice_embedding(samples):
    global _voice_model
    import sherpa_onnx

    _require_models()
    with _model_lock:
        if _voice_model is None:
            config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=str(MODELS / "speaker.onnx"), num_threads=2, provider="cpu")
            if not config.validate():
                raise ValueError("Modelo de voz inválido.")
            _voice_model = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        stream = _voice_model.create_stream()
        stream.accept_waveform(sample_rate=16000, waveform=samples)
        stream.input_finished()
        if not _voice_model.is_ready(stream):
            raise ValueError("Amostra de voz insuficiente.")
        return _unit(_voice_model.compute(stream))


def manage_identity(action, name="", replace=False):
    with _model_lock:
        profiles = load_profiles()
        if action == "list":
            return {"status": "done", "names": list(profiles)}
        if action == "forget":
            if name not in profiles:
                raise ValueError("Não existe cadastro com esse nome.")
            del profiles[name]
            _save_profiles(profiles)
            return {"status": "done", "removed": name}
        if action not in ("register", "identify"):
            raise ValueError("Use register, identify, list ou forget.")
        name = name.strip()
        if action == "register":
            if not name or len(name) > 80:
                raise ValueError("Informe um nome entre 1 e 80 caracteres.")
            if name in profiles and not replace:
                raise ValueError("Nome já cadastrado. Só substitua após pedido explícito do usuário.")
        elif not profiles:
            raise ValueError("Nenhuma pessoa cadastrada. Peça para cadastrar rosto e voz primeiro.")
        samples = recent_voice()  # freeze the user's last phrase before camera warmup
        face = face_embedding()
        voice = voice_embedding(samples)
        if action == "register":
            profiles[name] = {"face": face.tolist(), "voice": voice.tolist(),
                              "face_model": "sface-2021dec", "voice_model": "wespeaker-en-resnet34-LM"}
            _save_profiles(profiles)
            return {"status": "done", "registered": name, "stored_locally": True}
        face_name = best_match(face, profiles, "face", 0.45)
        voice_name = best_match(voice, profiles, "voice", 0.65)
        matched = face_name if face_name and face_name == voice_name else None
        return {"status": "done" if matched else "unverified", "name": matched,
                "face_match": face_name, "voice_match": voice_name,
                "reason": None if matched else "Rosto e voz não confirmaram a mesma pessoa."}
