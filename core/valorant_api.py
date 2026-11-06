"""Read-only Valorant queries through HenrikDev's documented API."""
from urllib.parse import quote

import requests

BASE_URL = "https://api.henrikdev.xyz/valorant"
REGIONS = ("br", "latam", "na", "eu", "ap", "kr")
PLATFORMS = ("pc", "console")


def identity(riot_id):
    name, sep, tag = str(riot_id or "").strip().rpartition("#")
    if not sep or not name.strip() or not tag.strip():
        raise ValueError("Informe o Riot ID completo, no formato Nome#TAG, nas configurações ou no pedido.")
    return name.strip(), tag.strip()


def query(values, action="rank", riot_id=None, region=None, platform=None, count=5):
    """Fetch once, without redirects or retries; never expose provider error bodies."""
    if action not in ("account", "rank", "matches"):
        raise ValueError("Consulta Valorant desconhecida.")
    key = str(values.get("api_key") or "").strip()
    if not key:
        raise ValueError("Adicione a chave HenrikDev em Configurações > Config. de plugins > Valorant.")
    name, tag = identity(riot_id or values.get("riot_id"))
    region = str(region or values.get("region") or "br").lower()
    platform = str(platform or values.get("platform") or "pc").lower()
    if region not in REGIONS or platform not in PLATFORMS:
        raise ValueError("Região ou plataforma Valorant inválida.")
    try:
        size = int(count)
    except (ValueError, TypeError):
        raise ValueError("Quantidade de partidas deve ser um inteiro entre 1 e 10.") from None
    if isinstance(count, bool) or size != count or not 1 <= size <= 10:
        raise ValueError("Quantidade de partidas deve ser um inteiro entre 1 e 10.")
    player = f"{quote(name, safe='')}/{quote(tag, safe='')}"
    paths = {
        "account": f"v2/account/{player}",
        "rank": f"v3/mmr/{region}/{platform}/{player}",
        "matches": f"v4/matches/{region}/{platform}/{player}",
    }
    try:
        response = requests.get(
            f"{BASE_URL}/{paths[action]}",
            headers={"Authorization": key, "Accept": "application/json"},
            params={"size": size} if action == "matches" else {},
            timeout=(5, 20), allow_redirects=False,
        )
    except requests.RequestException:
        raise ValueError("Não foi possível conectar à HenrikDev. Tente novamente mais tarde.") from None
    errors = {
        400: "Confira o Riot ID, região e plataforma informados.",
        401: "Chave HenrikDev inválida ou ausente. Confira as configurações.",
        403: "A HenrikDev recusou o acesso. Confira a chave e as permissões no painel do serviço.",
        404: "Jogador ou dados não encontrados. Confira o Riot ID, região e plataforma.",
        429: "Limite da HenrikDev atingido. Aguarde antes de consultar novamente.",
    }
    if response.status_code != 200:
        raise ValueError(errors.get(response.status_code, "HenrikDev indisponível ou resposta HTTP inesperada."))
    try:
        payload = response.json()
    except ValueError:
        raise ValueError("HenrikDev retornou uma resposta inválida.") from None
    if not isinstance(payload, dict) or payload.get("status") != 200 or "data" not in payload:
        raise ValueError("HenrikDev não confirmou os dados solicitados.")
    data = payload["data"]
    if action == "matches":
        if not isinstance(data, list):
            raise ValueError("Formato do histórico HenrikDev inesperado.")
        return [_match_summary(match, name, tag) for match in data[:size]]
    if not isinstance(data, dict) or not data:
        raise ValueError("Nenhum dado disponível para este jogador.")
    if action == "rank":
        return {key: data.get(key) for key in ("account", "current", "peak", "seasonal")}
    return {key: data.get(key) for key in ("name", "tag", "region", "account_level", "platforms", "updated_at")}


def _match_summary(match, name, tag):
    if not isinstance(match, dict):
        raise ValueError("Formato de partida HenrikDev inesperado.")
    metadata = match.get("metadata") or {}
    player = next((p for p in match.get("players", [])
                   if str(p.get("name", "")).casefold() == name.casefold()
                   and str(p.get("tag", "")).casefold() == tag.casefold()), None)
    team = next((t for t in match.get("teams", [])
                 if player and t.get("team_id") == player.get("team_id")), None)
    return {
        **{key: metadata.get(key) for key in ("match_id", "map", "queue", "started_at", "is_completed")},
        "player_found": player is not None,
        "agent": player.get("agent") if player else None,
        "stats": player.get("stats") if player else None,
        "team": team,
    }
