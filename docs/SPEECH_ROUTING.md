# Voz no PC ou no celular conforme a presença

Com a preferência ativada, o Jarvis consulta a webcam antes de cada fala do
assistente, incluindo respostas, avisos proativos e resumos dos agentes.
Os fragmentos de áudio da mesma fala mantêm o destino escolhido; a fala seguinte
faz uma nova consulta.

- Rosto do usuário cadastrado confirmado: áudio somente no PC.
- Usuário ausente, câmera indisponível ou resultado inconclusivo: áudio no Android.
- Android offline, voz desligada, app antigo ou vários aparelhos sem um destino
  escolhido: resposta no histórico e aviso de diagnóstico, sem áudio no PC.

A verificação usa os modelos de rosto locais já instalados. Não salva imagens
nem envia a webcam a um provedor de IA. Se o aviso visual descrito abaixo estiver
ativado, envia a prévia apenas ao celular pareado escolhido. O perfil segue o proprietário configurado
(`voice_owner`/`user_name`), ou o único rosto cadastrado se não houver um nome
configurado correspondente. É possível escolher explicitamente outro perfil.
Sem cadastro de rosto, a presença não pode ser confirmada e a saída vai ao celular.

O Android precisa da versão atualizada do app, pareada ao PC, com a conexão
**Respostas no celular** ou **Controle entre aparelhos** ativa e a voz habilitada.
O PC espera a confirmação do app antes de transmitir o áudio; ele não abre
mensageiros nem faz chamadas. A voz transmitida é o mesmo PCM gerado no PC.
Uma falha de rede não provoca repetição automática nem troca para o alto-falante
do PC. A verificação também não muda o volume ou reativa a voz desligada no app.

Por voz: “ative a saída de voz conforme minha presença”, “qual o destino da voz?”
ou “desative a troca de voz pela webcam”. A ferramenta `speech_destination`
aceita `enable`, `disable`, `status`, com `owner` e `device_id` opcionais.
As preferências ficam em `config/speech_routing.json` e persistem após reiniciar.

## Pessoa não reconhecida e prévia no celular (Android 0.9.6)

Com `unknown_alerts=true`, quando houver um rosto visível e duas leituras não
confirmarem o proprietário, o Jarvis envia uma imagem e uma prévia atualizada
da webcam por até 20 segundos ao Android escolhido. Não dispara o aviso para
uma câmera vazia, um erro da câmera ou falta de conexão com o celular. Não há
monitoramento permanente; a consulta ocorre antes das falas do assistente.

O celular anuncia exatamente: “Evaldo, tem uma pessoa não identificada mexendo
no seu computador”. Essa frase é o aviso solicitado pelo usuário; a evidência
é um rosto diante da câmera sem confirmação do proprietário, e não comprovação
de quem está usando teclado/mouse ou de uma intrusão. A tela da prévia informa
que pode se tratar de falha de reconhecimento.

Com o Jarvis aberto no celular, a tela da prévia abre automaticamente. Em segundo
plano, aparece uma notificação com imagem; toque nela para abrir a prévia. O app
precisa de notificações permitidas, conexão com o PC e voz habilitada. O aviso
falado usa a voz neural local incluída no APK, sem chave Gemini. Aviso e áudio
da resposta do PC entram em uma fila, evitando cortes entre eles. O mesmo aviso
é limitado a uma vez a cada dois minutos enquanto a pessoa permanece sem
identificação; uma confirmação do proprietário permite um novo aviso depois.

Os quadros ficam em memória, sem arquivo de vídeo ou foto criado pelo Jarvis.
A prévia termina após 20 segundos e os quadros no app expiram em um minuto.
O reconhecimento deixa de tratar como concorrentes cadastros com nome curto e
nome completo quando seus vetores de referência são muito semelhantes; outros
rostos ambíguos continuam sem confirmação. Também permite encontrar o
proprietário quando há mais de uma pessoa no enquadramento.

Se a voz não chegar, consulte `speech_destination status`: ele informa aparelhos
conectados, suporte a áudio/prévia e o último erro de entrega. A versão atual
usa prazo relativo para confirmar o áudio, sem exigir relógios iguais no PC e
no Android. O APK atualizado está em `dist/JARVIS-Android-debug.apk`.

Esta regra trata as falas da sessão do assistente no PC. Reprodução de vídeos e
narração de traduções são recursos separados. A conexão de controle do celular
precisa continuar disponível para receber as falas quando você estiver longe.
