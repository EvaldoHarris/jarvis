"""Face and voice identity, explicitly enrolled by the user."""
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
        "Locally recognizes an enrolled person by BOTH webcam face and recent microphone voice. "
        "Use register only on the person's explicit request to enroll their own face and voice; "
        "name must be supplied by that person, never guessed. They must be alone in the camera "
        "and have just spoken a phrase of at least 3 seconds. identify compares both modalities; "
        "only status=done with name confirms a match. Never infer identity just from appearance, "
        "configured user_name or a partial match. list shows enrolled names; forget deletes "
        "only the specifically requested person's local profile. replace only on explicit request. "
        "This is personalization, not authentication or proof of who is physically speaking."
    ),
    "brief": "Local face AND voice recognition: register by explicit consent, identify, list, forget. Needs a recent 3-second phrase and one visible face. Never guess identity.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["register", "identify", "list", "forget"]},
        "name": {"type": "STRING", "description": "Name explicitly supplied by the person for register/forget."},
        "replace": {"type": "BOOLEAN", "description": "Replace existing enrollment only if explicitly requested."},
    }, "required": ["action"]},
    "handler": person_identity,
}
