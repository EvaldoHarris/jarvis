# JARVIS para Android — Kotlin / Android Studio

Aplicativo nativo para **Android 11 ou superior**. Abre diretamente no
Android Studio pela pasta `android`. O aplicativo conversa com o Gemini pelo
próprio celular e não precisa do PC para suas funções locais. Requer internet e
uma chave de API com acesso/cota para o modelo configurado.

## Instalar e configurar

1. Instale o APK `JARVIS-Android-debug.apk` no celular. É uma compilação de teste,
   assinada com chave de desenvolvimento; ainda não é uma publicação na Play Store.
   Neste computador, o painel remoto também oferece **Ações → Baixar app Android**
   depois de parear o navegador. O download exige autenticação.
2. Abra JARVIS → **⚙**. Cadastre sua chave Gemini e o nome do modelo. O padrão é
   `gemini-2.5-flash`, alterável conforme os modelos disponíveis na sua conta.
3. Para visão e gestos, use **ATIVAR VISÃO E CONTROLE** e habilite o serviço JARVIS
   nas configurações de acessibilidade. Em algumas versões do Android, um APK
   instalado por arquivo exige permitir configurações restritas nos detalhes do app.
4. Na tela principal, escolha **Este Android — independente**, digite um pedido ou
   toque em **FALAR**. A permissão de microfone é solicitada ao usar a voz.

Em **⚙ → BUSCAR MODELOS DISPONÍVEIS**, consulte os modelos de conversa retornados
pela API para sua chave e escolha um antes de salvar. Um 404 indica modelo/recurso
indisponível, não comprova falta de cota. Se um modelo Flash retornar 404, o app
consulta a API e tenta até dois modelos Flash alternativos dessa lista; o modelo
que responder é salvo. Modelos Lite não são promovidos automaticamente para Flash
completo. Erros 429 não disparam troca de modelo nem repetição automática.

Em alta demanda temporária (503), o aplicativo aguarda aproximadamente 1 e 2 segundos
e faz no máximo duas novas tentativas no mesmo modelo. PARAR cancela também essa espera.
A recuperação não muda para um modelo mais caro e não altera a cota da conta.

A mensagem do Google é exibida com a chave ocultada, e cotas/preços continuam variando por modelo.

Não há chave de API embutida no APK. Configurações e credenciais locais são
criptografadas com chave do Android Keystore e o backup do aplicativo está desativado.
O reconhecimento de fala é o serviço instalado no Android, que pode usar a nuvem
conforme o aparelho. A leitura das respostas usa a voz Gemini, sem substituição
pelo leitor de voz do Android. Para respostas independentes, o app abre uma sessão
Gemini Live com a voz e o modelo de áudio sincronizados do PC; o padrão é Charon.
O acesso e a cota da API Live são separados dos modelos de texto. Nos pedidos ao PC,
o celular recebe os próprios bytes de áudio produzidos pelo computador.

## Escuta por palavra e conversa contínua

Com a permissão de microfone concedida, a opção padrão é **Dizer Jarvis**.
Abra o aplicativo para iniciar o serviço visível de microfone e diga
**“Jarvis, que horas são?”**, ou diga **“Jarvis”** e o pedido nos próximos dez segundos.
No botão **ESCUTA: JARVIS / CONTÍNUA / DESLIGADA**, escolha se quer palavra de
ativação, enviar cada frase sem palavra de ativação ou usar somente FALAR.
PARAR e a ação **Parar escuta** da notificação desligam o modo automático.

O serviço usa o reconhecimento de fala do Android para detectar a palavra; ele
não é um detector local de palavra de ativação. Dependendo do serviço instalado,
esse reconhecimento pode enviar áudio à nuvem mesmo antes de detectar “Jarvis”.
A escuta pausa durante o processamento e a reprodução das respostas para evitar
captar a própria voz. É retomada após terminar. O serviço pode continuar em segundo
plano depois de iniciado com o app visível, mas não se inicia por boot e continua
sujeito às restrições de bateria/microfone do Android. Não há escuta oculta.

O reator fica fixo acima da área rolável da conversa, inclusive ao consultar o histórico.

## Visão e controle

