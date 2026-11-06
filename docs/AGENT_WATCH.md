# Acompanhar Claude Code e Codex

Com o Jarvis reiniciado, diga **“acompanhe o Claude e o Codex e me avise quando terminarem”**.
A ferramenta `agent_watch` aceita `start`, `status`, `read` e `stop`.

- “Como estão os agentes?” consulta as sessões recentes.
- “O que o Claude do projeto atendeai respondeu?” lê a última resposta final registrada.
- “Acompanhe e leia as próximas respostas do Claude” ativa os resumos por voz (`start`, `read_replies=true`).
- “Pare de acompanhar os agentes” encerra a observação sem encerrar Claude ou Codex.

O acompanhamento lê os arquivos locais `.claude/projects/**/*.jsonl` e
`.codex/sessions/**/*.jsonl`, incluindo sessões das extensões do VS Code que gravam
nesses diretórios. Respeita `CLAUDE_CONFIG_DIR` e `CODEX_HOME`. Não depende da aba
visível, não envia mensagens e não aprova ações dos agentes.

A cada cinco segundos, observa até 100 sessões alteradas nas últimas 24 horas.
O primeiro levantamento não anuncia eventos antigos. Por padrão, as notificações
usam apenas metadados de estado, sessão e pasta. Com `read_replies=true`, incluem
o texto da resposta final para um resumo por voz. Prompts, raciocínio interno e
saídas de comandos não entram nesse resumo. A lista inclui sessões recentes,
que podem já estar fechadas.

`read` consulta a resposta já existente, mesmo sem acompanhamento ativo. Use
`engine=claude|codex`, `project` com o caminho ou nome exato da pasta, ou `session`
com o identificador mostrado por `status`. Havendo várias conversas possíveis,
o Jarvis pede que você identifique uma delas. A resposta inclui o estado atual
e a data do texto quando disponível; uma resposta anterior continua consultável
enquanto o agente trabalha em outro turno. O texto é limitado a 4.000 caracteres.
`status` informa se há uma resposta disponível, sem incluir seu conteúdo.

O Claude pode registrar `end_turn` primeiro no bloco de raciocínio e só depois
no bloco de texto da mesma mensagem. O monitor espera o texto legível para
notificar a resposta; blocos internos não apagam a última resposta registrada.

Conclusão significa fim de um turno registrado, não comprovação de que o código
funciona. Erros de API podem ser seguidos de novas tentativas. Pedidos explícitos
`AskUserQuestion` do Claude e eventos reconhecidos de aprovação do Codex são
sinalizados; diálogos de permissão que não constem dos registros não são
detectados. Uma sessão silenciosa permanece no último estado observado.
Se a versão da extensão não registrar um evento reconhecido, seu estado pode
ficar desconhecido ou desatualizado. O acompanhamento precisa ser iniciado
novamente depois de fechar o Jarvis.

## Responder aos agentes por voz

Depois de reiniciar o Jarvis, use por exemplo:

- “Jarvis, peça ao Codex do atendeai para continuar.”
- “Jarvis, diga ao Claude do KBGen para rodar os testes.”
- “Jarvis, qual autorização o Claude está pedindo?”
- “Jarvis, autorize essa ação uma vez no Claude.”
- “Jarvis, recuse esse pedido no Codex.”

A ferramenta `agent_control` lista as janelas (`windows`), observa a conversa
(`inspect`) e recebe `continue`, `send`, `approve` ou `reject` com o
`observation_id` dessa observação. Se houver mais de uma janela possível,
o Jarvis deve identificar o projeto solicitado antes de agir.

A interação usa a janela existente do VS Code no Windows e a visão configurada
para controle de tela. Ela traz a janela à frente e pode selecionar a aba do
agente. Não abre outra sessão nem executa `resume` pela linha de comando.
O painel precisa estar legível, com a conversa identificável. Diferentemente
da leitura dos registros, essa interação usa capturas de tela no provedor de
visão configurado, como o controle de tela já existente no Jarvis.

A observação vale por 60 segundos e para uma única ação. Antes de agir, o
Jarvis relê a conversa e o pedido de permissão. Rascunhos existentes são
preservados, agentes ocupados não recebem mensagens enfileiradas e “continue”
não aceita uma permissão pendente. A aprovação se aplica somente ao pedido
observado e exige uma instrução explícita do usuário; não aceita opções
“sempre permitir” ou “permitir nesta sessão”. Alertas do monitor não autorizam
respostas por conta própria.

Depois de colar a instrução, a integração confere o texto antes de acionar o
botão de envio. Depois de enviar ou responder a uma permissão, verifica a
transição do painel. Um resultado incerto não é repetido automaticamente.
A validação automatizada usa interfaces simuladas e não envia instruções
reais às sessões de trabalho do usuário.
