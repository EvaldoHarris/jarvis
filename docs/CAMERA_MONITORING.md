# Monitoramento de câmeras por grupos

Abra **Configuração → MONITORAMENTO DE CÂMERAS**. Crie um grupo (por exemplo,
Sítio ou Casa), marque as câmeras e salve. Repita para criar outros grupos.
**INICIAR GRUPO** começa a observação; **PARAR GRUPO** encerra apenas o escolhido;
**PARAR TODOS** encerra todos os grupos. Fechar o painel mantém o monitoramento.
Fechar o Jarvis encerra as conexões. Ao reabrir, os grupos continuam salvos,
mas precisam ser iniciados novamente.

Também é possível dizer “inicie o monitoramento do grupo Sítio”, “pare o grupo
Casa”, “como está o monitoramento?” ou “pare todos os monitoramentos”.

Até três grupos podem operar simultaneamente, com câmeras diferentes. A mesma
câmera não pode pertencer a dois grupos ativos ao mesmo tempo. Uma câmera sem
credenciais aparece identificada na lista e é pulada ao iniciar; configure sua
senha em **Config. de plugins → Câmeras**. O grupo não inicia se nenhuma das
câmeras selecionadas estiver configurada.

## Como funciona

### Imagens dos alertas

Uma detecção confirmada pelo detector local abre um alerta visual sem esperar a
análise da IA. O conector mantém até cinco segundos anteriores em memória,
amostrados a dois quadros por segundo e limitados a 8 MB por câmera conectada.
O alerta reproduz esse trecho e acompanha novas imagens por até 60 segundos;
não inclui áudio e não é uma gravação MP4. O rodízio pode aguardar mais 65
segundos após uma detecção para manter a câmera transmitindo durante o aviso.
Ao iniciar uma conexão ou acordar uma câmera solar, o trecho anterior pode ser
menor ou inexistente. O buffer contínuo é descartado ao desconectar. Os trechos
dos alertas são salvos no PC por até 24 horas em `data/monitor_recordings`, com
limite total de 1 GB e 50 MB por evento. A limpeza roda ao abrir a lista ou
salvar um alerta; remove os mais antigos primeiro. Fechar a janela preserva a
gravação. Use **GRAVAÇÕES DOS ALERTAS · 24 HORAS** no painel para reabrir.
O Android mantém os trechos recebidos no armazenamento privado do aplicativo
por até 24 horas, limitado a 200 MB e 50 MB por evento. Em **Casa**, abra
**GRAVAÇÕES DOS ALERTAS — 24 HORAS**. O celular só guarda o que recebeu enquanto
estava conectado; não sincroniza automaticamente os arquivos antigos do PC.

Se a verificação de presença pela webcam estiver habilitada nas configurações
de voz, ela decide o destino. Caso contrário, o PC desbloqueado com atividade
de teclado/mouse nos últimos dois minutos é considerado em uso. Isso é uma
aproximação de presença. Sem presença confirmada, o alerta vai ao Android
escolhido nas configurações de voz ou ao único Android conectado e compatível.
É necessário atualizar o aplicativo e manter a conexão autenticada com o PC
ativa, inclusive por acesso remoto já configurado quando estiver fora da rede.
Não há entrega push para um celular desconectado; nessa situação o aviso fica
no PC e a falha aparece no log. Notificações precisam estar permitidas no Android.
O botão da notificação abre as imagens recebidas. A reprodução é limitada a
dois quadros por segundo. No PC e Android, use pausa/reprodução, voltar ou
avançar cinco segundos e a barra de tempo. **ÚLTIMA IMAGEM** retoma o
acompanhamento do quadro mais recente. Pausar a reprodução mantém a captura.

Use **ACOMPANHAR MONITORAMENTO** no painel para selecionar um grupo e ver a
imagem atual do rodízio, o estado da conexão, os contadores e os últimos alertas.
A janela aproveita a conexão existente, sem iniciar outra sessão na câmera.
Imagens com mais de três segundos são ocultadas para evitar mostrar uma imagem
antiga como atual. Fechar o acompanhamento mantém os grupos funcionando.

