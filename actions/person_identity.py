"""Camera face identity, explicitly enrolled by the user."""
import json


def person_identity(parameters=None, **kwargs):
    from core.person_identity import manage_identity
    args = parameters or {}
    try:
        result = manage_identity(args.get("action", "identify"), args.get("name", ""),
                                 args.get("replace", False))
    except Exception as exc:
        result = {"status": "failed", "reason": str(exc)}
    return json.dumps(result, ensure_ascii=False)


TOOL = {
    "name": "person_identity", "tier": "core",
    "description": (
        "Locally recognizes an enrolled person by webcam face. Always try the camera for identity recognition; no voice sample is required. "
        "Use register only on the person's explicit request to enroll their own face; "
        "name must be supplied by that person, never guessed. They must be alone in the camera. "
        "identify compares the camera face against local profiles; "
        "register_voice separately enrolls the owner's voice for continuous listening, only on explicit request. "
        "Ask them to say Jarvis several times for at least 3 seconds, then call register_voice with their supplied name. "
        "Use typed input or push-to-talk for initial voice enrollment. This selects the voice allowed to activate the assistant. "
        "only status=done with name confirms a match. Never infer identity just from appearance, "
        "configured user_name or a partial match. list shows enrolled names; forget deletes "
        "only the specifically requested person's local profile. replace only on explicit request. "
        "This is personalization, not authentication or proof of who is physically speaking."
    ),
    "brief": "Camera identity: register, identify, list, forget. Separate register_voice enrolls the owner for Jarvis keyword activation, using recent speech and explicit consent. Never guess identity.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["register", "register_voice", "identify", "list", "forget"]},
        "name": {"type": "STRING", "description": "Name explicitly supplied by the person for register/forget."},
        "replace": {"type": "BOOLEAN", "description": "Replace existing enrollment only if explicitly requested."},
    }, "required": ["action"]},
    "handler": person_identity,
}
