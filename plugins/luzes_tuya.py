"""
Controle das luzes da casa via Tuya / Smart Life (nuvem Tuya, biblioteca tinytuya).

Configuração (uma vez):
  1. Crie um projeto Cloud em https://iot.tuya.com  (Cloud → Development → Create
     Cloud Project, data center "Western America" para contas do Brasil).
  2. Em "Devices → Link App Account", escaneie o QR com o app Smart Life.
  3. Copie Access ID e Access Secret para ⚙ → CONFIG. DE PLUGINS → LUZES (TUYA).

Dependência: pip install tinytuya
"""

import unicodedata

from memory.config_manager import get_plugin_config

_NS = "luzes_tuya"

PLUGIN = {
    "name": "controlar_luzes",
    "description": (
        "Controla as luzes e lâmpadas inteligentes da casa (Tuya / Smart Life): "
        "ligar, desligar, alternar, ajustar brilho, listar as lâmpadas ou ver o "
        "estado delas. Use quando o usuário pedir para acender/apagar a luz de um "
        "cômodo, todas as luzes, ou mudar a intensidade. 'dispositivo' é o nome "
        "da lâmpada/cômodo como está no app (ex.: 'sala', 'quarto'), ou 'todas'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "acao": {
                "type": "STRING",
                "description": "ligar | desligar | alternar | brilho | listar | status",
            },
            "dispositivo": {
                "type": "STRING",
                "description": "Nome da lâmpada ou cômodo, ou 'todas'. Vazio para listar.",
            },
            "brilho": {
                "type": "INTEGER",
                "description": "Brilho em porcentagem (1–100), só para acao=brilho.",
            },
        },
        "required": ["acao"],
    },
}


def _test(values: dict):
    try:
        devs = _devices(_cloud(values))
        return True, f"Conectado — {len(devs)} dispositivo(s) encontrados."
    except Exception as e:
        return False, str(e)


PLUGIN_SETTINGS = {
    "namespace": _NS,
    "title": "LUZES (TUYA)",
    "fields": [
        {"key": "api_key", "label": "Access ID", "type": "text"},
        {"key": "api_secret", "label": "Access Secret", "type": "password"},
        {"key": "region", "label": "Região do data center", "type": "choice",
         "options": ["us", "eu", "cn", "in", "us-e", "eu-w"], "default": "us"},
    ],
    "action": {"label": "TESTAR CONEXÃO", "run": _test},
}


# ── helpers ──────────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _cloud(values: dict | None = None):
    import tinytuya
    cfg = values if values is not None else get_plugin_config(_NS)
    key, secret = (cfg.get("api_key") or "").strip(), (cfg.get("api_secret") or "").strip()
    if not key or not secret:
        raise RuntimeError("Tuya não configurada. Preencha Access ID e Secret em "
                           "⚙ → Config. de plugins.")
    c = tinytuya.Cloud(apiRegion=cfg.get("region") or "us",
                       apiKey=key, apiSecret=secret)
    if getattr(c, "error", None):
        raise RuntimeError(f"Falha ao autenticar na Tuya: {c.error}")
    return c


def _devices(c) -> list[dict]:
    devs = c.getdevices()
    if isinstance(devs, dict):          # error payload
        raise RuntimeError(devs.get("Payload") or devs.get("Error") or str(devs))
    return devs or []


def _status(c, dev_id: str) -> dict:
    r = c.getstatus(dev_id) or {}
    return {i["code"]: i["value"] for i in r.get("result", []) if "code" in i}


def _switch_code(st: dict) -> str | None:
    for code in ("switch_led", "switch_1", "switch", "led_switch"):
        if code in st:
            return code
    return next((k for k in st if k.startswith("switch")), None)


def _match(devs: list[dict], name: str) -> list[dict]:
    n = _norm(name)
    if n in ("", "todas", "todos", "tudo", "all", "todas as luzes", "casa"):
        return devs
    exact = [d for d in devs if _norm(d.get("name", "")) == n]
    if exact:
        return exact
    return [d for d in devs if n in _norm(d.get("name", ""))
            or _norm(d.get("name", "")) in n]


def _set(c, dev_id: str, code: str, value) -> bool:
    r = c.sendcommand(dev_id, {"commands": [{"code": code, "value": value}]}) or {}
    return bool(r.get("success"))


# ── entry point ──────────────────────────────────────────────────────────────
def run(parameters: dict, player=None, session_memory=None) -> str:
    acao = _norm(parameters.get("acao", ""))
    nome = parameters.get("dispositivo", "") or ""
    try:
        c = _cloud()
        devs = _devices(c)
    except ImportError:
        return "A biblioteca tinytuya não está instalada. Rode: pip install tinytuya"
    except Exception as e:
        return f"Não consegui acessar a Tuya: {e}"

    if not devs:
        return "Nenhum dispositivo encontrado na conta Tuya vinculada."

    if acao in ("listar", "lista"):
        nomes = ", ".join(d.get("name", "?") for d in devs)
        return f"Dispositivos disponíveis: {nomes}."

    alvo = _match(devs, nome)
    if not alvo:
        return (f"Não encontrei nenhuma lâmpada chamada '{nome}'. "
                f"Tenho: {', '.join(d.get('name', '?') for d in devs)}.")

    ok, falhou = [], []
    for d in alvo:
        did, dname = d["id"], d.get("name", d["id"])
        try:
            st = _status(c, did)
            if acao == "status":
                sw = _switch_code(st)
                estado = "ligada" if sw and st.get(sw) else "desligada"
                ok.append(f"{dname} {estado}")
                continue
            if acao == "brilho":
                pct = max(1, min(100, int(parameters.get("brilho") or 100)))
                if "bright_value_v2" in st:
                    code, val = "bright_value_v2", int(10 + (1000 - 10) * pct / 100)
                elif "bright_value" in st:
                    code, val = "bright_value", int(25 + (255 - 25) * pct / 100)
                else:
                    falhou.append(f"{dname} (sem ajuste de brilho)")
                    continue
                sw = _switch_code(st)
                if sw and not st.get(sw):
                    _set(c, did, sw, True)
                (ok if _set(c, did, code, val) else falhou).append(dname)
                continue
            sw = _switch_code(st)
            if not sw:
                falhou.append(f"{dname} (não é uma lâmpada/interruptor)")
                continue
            if acao in ("ligar", "acender", "on"):
                val = True
            elif acao in ("desligar", "apagar", "off"):
                val = False
            elif acao in ("alternar", "inverter", "toggle"):
                val = not st.get(sw)
            else:
                return f"Ação desconhecida: '{acao}'. Use ligar, desligar, alternar, brilho, listar ou status."
            (ok if _set(c, did, sw, val) else falhou).append(dname)
        except Exception as e:
            falhou.append(f"{dname} ({e})")

    if acao == "status":
        msg = "; ".join(ok) + "."
    else:
        verbo = {"ligar": "Liguei", "acender": "Liguei", "desligar": "Desliguei",
                 "apagar": "Desliguei", "brilho": "Ajustei o brilho de"}.get(acao, "Alternei")
        msg = f"{verbo}: {', '.join(ok)}." if ok else ""
    if falhou:
        msg += f" Falhou: {', '.join(falhou)}."
    msg = msg.strip() or "Nada foi alterado."
    if player:
        try:
            player.write_log(f"JARVIS: {msg}")
        except Exception:
            pass
    return msg
