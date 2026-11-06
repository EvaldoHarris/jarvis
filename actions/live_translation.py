"""Voice tool for system-audio translation."""
from core.live_translation import translation


def live_translation(parameters=None, player=None):
    params = parameters or {}
    action = params.get("action", "start")
    if action == "status":
        from core.local_translation import backend
        return ("Tradução local: " + translation.state +
                f"; modelo={backend.model_name or 'não carregado'}; dispositivo={backend.device or 'auto'}; "
                f"último processamento={backend.last_seconds:.2f}s" +
                f"; áudio={'ativado' if translation.speech.enabled.is_set() else 'desativado'}" +
                f"; voz={translation.speech.voice_name or 'neural local'}" +
                ("; " + translation.speech.error if translation.speech.error else "") +
                (". " + translation.error if translation.error else ""))
    if action in ("audio_on", "audio_off"):
        return translation.set_audio(action == "audio_on")
    if action == "stop":
        result = translation.stop()
        if player is not None:
            player.show_translation_caption("")
        return result
    if action != "start":
        return "Ação inválida. Use start, stop, status, audio_on ou audio_off."
    if player is None or not hasattr(player, "show_translation_caption"):
        return "A janela de legendas não está disponível."
    language = str(params.get("language") or "português brasileiro").strip()[:80]
    return translation.start(player.show_translation_caption, language,
                             str(params.get("source_language") or "auto"), bool(params.get("audio", True)))


TOOL = {
    "name": "live_translation",
    "description": "Translate the video the user is watching using computer output audio, with floating subtitles. "
                   "Use for 'traduza o que estou assistindo', 'traduzir vídeo em tempo real', "
                   "'ativar legendas traduzidas'. stop: 'parar tradução'. Does not play or open videos. "
                   "Speech recognition and translation run locally using Whisper and Argos. "
                   "Narration defaults to an offline Piper neural voice; no audio or text is sent to Gemini. "
                   "Excludes Jarvis process audio. Spoken translation and subtitles are enabled by default. "
                   "audio=false for subtitles only. audio_on/audio_off toggle narration during translation. "
                   "Use audio_on for 'ative o áudio da tradução', audio_off for 'somente legendas'. "
                   "Default target: Brazilian Portuguese. source_language defaults to auto; "
                   "set en for English videos to improve recognition on short phrases.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["start", "stop", "status", "audio_on", "audio_off"]},
        "audio": {"type": "BOOLEAN", "description": "Speak translated captions locally; default true"},
        "language": {"type": "STRING", "description": "Target language"},
        "source_language": {"type": "STRING", "description": "Source language code, e.g. en, es, or auto"},
    }, "required": ["action"]},
    "handler": live_translation,
}
