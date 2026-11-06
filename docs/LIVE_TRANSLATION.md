# Tradução local de vídeos (Windows)

A fala do vídeo é reconhecida e traduzida localmente com **faster-whisper + Argos**.
A narração usa **a voz neural local Piper pt_BR-faber-medium**. Áudio e texto
permanecem no computador. Após a preparação dos modelos, legendas e narração
funcionam sem internet ou chave de API. A voz tem outro timbre: não é a Charon.

## Preparação

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-translation.txt
# Opcional: aceleração NVIDIA com driver compatível com CUDA 12
.\.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
.\.venv\Scripts\python.exe setup_translation.py --model small --source en --target pt
.\.venv\Scripts\python.exe setup_translation.py --voice pt_BR-faber-medium
```

A GPU é selecionada automaticamente quando detectada. O padrão é Whisper small
na GPU e base na CPU. Para usar CPU, prepare também esse modelo e configure antes
de iniciar o Jarvis:

```powershell
.\.venv\Scripts\python.exe setup_translation.py --model base
$env:JARVIS_TRANSLATION_DEVICE = "cpu"
```

`JARVIS_TRANSLATION_MODEL` seleciona outro modelo previamente preparado.
Falhas de CUDA aparecem na legenda e no status. Não há mudança silenciosa para
serviço de nuvem. Whisper fica em `models/translation/` (ignorado pelo Git);
os pacotes Argos ficam na pasta de dados do usuário.

## Uso

Reinicie o Jarvis e diga ou escreva **“Traduza o que estou assistindo”**.
Para vídeos em inglês, **“Traduza este vídeo do inglês para português”** fixa o
idioma de origem e evita detecções instáveis em frases muito curtas.
A janela de legendas aparece sobre os aplicativos e pode ser movida.
O áudio traduzido vem ativado por padrão. A opção **Ouvir tradução ao vivo** na
janela e os comandos **“ative o áudio da tradução”** / **“somente legendas”**
permitem alternar a narração sem reiniciar a captura. Para encerrar, diga
**“parar tradução”**, feche a janela ou use **Parar tradução**. Parar cancela também
a fala que estiver tocando e descarta os textos pendentes.
**“Status da tradução”** informa modelo, dispositivo e tempo da última tradução.
Esse tempo é de processamento; não inclui a espera para capturar a fala.

Para outro par de idiomas, prepare os modelos antes de usar:

```powershell
.\.venv\Scripts\python.exe setup_translation.py --source es --target pt
```

O modo automático detecta o idioma em cada trecho. Um idioma sem pacote instalado
mostra instruções e interrompe a sessão. Não baixa modelos durante a captura.
A disponibilidade dos pares depende do catálogo Argos.

## Latência e limites

A captura usa o loopback por processo do Windows, sem microfone, e exclui o
processo do Jarvis e seus processos filhos. Assim, nem as respostas do Jarvis nem
a narração traduzida voltam para a tradução. O vídeo externo continua sendo
capturado mesmo durante a narração. A captura abrange os dispositivos de saída,
sem ficar presa à saída padrão. Requer Windows build 20348 ou posterior; se não
for suportado, mostra erro, sem retornar à captura que causava o ciclo.

Use com vídeos no navegador ou em outro player externo. O player interno do HUD
também pertence ao processo do Jarvis e fica excluído. Outros aplicativos e
notificações ainda podem entrar na captura. Players iniciados pelo próprio
Jarvis como processos filhos também ficam excluídos; abra o player separadamente.

A opção explícita `JARVIS_TRANSLATION_TTS=gemini` segue a voz escolhida no Jarvis. Usa Gemini TTS com
áudio em streaming (PCM mono, 24 kHz), mantendo o reconhecimento e a tradução
locais. O modelo padrão é `gemini-3.8-flash-lite-tts`; `JARVIS_TRANSLATION_TTS_MODEL`
permite escolher outro modelo TTS compatível. Não usa a conversa principal do
Jarvis para ler as legendas. Ao mudar a voz do Jarvis, reinicie a tradução para
carregar a nova voz. O timbre acompanha a escolha; a entonação pode variar entre
o modelo de conversa e o de síntese.

O padrão é totalmente offline. Para restaurar esse modo após selecionar Gemini:

```powershell
.\.venv\Scripts\python.exe -m pip install "piper-tts>=1.3,<2"
.\.venv\Scripts\python.exe setup_translation.py --voice pt_BR-faber-medium
$env:JARVIS_TRANSLATION_TTS = "piper"
```

`JARVIS_TRANSLATION_VOICE` seleciona outra voz Piper previamente instalada e do
mesmo idioma de destino. Para outros idiomas, a seleção automática usa uma voz
instalada daquele idioma. `JARVIS_TRANSLATION_TTS=system` permite usar explicitamente
a voz antiga do Windows. `JARVIS_TRANSLATION_TTS=gemini` é uma opção de nuvem que
envia o texto traduzido e consome cota; nunca é usada como fallback automático.
Não há troca silenciosa para outra voz quando a síntese falha. No modo Gemini,
sem conexão ou cota, a narração é desativada e as legendas continuam. A fila mantém
somente a fala mais recente pendente; se a tradução falada não acompanhar o vídeo,
trechos são omitidos em vez de acumular atraso. A narração cede a vez às respostas
do Jarvis. Enquanto ela fala e durante uma pequena margem de eco, o microfone do
assistente não envia essa voz de volta ao modelo. O botão Parar permanece disponível.

Os trechos fecham após cerca de 300 ms de silêncio (mínimo de 600 ms por trecho)
ou ao atingir cerca de dois segundos. O filtro de atividade vocal do Whisper
reduz transcrições de silêncio; o recorte inicial usa o volume do áudio, podendo
confundir música com fala. A legenda aparece depois do reconhecimento e tradução.
Blocos antigos são descartados quando o processamento não acompanha o vídeo.
Frases podem ser cortadas entre blocos, reduzindo o contexto da tradução. Não há
sincronização pelo relógio do vídeo ou pelos lábios. Legendas expiram em 15 segundos.

Na validação com RTX 5060 Ti, Whisper small em CUDA e Argos em CPU, os blocos de
dois segundos de uma fala sintética em inglês levaram 0,12–0,15 s para reconhecer
e traduzir após aquecimento, com conexões de rede bloqueadas no teste. Isso não
inclui a captura nem garante o mesmo resultado com vídeos reais. O primeiro
processamento levou 1,74 s; carregar e aquecer o Whisper levou cerca de 9–27 s.

Fontes: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[Argos Translate](https://github.com/argosopentech/argos-translate) e
[captura por processo da Microsoft](https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/ApplicationLoopback).

A síntese segue a [documentação de voz do Gemini](https://ai.google.dev/gemini-api/docs/generate-content/speech-generation).
