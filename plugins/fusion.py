"""
Controle do Autodesk Fusion pelo JARVIS.

Requer o add-in fusion_addin/JarvisBridge instalado e rodando no Fusion
(copie a pasta para %APPDATA%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns e
ative em Shift+S → Add-Ins). O plugin pede ao modelo um script da API do Fusion
para o pedido do usuário e o executa no Fusion; se der erro, tenta corrigir uma vez.
Tudo o que o script faz pode ser desfeito com Ctrl+Z no Fusion.
"""

import json
import re
import socket

from core import gemini

HOST, PORT = "127.0.0.1", 27183

PLUGIN = {
    "name": "controlar_fusion",
    "description": (
        "Controla o Autodesk Fusion (Fusion 360): cria e modifica modelos 3D "
        "(esboços, extrusões, furos, filetes, componentes, parâmetros), consulta "
        "informações do projeto aberto (corpos, dimensões, volume, parâmetros) e "
        "exporta arquivos (STL, STEP). Use quando o usuário pedir algo no Fusion, "
        "CAD ou modelagem 3D. 'pedido' é a instrução completa em linguagem natural, "
        "com medidas e unidades."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "pedido": {"type": "STRING",
                       "description": "O que fazer no Fusion, com todos os detalhes e medidas."},
        },
        "required": ["pedido"],
    },
}

_PROMPT = """Você escreve scripts Python para a API do Autodesk Fusion.
O script roda DENTRO do Fusion com estas variáveis já definidas:
  adsk, app (adsk.core.Application), ui, design (adsk.fusion.Design ou None), root (design.rootComponent)
Regras:
- NÃO use run(context), NÃO importe adsk de novo, NÃO mostre messageBox.
- A API interna usa CENTÍMETROS: converta mm (÷10) e m (×100).
- Use adsk.core.ValueInput.createByReal / createByString e Point3D.create.
- Se design for None, defina result = "Nenhum design aberto no Fusion." e pare.
- Ao terminar, atribua a `result` uma frase curta em português dizendo o que foi feito
  ou a informação pedida.
- Para exportar, use design.exportManager e salve na pasta Documentos do usuário.
Responda SOMENTE com o código Python, sem explicações.

Pedido: {pedido}
"""


def _send(payload: dict, timeout: float = 130) -> dict:
    with socket.create_connection((HOST, PORT), timeout=timeout) as s:
        s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode("utf-8") or "{}")


def _code_from(txt: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", txt or "", re.S)
    return (m.group(1) if m else txt or "").strip()


def run(parameters: dict, player=None, session_memory=None) -> str:
    pedido = (parameters.get("pedido") or "").strip()
    if not pedido:
        return "O que o senhor quer que eu faça no Fusion?"

    try:
        _send({"ping": True}, timeout=3)
    except Exception:
        return ("Não consegui falar com o Fusion. Verifique se ele está aberto e se o "
                "add-in JarvisBridge está ativo em Shift+S → Add-Ins.")

    def log(msg):
        if player:
            try:
                player.write_log(msg)
            except Exception:
                pass

    prompt = _PROMPT.format(pedido=pedido)
    log("SYS: Fusion — gerando script…")
    for tentativa in range(2):
        code = _code_from(gemini.text(prompt, tier=gemini.SMART, timeout_ms=60_000))
        if not code:
            return "Não consegui gerar o script para o Fusion agora."
        try:
            resp = _send({"code": code})
        except Exception as e:
            return f"A conexão com o Fusion caiu: {e}"
        if resp.get("ok"):
            msg = resp.get("result") or "Feito no Fusion."
            if msg == "None":
                msg = "Feito no Fusion."
            log(f"JARVIS: {msg}")
            return msg
        erro = resp.get("result", "")
        log(f"SYS: Fusion — erro no script (tentativa {tentativa + 1}).")
        prompt = (_PROMPT.format(pedido=pedido)
                  + f"\n\nSua tentativa anterior:\n{code}\n\nFalhou com este erro:\n{erro}\n"
                  "Corrija e responda só com o código completo.")
    return f"O Fusion recusou o comando. Último erro: {erro.strip().splitlines()[-1] if erro else 'desconhecido'}"