Cada grupo observa uma câmera por vez em rodízio. O padrão é 30 segundos por
câmera após receber o primeiro quadro, analisando localmente um quadro a cada
1,5 segundo. A conexão inicial também leva tempo. Se houver apenas uma câmera,
a conexão permanece nela. Uma câmera indisponível não bloqueia as demais e é
revisitada após uma pausa crescente de 2 a 15 minutos. Não há garantia de
cobertura de todos os instantes; um evento durante a visita a outra câmera pode
não ser visto. Abrir várias câmeras iCSee no app/VMS/HUD pode disputar as sessões
P2P conforme o equipamento. Iniciar um grupo fecha a prévia atual do HUD, e
as câmeras dos grupos ativos ficam reservadas: pare o grupo antes de abrir uma
segunda conexão de prévia/análise manual pelo Jarvis.

O detector local YOLOX procura pessoas, carros, motos, ônibus e caminhões.
Veículos precisam aparecer em dois quadros amostrados antes de gerar evento.
Para pessoas, o padrão usa confiança mínima de 0,70, exige diferença de pelo
menos 0,12 em relação à segunda classe prevista e descarta regiões minúsculas
ou quase fora da imagem. A região precisa ser consistente em três observações
consecutivas e depois passar pela confirmação do evento: normalmente quatro
quadros, cerca de 4,5 segundos no intervalo padrão. Falhas e mudanças de câmera
reiniciam a confirmação. Isso reduz alertas transitórios, mas pode deixar de
avisar pessoas muito distantes ou que apareçam brevemente. Em **AJUSTES DO
MONITORAMENTO**, ajuste **Confiança mínima para pessoas** separadamente dos
veículos. Salve e reinicie o grupo para aplicar. Objetos persistentemente
confundidos pelo modelo ainda podem gerar falsos positivos; esses filtros
não garantem eliminar todos os erros e precisam de avaliação nas câmeras reais.
Depois, o evento passa à IA configurada do Jarvis para descrever aquela imagem,
e o aviso entra na fila de voz sem interromper a fala atual. Se a IA falhar,
o aviso informa que existe somente uma indicação do detector local.

O intervalo padrão entre avisos da mesma classe/câmera é 180 segundos. Um objeto
que continua presente não gera avisos repetidos a cada intervalo: são necessárias
observações de ausência por pelo menos 10 segundos para uma nova ocorrência.
Isso não distingue indivíduos ou veículos diferentes que apareçam sem intervalo.
Não há reconhecimento de identidade, conclusão de furto ou inferência de intenção.

As filas são limitadas e uma sobrecarga pode descartar eventos, contabilizados
em `status`. Cada grupo guarda até 15 descrições de eventos em memória. Não são
gravadas imagens contínuas em disco; apenas os trechos dos alertas são retidos
pelos limites descritos acima. As imagens dos eventos
são enviadas ao provedor de IA configurado; os demais quadros ficam locais.
Mensagens de aviso podem aparecer no registro normal de atividade do Jarvis.

## Ajustes e estado

O painel permite ajustar tempo por câmera, intervalo de amostragem, confiança
mínima e intervalo de avisos. Alterações em um grupo ativo só entram em vigor
após pará-lo e iniciá-lo novamente. O estado mostra a câmera atual, quantidade
de quadros verificados, avisos, último evento e problemas de conexão. “Iniciando”
não significa que imagens já foram recebidas; “observando” indica quadros sendo
processados. Em `status`, também estão as falhas de análise/conexão e descartes.

Os grupos ficam em `config/camera_monitor.json`, ignorado pelo Git, contendo
somente referências às câmeras e parâmetros. As credenciais continuam na
configuração local de câmeras. Para iCSee, mantenha o Docker aberto.

## Detector

O modelo foi preparado nesta instalação. Em outra instalação:

```powershell
.venv\Scripts\python.exe scripts/prepare_security_monitor.py
```

São cerca de 36 MB, obtidos do repositório oficial OpenCV Zoo com SHA-256 fixado.
Usa OpenCV/NumPy já existentes no projeto; não exige instalar PyTorch.
Fonte e licença Apache 2.0: [OpenCV Zoo YOLOX](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox).
Testes com uma imagem de referência detectaram duas pessoas, mas iluminação,
distância, oclusão e câmera noturna afetam a detecção no local real.