- **NAVEGADOR** abre o navegador integrado do celular. Peça por voz ou texto,
  por exemplo: “Pesquise hotéis em Ubatuba”, “Clique no Golden Garden”,
  “Preencha o destino com Ubatuba” ou “Role a página”. O agente recebe o DOM
  visível e uma captura após navegar, clicar ou preencher, na mesma sessão.
  Textos ambíguos são recusados; ele pode usar o ID observado para desambiguar.
  O navegador é um WebView Android; Playwright continua sendo usado no PC.
  Não há acesso ao perfil, senhas ou cookies do Chrome instalado no telefone.
  Login e CAPTCHA podem exigir intervenção pessoal.
- **CÂMERA** abre a câmera do Android; depois de tirar uma foto, digite a pergunta
  e toque em **ENVIAR**. Nesta versão a análise é por foto, não vídeo contínuo.
- **VER TELA** explica como usar o reator flutuante. Abra o aplicativo desejado e
  toque nesse reator: ele captura a tela antes de abrir o JARVIS. Você confirma o
  envio da imagem tocando em **ENVIAR**. Segurar o reator abre o assistente.
- O assistente pode observar a tela/textos acessíveis, abrir aplicativos, tocar,
  rolar, preencher o campo selecionado e usar Voltar/Início para cumprir pedidos.
  Também pode listar aplicativos, abrir Recentes/Notificações e manter um toque
  longo. A leitura inclui IDs de recurso, limites e propriedades dos controles.
  Depois das ações, o agente recebe uma nova leitura da janela para conferir o
  resultado. Um texto ou ID precisa identificar um único controle.
- As ações dependem de acessibilidade ativa, das restrições do Android e do app
  controlado. Telas protegidas podem impedir captura; bloqueio de tela e permissões
  do sistema não são contornados. Gesto concluído não prova que a tarefa terminou.
- **PARAR** interrompe o pedido e a fala; ações que já ocorreram não são desfeitas.

Texto, fotos e capturas usados na análise são enviados à API Gemini configurada.
Não há análise facial de identidade, root, ADB no celular do usuário ou acesso
oculto. O histórico da conversa fica na memória do processo e pode desaparecer
ao fechar o aplicativo; as memórias, tarefas e documentos da biblioteca são
persistentes e criptografados. O vídeo RTSP é reproduzido localmente; a IA recebe
um quadro quando o usuário solicita sua análise, sem acompanhamento contínuo automático.

## Parear PC e celular

1. Execute a versão atualizada do Jarvis no PC e abra **CONTROLE REMOTO** para
   gerar uma chave de oito caracteres.
2. No Android → **⚙**, informe o endereço do PC, por exemplo
   `http://192.168.15.13:8000`, e digite a chave. Toque em **Parear PC**.
3. Ative **Permitir controle deste celular pelo PC** na tela principal. O Android
   mantém uma notificação com a opção **Desconectar** enquanto essa ligação está ativa.
4. Escolha **Computador pareado** para enviar comandos do celular ao PC; as
   respostas do PC aparecem na conversa quando ele as emitir. Envio aceito não
   significa ação executada. O assistente do PC precisa estar ligado e operacional.
5. No PC, diga por exemplo **“Liste os celulares conectados”**, **“Abra o WhatsApp
   no celular”** ou **“Veja a tela do Android”**. O plugin `android_control` é usado
   para o telefone; os comandos do computador continuam usando suas ferramentas.

As respostas aos pedidos enviados pelo Android ao PC retornam ao aparelho e são
reproduzidas com o áudio original do PC. Não é necessário ativar o alto-falante do painel web.
Ao usar FALAR, a leitura das respostas é ativada automaticamente. O reconhecedor
é reutilizado entre falas; se o serviço Android desconectar (erro 11), há uma
tentativa de recuperação e depois a alternativa de reconhecimento do sistema.

O pareamento é lembrado após reiniciar. Se o PC ficar offline, o Android tenta
reconectar e continua disponível como assistente local. Pedidos de controle não
são guardados para execução posterior e não são repetidos automaticamente.
Se houver mais de um celular, escolha o ID retornado pela lista do PC.

## Fora de casa

Use uma **VPN privada entre os dois dispositivos**, por exemplo Tailscale:

1. Instale Tailscale no Windows e no Android e entre na mesma rede privada
   (tailnet). Isso exige sua conta e configuração nesses aparelhos; o JARVIS não
   instala nem autentica uma VPN automaticamente.
2. Use nas configurações do JARVIS Android o IP VPN do PC, normalmente
   `http://100.x.y.z:8000`. O tráfego HTTP fica dentro do túnel criptografado da VPN.
3. Deixe a VPN conectada nos dois lados e permita o serviço na rede privada do
   firewall do Windows, caso ele solicite. Não abra a porta 8000 no roteador.
