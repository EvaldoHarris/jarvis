"""Opt-in local face and speaker embeddings; no biometric data sent to an API."""
import json
import threading
import time
import uuid
import unicodedata
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


def recent_voice(min_samples=32000):
    with _audio_lock:
        if time.monotonic() - _last_speech > 12:
            raise ValueError("Não há voz recente. Fale uma frase de pelo menos 3 segundos e tente novamente.")
        samples = np.frombuffer(b"".join(_audio), dtype=np.int16).astype(np.float32) / 32768
    if samples.size < min_samples:
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
        if kind not in profile:
            continue
        candidate = _unit(profile[kind])
        if candidate.shape == vector.shape:
            scores.append((float(vector @ candidate), name))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < threshold:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.08:
        # A short name and its full-name enrollment must not compete against
        # themselves. Require both a name prefix and near-identical references;
        # unrelated names/ambiguous lookalikes still refuse a match.
        winner = scores[0][1]
        competing = [name for score, name in scores[1:] if scores[0][0] - score < .08]
        if kind != 'face' or any(not same_face_profile(winner, name, profiles) for name in competing):
            return None
    return scores[0][1]


def same_face_profile(first, second, profiles):
    def words(name):
        return unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().casefold().split()
    a, b = words(first), words(second)
    if not a or not b or not (a == b[:len(a)] or b == a[:len(b)]):
        return False
    try:
        return float(_unit(profiles[first]['face']) @ _unit(profiles[second]['face'])) >= .8
    except (KeyError, ValueError):
        return False


def _require_models(expected=("yunet.onnx", "sface.onnx")):
    if any(not (MODELS / name).is_file() for name in expected):
        command = "python setup_identity.py --voice" if "speaker.onnx" in expected else "python setup_identity.py"
        raise ValueError(f"Modelos ausentes. Execute: {command}")


def face_observation():
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
        vectors = []
        for face in (faces if faces is not None else []):
            if min(face[2], face[3]) < 48:
                continue  # tiny background faces cannot provide reliable identity
            aligned = recognizer.alignCrop(frame, face)
            vectors.append(_unit(recognizer.feature(aligned)))
        return {'vectors': vectors, 'image': image, 'face_count': len(vectors)}


def face_embedding():
    observation = face_observation()
    if observation['face_count'] != 1:
        raise ValueError("Preciso de exatamente uma pessoa visível na câmera para reconhecer o rosto.")
    return observation['vectors'][0]


def voice_embedding(samples):
    global _voice_model
    import sherpa_onnx

    _require_models(("speaker.onnx",))
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
        if action == "register_voice":
            if not name.strip() or len(name.strip()) > 80:
                raise ValueError("Informe um nome entre 1 e 80 caracteres.")
            name = name.strip()
            profile = profiles.get(name, {})
            if "voice" in profile and not replace:
                raise ValueError("Voz já cadastrada. Use replace somente a pedido explícito.")
            vector = voice_embedding(recent_voice())
            from memory.config_manager import get_input_device
            profile.update(voice=vector.tolist(), voice_model="wespeaker-en-resnet34-LM",
                           voice_input_device=get_input_device())
            profiles[name] = profile
            _save_profiles(profiles)
            from memory.config_manager import save_voice_owner
            save_voice_owner(name)
            return {"status": "done", "registered_voice": name, "wake_word": "Jarvis"}
        if action not in ("register", "identify"):
            raise ValueError("Use register, identify, list ou forget.")
        name = name.strip()
        if action == "register":
            if not name or len(name) > 80:
                raise ValueError("Informe um nome entre 1 e 80 caracteres.")
            if name in profiles and not replace:
                raise ValueError("Nome já cadastrado. Só substitua após pedido explícito do usuário.")
        elif not profiles:
            raise ValueError("Nenhuma pessoa cadastrada. Peça para cadastrar o rosto pela câmera primeiro.")
        face = face_embedding()
        if action == "register":
            profiles.setdefault(name, {}).update(face=face.tolist(), face_model="sface-2021dec")
            _save_profiles(profiles)
            return {"status": "done", "registered": name, "stored_locally": True}
        face_name = best_match(face, profiles, "face", 0.45)
        return {"status": "done" if face_name else "unverified", "name": face_name,
                "face_match": face_name,
                "reason": None if face_name else "O rosto na câmera não confirmou uma pessoa cadastrada."}


def verify_voice_owner(samples):
    """Fail closed: only the explicitly configured owner's voice may activate."""
    from memory.config_manager import load_api_keys
    from core.voice_health import record
    config = load_api_keys()
    owner = (config.get("voice_owner") or config.get("user_name") or "").strip()
    profiles = load_profiles()
    if not owner or "voice" not in profiles.get(owner, {}):
        record("activation_owner_enrollment_missing")
        return None
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size < 5600:  # A short keyword is allowed; never pad/repeat speech.
        record("activation_voice_sample_too_short")
        return None
    vector = _unit(voice_embedding(samples))
    reference = _unit(profiles[owner]["voice"])
    if vector.shape != reference.shape:
        record("activation_voice_model_incompatible")
        return None
    score = float(vector @ reference)
    competitors = [_unit(profile["voice"]) for name, profile in profiles.items()
                   if name != owner and "voice" in profile]
    others = [float(vector @ candidate) for candidate in competitors if candidate.shape == vector.shape]
    margin = score - max(others) if others else None
    reason = "below_threshold" if score < .65 else (
        "ambiguous" if margin is not None and margin < .08 else "matched")
    record(f"activation_voice_comparison reason={reason} score={score:.3f} "
           f"threshold=0.650 margin={margin if margin is None else round(margin, 3)}")
    match = best_match(vector, profiles, "voice", 0.65)
    return owner if match == owner else None
