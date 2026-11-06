"""Resumo do dia: junta o que o Jarvis já sabe em um texto curto.

Fontes (cada uma é opcional; se falhar, fica de fora sem travar o resumo):
  - notificações importantes e as que você não viu (core/alerts.py + central do Windows)
  - agenda do Google, se a conta estiver conectada
  - lembretes agendados pelo Jarvis para hoje
  - o que os agentes de programação fizeram nas últimas 24 h
  - saúde do PC (memória, disco)
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _notifications() -> tuple[list[str], list[str]]:
    """(importantes, outras) — da central do Windows e do que chegou com o Jarvis aberto."""
    from core import alerts
    seen, important, other = set(), [], []

    def add(n, imp):
        key = (n.get("app"), n.get("title"), n.get("text", "")[:80])
        if key in seen:
            return
        seen.add(key)
        line = f"{n.get('app')}: {n.get('title')} — {n.get('text', '').replace(chr(10), ' ')[:160]}"
        (important if imp else other).append(line)

    cfg = alerts.load()
    try:
        current = asyncio.run(alerts.NotificationWatcher()._read())
    except Exception:
        current = []
    for n in current:
        imp, why = alerts.classify(n, cfg)
        if why != "app silenciado":
            add(n, imp)
    with alerts._lock:
        kept = list(alerts._missed)
    for n in kept:
        if n.get("reason") != "app silenciado":
            add(n, n.get("important"))
    return important, other


def _calendar(day_offset: int = 0) -> list[str] | None:
    from core import google_workspace as g
    if not g.status().get("token_saved"):
        return None
    local = datetime.now().astimezone()
    start = (local + timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
    if day_offset == 0:
        start = local
    end = start.replace(hour=23, minute=59, second=59)
    rows = []
    for e in g.list_events(start.isoformat(), end.isoformat(), 15).get("events", []):
        when = (e.get("start") or {}).get("dateTime", "")[11:16] or "dia todo"
        rows.append({"text": f"{when} {e.get('title', '')}", "link": e.get("link", "")})
    return rows


def _reminders() -> list[str]:
    folder = Path.home() / ".jarvis" / "reminders"
    today = datetime.now().strftime("%Y%m%d")
    rows = []
    for f in sorted(folder.glob(f"JARVISReminder_{today}_*.py")):
        m = re.search(r"_(\d{8})_(\d{2})(\d{2})", f.stem)
        when = f"{m.group(2)}:{m.group(3)}" if m else ""
        if m and datetime.strptime(f"{m.group(1)}{m.group(2)}{m.group(3)}", "%Y%m%d%H%M") < datetime.now():
            continue
        msg = re.search(r"^message = (\".*\")$", f.read_text(encoding="utf-8", errors="replace"), re.M)
        rows.append(f"{when} {json.loads(msg.group(1)) if msg else ''}".strip())
    return rows


def _coding_agents() -> list[str]:
    root = Path.home() / "Desktop" / "JarvisProjects"
    cutoff = time.time() - 24 * 3600
    rows = []
    for log in root.glob("*/.jarvis-agent.log"):
        if log.stat().st_mtime < cutoff:
            continue
        text = log.read_text(encoding="utf-8", errors="replace")
        last = text.strip().split("-" * 60)[-2 if text.strip().endswith("-" * 60) else -1].strip()
        head = last.splitlines()[0] if last else ""
        summary = last.split("Resumo:", 1)[-1].split("Arquivos alterados:", 1)[0].strip()
        rows.append(f"{log.parent.name}: {head} — {summary[:200]}")
    return rows


def _pc_health() -> list[str]:
    import psutil
    rows = []
    mem = psutil.virtual_memory().percent
    if mem >= 85:
        rows.append(f"memória em {mem:.0f}%")
    for part in psutil.disk_partitions():
        try:
            use = psutil.disk_usage(part.mountpoint)
        except Exception:
            continue
        if use.percent >= 90:
            rows.append(f"disco {part.device} com {use.percent:.0f}% ocupado ({use.free // 2**30} GB livres)")
    return rows


def _image(url: str) -> bytes | None:
    """Miniatura da notícia: só http(s), até 400 KB, 4 s."""
    if not url.startswith(("http://", "https://")):
        return None
    try:
        import httpx
        with httpx.stream("GET", url, timeout=4, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"}) as r:
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                return None
            data = b""
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > 400_000:
                    return None
            return data
    except Exception:
        return None


def _og_image(page: str) -> str:
    """Imagem de capa declarada pela própria matéria (og:image)."""
    try:
        import httpx
        r = httpx.get(page, timeout=4, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)',
                      r.text[:200_000], re.I) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)', r.text[:200_000], re.I)
        return m.group(1).replace("&amp;", "&") if m else ""
    except Exception:
        return ""


def news(queries=("notícias hoje", "Brasil"), count: int = 6) -> list[dict]:
    """Notícias com link, fonte e imagem (baixada em paralelo)."""
    from concurrent.futures import ThreadPoolExecutor
    from actions.web_search import _get_ddgs
    rows, seen = [], set()
    with _get_ddgs()() as ddgs:
        for q in queries:
            try:
                found = ddgs.news(q, region="br-pt", max_results=count)
            except Exception as exc:
                print(f"[Brief] news '{q}': {exc}")
                continue
            for r in found:
                key = re.sub(r"\W+", "", (r.get("title") or "").lower())[:60]
                if r.get("url") and key and key not in seen:
                    seen.add(key)
                    rows.append({"title": r["title"], "url": r["url"], "source": r.get("source", ""),
                                 "snippet": r.get("body", ""), "date": r.get("date", ""),
                                 "image_url": r.get("image", "")})
    rows = rows[:count]

    def picture(row):
        return _image(row["image_url"]) or _image(_og_image(row["url"]))

    with ThreadPoolExecutor(6) as pool:
        for row, img in zip(rows, pool.map(picture, rows)):
            row["image"] = img
    return rows


def _section(title: str, icon: str, fn) -> dict | None:
    try:
        rows = fn()
    except Exception as exc:
        print(f"[Brief] {title}: {exc}")
        return None
    if rows is None:
        return None
    return {"title": title, "icon": icon, "items": [r if isinstance(r, dict) else {"text": r} for r in rows]}


def build_data(kind: str = "morning", with_news: bool = True) -> dict:
    """Resumo estruturado para o painel. kind = morning | evening."""
    sections = []
    agenda = (_section("Agenda de amanhã", "📅", lambda: _calendar(1)) if kind == "evening"
              else _section("Agenda de hoje", "📅", lambda: _calendar(0)))
    for s in (agenda, _section("Lembretes de hoje", "⏰", _reminders)):
        if s:
            sections.append(s)
    try:
        important, other = _notifications()
        sections.append({"title": "Notificações importantes", "icon": "🔔", "important": True,
                         "items": [_note_item(r) for r in important[:12]]})
        if other:
            sections.append({"title": f"Outras notificações ({len(other)})", "icon": "📨",
                             "items": [_note_item(r) for r in other[:8]]})
    except Exception as exc:
        print(f"[Brief] notificações: {exc}")
    for s in (_section("Agentes de programação (24 h)", "🤖", _coding_agent_items),
              _section("Saúde do PC", "🖥", _pc_health)):
        if s:
            sections.append(s)
    data = {"title": "Resumo do fim do dia" if kind == "evening" else "Resumo do dia",
            "when": datetime.now().strftime("%d/%m %H:%M"), "sections": sections, "news": []}
    if with_news:
        try:
            data["news"] = news()
        except Exception as exc:
            print(f"[Brief] notícias: {exc}")
    return data


def _note_item(line: str) -> dict:
    app, _, rest = line.partition(": ")
    title, _, text = rest.partition(" — ")
    return {"app": app, "text": title, "sub": text}


def _coding_agent_items() -> list[dict]:
    root = Path.home() / "Desktop" / "JarvisProjects"
    items = []
    for row in _coding_agents():
        name = row.split(":", 1)[0]
        items.append({"text": row, "link": (root / name).as_uri()})
    return items


def as_text(data: dict) -> str:
    """Versão em texto, para o modelo ler e falar os destaques."""
    out = [f"{data['title']} — {data['when']}"]
    for s in data["sections"]:
        rows = [f"- {(i.get('app') + ': ') if i.get('app') else ''}{i.get('text', '')}"
                f"{(' — ' + i['sub'][:160]) if i.get('sub') else ''}" for i in s["items"]]
        out.append(f"## {s['title']}\n" + ("\n".join(rows) or "- nada"))
    if data.get("news"):
        out.append("## Notícias\n" + "\n".join(f"- {n['title']} ({n['source']})" for n in data["news"]))
    return "\n\n".join(out)


def build(kind: str = "morning") -> str:
    return as_text(build_data(kind, with_news=False))
