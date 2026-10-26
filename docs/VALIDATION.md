# Validacao conjunta do Jarvis

Implementacao pronta para verificacao do uso real. Primeiro reabra o Jarvis
do PC e instale o APK Android 0.5.0. Preserve o pareamento/configuracoes; nao
limpe dados do aplicativo. A conexao Google depende da configuracao em
[GOOGLE_SETUP.md](GOOGLE_SETUP.md).

Os testes tecnicos ja cobrem os componentes. A sequencia abaixo valida como
voz, modelo, ferramentas e seus aplicativos reais trabalham juntos.

| Fluxo | Pedido/acao | Resultado a conferir |
|---|---|---|
| Voz Android | "Jarvis", aguardar sinal e dizer uma frase | Sinal de pronto, transcricao e resposta pelo celular |
| Rotina PC | "Comecar meu trabalho" | Discord, VS Code e Chrome confirmados, plano 3/3 |
| Progresso | Abrir TAREFAS E PROGRESSO durante uma tarefa | Objetivo, etapa e motivo de bloqueio correspondem ao que ocorreu |
| Pausa | Pausar/interromper durante a tarefa | Nao executar as etapas seguintes; acao ja enviada pode terminar |
| Retomada | Continuar a tarefa pausada | Conferir aplicativos e preservar etapas concluidas |
| Cancelamento | Cancelar tarefa | Plano cancelado; nao afirmar que desfez acoes anteriores |
| Navegador | Abrir um resultado pelo nome observado | Destino correto, sem inventar seletor ou concluir apenas a busca |
| Datas | Google Travel, 19 a 29/12/2026 | Aplicar e conferir ambos os campos |
| Alvo repetido | "Mouse sobre Ver precos do Hotel [nome]" | Alvo do hotel correto; recusar ambiguidade |
| Monitores | "Coloque VS Code a esquerda do monitor [ID observado]" | Janela correta, monitor correto e limites conferidos |
| Documentos | Buscar orcamentos em uma pasta escolhida | Arquivos relevantes, paginas/linhas citadas, sem busca silenciosamente completa |
| OCR | Ler um PDF digitalizado de teste | Transcricao local; conferir precos/datas contra a imagem |
| Comparacao | Comparar dois documentos e salvar CSV/XLSX novo | Rotulos/valores/fontes preservados, arquivo reaberto/conferido |
| XLSX | Alterar celulas e salvar nova versao | Original intacto; copia com valores certos, sem alegar recalculo de formulas |
| Google leitura | Listar emails nao lidos e proximos compromissos | Dados reais da conta autorizada, sem alterar mensagens |
| Google escrita | Preparar mensagem para seu proprio email ou evento de teste | Previa no PC; so enviar/criar apos confirmar; nao repetir escrita incerta |
| Android conectado | ACOMPANHAR TAREFAS DO PC | Progresso e controles usando o pareamento existente |
| Android sem PC | Usar funcoes locais com o PC desligado | Assistente local continua independente; painel de tarefas mostra desconexao |

Em cada falha, registrar pedido exato, resposta, etapa/estado, horario e a
evidencia observada. Nao atribuir a causa a animacao, DOM, DPI ou cota sem o
resultado tecnico correspondente. Nao testar exclusao de arquivos nem envio
a terceiros para validar simples cliques.
