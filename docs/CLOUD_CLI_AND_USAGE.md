# CLIs de hospedagem e uso dos agentes

Reinicie o Jarvis após atualizar o código. A ferramenta `cloud_cli` é descoberta
automaticamente em `actions/`, sem cadastrar chaves no Jarvis.

## Railway e Netlify

O Jarvis utiliza os CLIs instalados e suas sessões locais. Se faltarem:

```powershell
npm install -g @railway/cli
npm install -g netlify-cli
```

Exemplos de pedidos:

- “Jarvis, conecte ao Railway.” Abre o login no navegador, se necessário.
- “Liste meus projetos no Netlify.”
- “Vincule esta pasta ao projeto [ID] do Railway.” Informe a pasta do projeto.
- “Veja o status e os últimos logs do serviço backend no Railway nesta pasta.”
- “Publique a pasta dist deste projeto como preview no site [ID] do Netlify.”
- “Publique em produção no Netlify.” Informe site, pasta do projeto e saída do build.

Operações: `available`, `login`, `projects`, `status`, `link`, `deploy`;
Railway também oferece `logs` (últimas 100 linhas) e `deployments`.
O Netlify recebe arquivos já compilados: o Jarvis não executa um build implícito.
Deploys exigem confirmação no painel com pasta e argumentos visíveis.
O aceite do CLI não comprova que a aplicação está saudável; consulte o deploy.

Referências: [Railway CLI](https://docs.railway.com/cli),
[Netlify deploy](https://cli.netlify.com/commands/deploy/).

## Uso restante no painel desktop

Na coluna de telemetria, `IA · USO RESTANTE` mostra os percentuais restantes
do Claude e Codex por janela (normalmente 5 horas e 7 dias). Passe o mouse
para ver os horários de renovação e a última leitura, no fuso local do PC.
Percentuais representam a cota da assinatura, não um número de mensagens.
Ausência de dados aparece como “Indisponível”; leituras antigas são sinalizadas,
e uma janela vencida aparece como `--`, sem presumir uma renovação de 100%.

- **Codex:** consulta `account/rateLimits/read` pelo `codex app-server`, com o
  login ChatGPT já existente. Atualiza a cada dois minutos em segundo plano,
  sem criar conversas ou enviar prompts. Contas com API key podem não fornecer
  cotas de assinatura.
- **Claude:** a consulta usa o login local do Claude Code, sem precisar abrir
  uma nova conversa. Funciona também quando a sessão está no painel do VS Code,
  que pode não executar a `statusLine`. **ATUALIZAR CLAUDE** solicita uma nova
  verificação em segundo plano. As consultas da conta têm intervalo mínimo de
  cinco minutos; respostas 429 ampliam a espera. O Jarvis não renova nem altera
  os tokens: se o login expirar, abra o Claude Code ou use `claude auth login`.
  A consulta da conta usa um endpoint interno do Claude, sem contrato de API
  pública estável; falhas aparecem no tooltip sem inventar percentuais.
- A `statusLine` oficial continua sendo uma fonte preferencial quando fornece
  dados recentes. Seu adaptador é opcional e preserva a linha de status anterior.

Para configurar o adaptador opcional do terminal:

```powershell
.venv/Scripts/python.exe scripts/claude_usage_statusline.py --install
```

Ambas as fontes gravam somente percentuais, horários de renovação e da leitura em
`~/.claude/jarvis-usage.json` (ou em `CLAUDE_CONFIG_DIR`). Não copia credenciais
ou conversas. O token de acesso local só é enviado por HTTPS ao domínio
`api.anthropic.com`, sem seguir redirecionamentos, e não é exposto na interface,
nos logs ou no cache. Para retirar o adaptador, restaure o backup
`settings.jarvis-backup-*.json` ou retire sua chamada do campo `statusLine` em
`settings.json`.

Referências: [Codex app-server](https://learn.chatgpt.com/docs/app-server),
[Claude statusLine](https://code.claude.com/docs/en/statusline).
