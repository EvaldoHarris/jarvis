"""Read-only, incremental observation of local Claude/Codex session journals."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

CHUNK = 2 * 1024 * 1024
REPLY_LIMIT = 4000


def _clip(text):
    text = str(text or "").strip()
    return text if len(text) <= REPLY_LIMIT else text[:REPLY_LIMIT] + " [...]"


def _text_blocks(content):
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return "\n".join(b['text'] for b in content if isinstance(b, dict)
                     and b.get('type') == 'text' and isinstance(b.get('text'), str)).strip()


def classify(engine, record):
    """Return explicit journal evidence, never infer completion from inactivity."""
    if engine == "codex":
        payload = record.get("payload") or {}
        if not isinstance(payload, dict):
            return None
        if record.get("type") in ("session_meta", "turn_context"):
            return {"project": str(payload.get("cwd") or "")}
        if record.get("type") != "event_msg":
            return None
        kind = payload.get("type")
        states = {"task_started": "working", "task_complete": "completed",
                  "turn_aborted": "interrupted", "error": "error",
                  "approval_request": "needs_attention"}
        if kind in states:
            result = {"state": states[kind], "evidence": kind}
            if kind == "task_complete" and payload.get("last_agent_message"):
                result["reply"] = _clip(payload["last_agent_message"])
                if payload.get("turn_id") or record.get("timestamp"):
                    result["reply_id"] = str(payload.get("turn_id") or record.get("timestamp"))
                if record.get("timestamp"):
                    result["reply_at"] = str(record["timestamp"])
            return result
    else:
        if record.get("isSidechain"):
            return None
        kind = record.get("type")
        msg = record.get("message") or {}
        if not isinstance(msg, dict):
            return None
        result = {"project": str(record.get("cwd") or "")}
        if kind == "system" and record.get("subtype") == "api_error":
            result.update(state="error", evidence="api_error (may be retried)")
        elif kind == "user" and not record.get("toolUseResult") and not any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in (msg.get("content") if isinstance(msg.get("content"), list) else [])):
            result.update(state="working", evidence="user message")
        elif kind == "assistant":
            blocks = msg.get("content") or []
            if isinstance(blocks, list) and any(isinstance(b, dict) and b.get("type") == "tool_use"
                                               and b.get("name") == "AskUserQuestion" for b in blocks):
                result.update(state="needs_attention", evidence="AskUserQuestion")
            elif msg.get("stop_reason") == "end_turn":
                text = _text_blocks(blocks)
                # Claude writes separate thinking and text records with the same
                # message id and stop_reason. Thinking alone is not a readable reply.
                if text:
                    result.update(state="completed", evidence="end_turn", reply=_clip(text),
                                  reply_id=str(msg.get("id") or record.get("uuid") or ""),
                                  reply_at=str(record.get("timestamp") or ""))
            elif msg.get("stop_reason") == "tool_use":
                result.update(state="working", evidence="tool_use")
        return result
    return None


class SessionMonitor:
    def __init__(self, roots=None, clock=time.time):
        self.roots = roots if roots is not None else {
            "claude": Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "projects",
            "codex": Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions",
        }
        self.clock = clock
        self.files = {}
        self.initialized = False
        self.errors = []

    def poll(self):
        events = []
        self.errors = []
        candidates = []
        for engine, root in self.roots.items():
            if not root.is_dir():
                self.errors.append(f"{engine}: session directory unavailable")
                continue
            try:
                for path in root.rglob("*.jsonl"):
                    # Subagent journals are not separate user-facing sessions.
                    if "subagents" in path.relative_to(root).parts:
                        continue
                    stat = path.stat()
                    if self.clock() - stat.st_mtime < 86400:
                        candidates.append((stat.st_mtime, engine, path, stat))
            except OSError as exc:
                self.errors.append(f"{engine}: {type(exc).__name__}")
        for _, engine, path, stat in sorted(candidates, reverse=True)[:100]:
            key = str(path)
            fresh = key not in self.files
            row = self.files.setdefault(key, {"engine": engine, "session": path.stem,
                "project": "", "state": "unknown", "offset": 0, "pending": b"", "reply": "",
                "updated": stat.st_mtime})
            baseline = fresh and not self.initialized
            if stat.st_size < row["offset"]:
                row.update(offset=0, pending=b"", state="unknown", reply="", reply_id="", reply_at="")
                baseline = True
            try:
                with path.open("rb") as stream:
                    if baseline and stat.st_size > CHUNK:
                        stream.seek(stat.st_size - CHUNK)
                        stream.readline()  # tail starts in an arbitrary record
                    else:
                        stream.seek(row["offset"])
                    data = row["pending"] + stream.read(CHUNK)
                    row["offset"] = stream.tell()
                lines = data.split(b"\n")
                row["pending"] = lines.pop()
                if len(row["pending"]) > CHUNK * 4:
                    row["pending"] = b""  # bound a malformed/incomplete record
                terminal_changed = False
                final_reply_observed = False
                previous_reply = (row.get("reply_id"), row.get("reply"))
                for line in lines:
                    try:
                        record = json.loads(line)
                        if not isinstance(record, dict):
                            continue
                        change = classify(engine, record)
                    except (ValueError, TypeError, AttributeError):
                        continue
                    if change:
                        final_reply_observed |= bool(change.get("reply"))
                        if change.get("project"):
                            row["project"] = change["project"]
                        if "state" in change:
                            if change["state"] != row["state"]:
                                terminal_changed = change["state"] in (
                                    "completed", "error", "needs_attention", "interrupted")
                            # Keep the last readable final answer during later work
                            # or errors. Status indicates whether another turn is active.
                            row.update({k: v for k, v in change.items() if k != "project"})
                row["updated"] = stat.st_mtime
                # Only the final state of each batch is relevant; no historical replay.
                reply_changed = bool(row.get("reply")) and previous_reply != (row.get("reply_id"), row.get("reply"))
                if not baseline and (terminal_changed or reply_changed) and row["state"] in (
                        "completed", "error", "needs_attention", "interrupted"):
                    event = self.public(row)
                    if final_reply_observed and row["state"] == "completed":
                        event["reply"] = row["reply"]
                    events.append(event)
            except OSError as exc:
                self.errors.append(f"{engine}: {type(exc).__name__}")
        self.initialized = True
        live = {str(c[2]) for c in sorted(candidates, reverse=True)[:100]}
        self.files = {k: v for k, v in self.files.items() if k in live}
        return events

    @staticmethod
    def public(row):
        return {**{k: v for k, v in row.items() if k not in ("offset", "pending", "reply", "reply_id")},
                "reply_available": bool(row.get("reply"))}

    def snapshot(self):
        return [self.public(r) for r in sorted(self.files.values(), key=lambda r: r["updated"], reverse=True)]

    def read_reply(self, engine="", session="", project=""):
        """Return an explicitly selected session's last final answer, including baseline.

        Never silently choose another project's conversation just because it is newer.
        Metadata lists choices without exposing their answers.
        """
        rows = [r for r in self.files.values() if not engine or r["engine"] == engine]
        if session:
            rows = [r for r in rows if r["session"] == session]
        if project:
            wanted = project.replace('\\', '/').rstrip('/').casefold()
            rows = [r for r in rows if wanted in (r["project"].replace('\\', '/').rstrip('/').casefold(),
                    r["project"].replace('\\', '/').rstrip('/').rsplit('/', 1)[-1].casefold())]
        if not rows:
            return {"result": "not_found", "sessions": []}
        if len(rows) != 1:
            return {"result": "ambiguous", "sessions": [self.public(r) for r in rows]}
        row = rows[0]
        return {"result": "available" if row.get("reply") else "no_reply", **self.public(row),
                "reply": row.get("reply", ""), "scope": "last_recorded_final_reply"}