4. Faça o pareamento usando esse endereço. Mudar o endereço do PC limpa o
   pareamento no aplicativo para evitar reutilizar credenciais em outro servidor.

Também é aceito um endereço HTTPS com certificado válido; o app não ignora erros
de certificado. HTTP aberto em IP público é recusado. Uma VPN não liga um PC
desligado. Fora de casa ainda precisa ser validado com sua conta e seu celular.

Referências: [Tailscale em dispositivos pessoais](https://tailscale.com/docs/use-cases/personal-or-at-home-use/access-nas-media-file-servers?tab=android),
[acessibilidade Android](https://developer.android.com/reference/android/accessibilityservice/AccessibilityService),
[ferramentas Gemini](https://ai.google.dev/gemini-api/docs/function-calling).

## Compilar no Android Studio

Abra esta pasta como projeto. Use o JDK integrado do Android Studio (17 ou
superior), Android SDK 35 e sincronize o Gradle. `local.properties` é gerado pelo
Android Studio e não faz parte do repositório.

```powershell
.\gradlew.bat assembleDebug testDebugUnitTest lintDebug
```

No Linux/macOS: `./gradlew assembleDebug testDebugUnitTest lintDebug`.
O APK fica em `app/build/outputs/apk/debug/app-debug.apk`.

Há testes unitários de endereço/limites de rede e testes instrumentados de
Keystore, captura/acessibilidade e agente com HTTP simulado. O teste instrumentado
de pareamento com PC só é executado quando recebe o argumento `pcPin` apontando
para um servidor de teste em `10.0.2.2:8771`; não use esse endereço no celular real.

## Estado da validação

Compilação, testes unitários e lint concluídos; integração bidirecional testada
em emulador com servidor PC isolado. O teste de IA usou provedor simulado, sem
consumir sua chave/cota. Voz, câmera física, aplicativos de terceiros e conexão
por internet/VPN precisam ser conferidos no aparelho real. O Android/fabricante
pode encerrar serviços em segundo plano; essa versão não promete execução 24h.

O aplicativo faz parte do mesmo projeto e mantém a licença da raiz do repositório.

## 0.4.3 — reconhecimento da palavra de ativação

O reconhecedor Android recebe uma lista de prioridade com **Jarvis** e formas
de chamá-lo no Android 13 ou superior; o suporte efetivo depende do serviço de
voz instalado. O app pede até cinco hipóteses e só usa uma alternativa quando
há confiança suficiente fornecida pelo Android. Sem pontuação confiável,
mantém a transcrição principal. O comando após o sinal continua usando a
hipótese principal para não trocar a intenção por uma alternativa.

São aceitas grafias fonéticas próximas como **Jarves**, **Jervis**, **Javis**,
**Javes**, **Djarvis** e a separação **Jar vis**, quando usadas para chamar o
assistente no início da frase, com ou sem “Oi”, “Olá” ou “Ei”. Palavras comuns
e outros nomes como **já vi**, **Java**, **Chaves** e **Jarbas** não são aceitos
como ativação. Repetir “Jarvis, Jarvis” apenas arma a escuta; não vira um pedido.

Se necessário, abra **⚙ → AJUSTAR A PALAVRA JARVIS → OUVIR JARVIS** e diga só o
nome uma vez. Confira a palavra reconhecida e toque **SALVAR VARIAÇÃO** para
adicionar uma forma específica deste telefone. A configuração é criptografada
e pode ser restaurada nessa mesma tela. O app não salva áudio; o serviço de
reconhecimento do Android pode usar a nuvem, conforme a configuração do aparelho.
Isso ajusta o reconhecimento do texto recebido, sem treinar um novo modelo acústico.

## 0.4.2 — confirmação da palavra Jarvis

Ao reconhecer **Jarvis** e estar pronto para receber o pedido, o celular emite
um bip curto, vibra brevemente e mostra **PODE FALAR — ESTOU OUVINDO**. O reator
fica verde e a indicação permanece fixa acima da conversa, mesmo ao rolar o
histórico. O botão flutuante também fica verde e mostra **PODE FALAR** quando a
acessibilidade está ativa. A janela de comando dura dez segundos; depois, volta
a pedir **Jarvis**. Ao enviar um comando, o sinal de prontidão é encerrado.

Essa confirmação é local e não depende do Gemini. O bip respeita o volume de
mídia, e a vibração depende do hardware/configuração do telefone. Resultados
parciais antecipam a confirmação depois de estabelecida uma sessão segmentada;
o resultado final não repete o sinal nem envia a palavra Jarvis como comando.
Se o provedor encerrar a sessão por frase, o sinal aguarda a próxima sessão
ficar pronta. Durante reconexão aparece **PREPARANDO O MICROFONE**.

## 0.4.1 — tempo de resposta

As ações nativas não acumulam mais as pausas fixas de 350 + 450 ms. A observação
aguarda brevemente a estabilização dos eventos de acessibilidade, com limite,
e continua conferindo a janela após agir. Ferramentas de consulta não têm uma
pausa artificial entre resultados. A conexão HTTP da IA é reutilizada entre pedidos.

No envio à IA, capturas antigas das ferramentas são removidas quando já existe
um quadro mais recente. Fotos originais anexadas pelo usuário e assinaturas das
chamadas de ferramentas são preservadas. A sessão de voz é preparada em paralelo
ao processamento do pedido; o texto só é enviado para leitura após a resposta
final. A preparação é encerrada ao cancelar, falhar ou ficar ociosa por 45 segundos.
A voz continua a mesma do PC. Rede, modelo e complexidade ainda afetam o tempo.
No Android 12 ou superior, a reprodução pode iniciar com um trecho menor de PCM
pronto, mantendo o buffer de reprodução para receber os próximos blocos.

Os registros locais `JarvisLatency` medem tempo de modelo, ferramenta e primeiro
áudio, sem texto da conversa, imagens ou chaves de API. A validação usa servidores
simulados para confirmar reutilização da conexão e ausência de fala antecipada.

## 0.3.0 — navegação, visão e aplicativos

Estas funções são executadas no próprio Android, com a chave de IA do celular,
sem depender do computador. No seletor **Computador pareado**, os pedidos
continuam sendo executados pelas ferramentas do PC e respondidos no celular.
Isso não transfere automaticamente plugins, credenciais de câmeras, arquivos,
automações domésticas ou memória do PC ao armazenamento do Android.

## 0.4.0 — casa, memória, arquivos e tarefas

### Câmeras e luzes

Abra **CASA: CÂMERAS E LUZES**. Você pode cadastrar câmeras/DVR Intelbras e iCSee,
com IP privado, porta RTSP, usuário/senha do dispositivo e quantidade de canais.
O botão **IMPORTAR CONFIGURAÇÕES DO PC PAREADO** copia esses dados e a configuração
Tuya pela conexão autenticada. Ele não copia chaves Gemini nem outros plugins.
As credenciais são armazenadas no Keystore e não são incluídas nos resultados
das ferramentas enviados à IA. A importação é uma cópia, sem sincronização automática.

Escolha o canal no player ou diga **“Abra o canal 12 da Intelbras”**. O vídeo usa
Media3 RTSP/TCP e exige H.264; H.265 não é suportado por este player RTSP.
Cada câmera é independente: listar/configurar uma não testa nem bloqueia as outras.
Só o dispositivo escolhido é aberto. O áudio do player inicia desligado e o vídeo
pausa ao sair da tela. **“O que aparece nessa câmera?”** obtém um quadro real para
análise; o app não transmite todos os quadros continuamente à IA. Não há PTZ nesta
integração RTSP nem acesso ao serviço P2P da nuvem iCSee. Fora da rede, é necessária
uma VPN com rota até o IP da câmera; parear apenas o PC não cria essa rota.

A Tuya/Smart Life usa a API oficial de nuvem e o projeto já vinculado à conta do
aplicativo. Configure Access ID, Secret e região ou importe-os do PC. O projeto
precisa ter os serviços e permissões Tuya ativos. **“Liste as luzes”**, **“Ligue a
luz Sala”**, **“Desligue a Sala”** e **“Ajuste o brilho da Sala para 40%”** funcionam
diretamente pelo celular, sem PC ligado. O nome/ID deve identificar um único
dispositivo. As ações não são repetidas automaticamente; a confirmação distingue
o comando aceito do estado verificado. Esta integração controla interruptores e
brilho compatíveis, não todos os tipos de dispositivos Tuya ou rotinas Alexa.

### Informações e tarefas persistentes

Em **MEMÓRIA, ARQUIVOS E TAREFAS**, adicione informações e tarefas manualmente, ou
peça **“Lembre que meu projeto se chama...”**, **“O que você lembra sobre meu projeto?”**,
**“Crie uma tarefa para...”** ou **“Lembre-me amanhã às 15h de...”**. Memórias só são
gravadas por pedido explícito. Você pode listar, esquecer, concluir ou excluir.
O botão de importar memórias faz uma cópia das informações do PC com o prefixo
**PC |**, preservando as informações locais; mudanças posteriores são independentes.

Os lembretes usam alarmes aproximados do Android e notificações. Eles são
restaurados depois de reiniciar o telefone ou atualizar o app e não dependem do
PC. É necessário permitir notificações; economia de bateria pode atrasar o aviso.
Não são alarmes exatos e não executam automações físicas. Concluir ou excluir
uma tarefa cancela o aviso. O limite é de 200 tarefas e 200 informações.

### Arquivos autorizados

Use **ADICIONAR ARQUIVO** para selecionar um documento no seletor do Android.
Não é solicitada permissão para ler todo o armazenamento. O vínculo de leitura
é lembrado; o arquivo original continua onde está. O agente pode listar e ler
texto UTF-8, CSV, Markdown, JSON e PDF local, com leitura por páginas. Texto é
limitado a 1 MB e PDF a 30 MB; documentos grandes são retornados em partes.
Arquivos Word/Excel não são interpretados diretamente nesta versão.

Peça **“Leia o arquivo...”**, **“Resuma a página 2 do PDF...”** ou **“Crie uma nota
chamada compras com...”**. Notas criadas no app são criptografadas e podem ser
editadas pelo agente ou compartilhadas por uma ação sua no seletor de aplicativos.
Originais importados são somente leitura. Segure um documento para remover o
vínculo da biblioteca; isso não exclui o original. Compartilhar gera uma cópia
temporária em cache. O conteúdo usado numa análise é enviado à API Gemini.

As telas locais de memória, tarefas e arquivos funcionam sem PC e sem chamada à
IA; interpretar pedidos por voz/texto continua exigindo o provedor configurado.
Limites e configuração de rede, codecs e permissões precisam ser conferidos
com as câmeras e a conta Tuya reais.

Validação desta versão: memória criptografada, tarefas/notificações, leitura de
texto/PDF, notas, importação autenticada e assinatura/comando Tuya foram testados.
O player Android abriu o canal 12 do DVR Intelbras configurado neste ambiente e
recebeu um quadro real. As luzes foram testadas com servidor simulado; nenhum
dispositivo físico foi ligado/desligado durante a validação.

Referências técnicas: [RTSP no Media3](https://developer.android.com/media/media3/exoplayer/rtsp),
[assinatura Tuya](https://developer.tuya.com/en/docs/iot/new-singnature?id=Kbw0q34cs2e5g),
[dispositivos associados Tuya](https://developer.tuya.com/en/docs/archived-documents/fc19523d18?id=Kakr4p8nq5xsc).

O navegador bloqueia esquemas executáveis/arquivos locais, não expõe uma ponte
JavaScript para código nativo e não ignora certificados inválidos. Capturas e
texto observado são enviados à IA quando uma ferramenta é solicitada pelo
agente para atender ao pedido. Dados dos sites não são instruções do assistente.

Validação em emulador: página com título e link semelhantes, abertura do link
Golden Garden, preenchimento com aspas, recusa de botões duplicados, retorno de
página, captura visual e clique nativo por texto/ID. São páginas de teste; sites
e aplicativos reais devem ser conferidos no aparelho.

### 0.2.1: captura estavel

No Android 13 ou superior, a escuta automatica usa AudioRecord PCM mono de 16 kHz e uma sessao segmentada com EXTRA_AUDIO_SOURCE. O microfone permanece aberto entre segmentos; durante respostas, os quadros sao substituidos por silencio antes de chegar ao reconhecedor. PARAR fecha o fluxo e libera a captura. O suporte a segmentacao depende do servico de voz instalado; Android 11 e 12 conservam o reconhecimento por frases.
# Android 0.5.0 — tarefas do PC

O botao **ACOMPANHAR TAREFAS DO PC** mostra objetivo, etapas e progresso do
plano do computador pareado, com pausar, continuar e cancelar. Requer o PC
atualizado e online. Continua usando os tokens existentes; nao limpa o
pareamento e nao impede as funcoes independentes do Android.



### Seleção de IA ? versão 0.6.0

Em Configurações, escolha **Automático**, **Somente Gemini** ou **Somente IA local** e salve.
Automático prioriza Gemini e continua no local em falha de rede ou HTTP 429/500/502/503/504, após as tentativas existentes, se um modelo estiver importado. Erros de chave ou configuração não provocam troca. Resultados de ferramentas anteriores são mantidos, sem reiniciar a sequência executada. Sem chave, Automático tenta local.

Importe um arquivo `.litertlm` compatível pelo botão de importação (arquivo até 6 GB; espaço livre suficiente para uma cópia). O arquivo é copiado para o armazenamento privado; não ? enviado ao PC nem à API. Um modelo de texto com português e boa saída JSON é necessário. Veja o [catálogo oficial LiteRT Community](https://huggingface.co/litert-community) e os termos de cada modelo. O APK não inclui pesos nem baixa arquivos automaticamente. Importação não comprova compatibilidade: o carregamento nativo a verifica no primeiro uso.

A integração local inicial usa CPU, conversa em texto e as ferramentas de acessibilidade já existentes; comandos são aceitos apenas como JSON válido com nome de ferramenta conhecido. Qualidade e latência de comandos dependem do modelo; ainda precisam ser medidas no S25 Ultra. Imagens são recusadas explicitamente neste modo, mesmo que o arquivo importado tenha capacidade multimodal. A voz Charon e o reconhecimento de fala são independentes e podem exigir internet. A seleção do motor não altera pedidos explicitamente direcionados ao PC.


### Configurações e download — versão 0.6.1

A engrenagem abre uma tela dedicada, com IA, voz/ativação, PC/pareamento, controle remoto, permissões e acesso às configurações de câmeras, DVR, Tuya, memória, arquivos e tarefas. Toque em **SALVAR CONFIGURAÇÕES** para aplicar os campos. Permissões e consentimento de controle continuam com as confirmações do Android.

Em **Modelo local → BAIXAR MODELO LOCAL**, o aplicativo baixa Qwen3 1.7B quantizado do [LiteRT Community](https://huggingface.co/litert-community/Qwen3-1.7B), revisão `79bf0667b32ae025b972e5fe555fe72ca6e8816c`, arquivo de 977.184.032 bytes (aproximadamente 932 MiB). Não exige conta nem chave. O download é iniciado apenas pelo usuário e utiliza a conexão atual, inclusive dados móveis. Reserve pelo menos 1,1 GB e mantenha o app aberto; não é um download persistente após encerramento pelo sistema. A tela pode ser fechada e reaberta sem iniciar um segundo download enquanto o processo continuar vivo. O botão cancelar interrompe a transferência; tentar novamente começa do início.

O arquivo temporário só substitui o modelo instalado depois de conferir tamanho e SHA-256 fixado no catálogo. Falha, cancelamento ou arquivo incompleto preservam o modelo anterior. O SHA-256 esperado é `2a72330b504a6596d53a2c00923c57173b10f1b83e6a541213ffec08d1fc5de8`. A execução local no S25 Ultra ainda exige validação de desempenho e qualidade; download verificado não é validação de inferência. Modelos de texto não substituem a visão nem a voz Gemini.


### Um só Jarvis — versão 0.7.0

Em Configurações, a seção **Um só Jarvis** compartilha memória pessoal, tarefas e contexto recente com o PC principal pareado. Há sincronização manual, fila offline, revisão de conflitos e preservação de IDs. O PC principal usa a rede local/VPN; não há servidor em nuvem. A sincronização funciona enquanto o processo Android está ativo e retorna ao reabrir o app. Não replica arquivos, imagens, chaves nem ações. Veja [o guia dos dispositivos compartilhados](../docs/SHARED_JARVIS.md). Outros PCs se conectam pelo painel **UM SÓ JARVIS — MEUS DISPOSITIVOS** da versão desktop.


### Canal direto protegido — Android 0.8.0

Sincronização entre aparelhos pela internet com TLS e certificado por dispositivo, sem VPN instalada nem servidor intermediário. O primeiro pareamento é local, por convite temporário. Esta etapa compartilha memória, tarefas e contexto; controle remoto e áudio continuam na rede local/VPN. Acesso externo exige configuração do roteador e teste pela rede móvel. Veja [configuração e limites](../docs/DIRECT_CONNECTION.md).


### Leitor QR ao vivo — versão 0.8.1

No canal direto, ESCANEAR QR DO PC abre o leitor integrado e reconhece o convite automaticamente, sem tirar ou salvar foto. Permita o uso da câmera quando solicitado. Após a leitura, confirme em PAREAR CANAL PROTEGIDO. Leitura local com [ZXing Android Embedded](https://github.com/journeyapps/zxing-android-embedded).
