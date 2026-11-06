# Valorant no Jarvis

Rank, RR, pico de rank e estatísticas das últimas partidas são consultados pela
[HenrikDev](https://docs.henrikdev.xyz/general/auth), um serviço independente e
não oficial da Riot Games. A chave Tracker.gg não funciona nesta integração.

1. Gere uma chave no [painel HenrikDev](https://api.henrikdev.xyz/dashboard/).
2. Reinicie o Jarvis para descobrir o novo plugin.
3. Abra **Configurações → Config. de plugins → VALORANT — HENRIKDEV**.
4. Preencha a chave, seu Riot ID completo (`Nome#TAG`), região (`br` no Brasil)
   e plataforma (`pc` ou `console`). Salve e use **TESTAR CONEXÃO**.

A chave fica no arquivo local `config/api_keys.json`, em
`plugin_config.valorant.api_key`, seguindo o armazenamento dos demais plugins.
O campo aparece mascarado; o arquivo não é criptografado e é ignorado pelo Git.
Não compartilhe esse arquivo nem envie a chave pelo chat.

Exemplos de pedidos:

- “Jarvis, qual é meu rank no Valorant?”
- “Mostre as estatísticas das minhas últimas cinco partidas de Valorant.”
- “Consulte o rank de Nome#TAG na região br.”

Use dados próprios ou de jogadores que autorizaram a consulta. O histórico é uma
amostra de até dez partidas, e não representa todas as partidas da conta.
Erros de autenticação, jogador não encontrado, indisponibilidade e limite de
requisições são apresentados sem repetir chamadas automaticamente.

Endpoints documentados utilizados: conta v2, MMR v3 e partidas v4, todos por HTTPS
em `api.henrikdev.xyz`, com a chave no cabeçalho `Authorization`.
