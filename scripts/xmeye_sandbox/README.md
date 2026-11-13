# Teste isolado de câmera iCSee/XMEye

## Integração com Jarvis

O plugin `cameras_locais` agora conecta as iCSee pelo Cloud ID/P2P, tanto no
sítio quanto na rede atual. O Intelbras continua por RTSP. `list`, `test`,
`preview`, `analyze` e `live` usam a conexão correspondente à câmera escolhida;
`stop` fecha o vídeo e remove o contêiner. O vídeo ao vivo usa até 5 JPEGs/s,
sem áudio, com limite de quatro horas por sessão. Não é monitoramento por IA.

O Docker deve estar aberto e a imagem preparada pelos comandos abaixo.
Após atualizar o código, reinicie o Jarvis. A lista de câmeras já importada
aparece por nome. Câmeras com nomes repetidos recebem um sufixo com os últimos
quatro caracteres do Cloud ID. O alias genérico “iCSee” é recusado quando
existem várias opções, para evitar abrir a câmera errada.

As credenciais podem ser preenchidas por câmera em Configurações → Plugins →
CÂMERAS — ICSEE NUVEM / INTELBRAS, ou pelo formulário local abaixo. O botão
**Salvar no Jarvis e testar** grava apenas a credencial daquela câmera em
`config/api_keys.json`, arquivo local ignorado pelo Git. O formato atual dessa
configuração armazena a senha em texto simples, como os demais campos do plugin;
não se trata de um cofre criptografado. Credenciais antigas por IP não são
atribuídas automaticamente às câmeras importadas.

Exemplos: “Jarvis, liste minhas câmeras”, “abra a câmera casa”, “mostre a câmera
Entrada do sítio”, “feche a câmera”. A análise de uma captura envia essa imagem
ao provedor de IA configurado e deve ser anunciada antes; visualizar não envia.

Este protótipo executa somente o SDK x86 já inspecionado dentro de Wine em
Docker Linux. Não carrega DLLs no Windows nem no Jarvis. O Docker Desktop deve
estar funcionando. O contêiner roda como usuário sem privilégios, sem capacidades,
sem volumes do host, sem portas publicadas, com limite de recursos e raiz somente
de leitura. O diretório de trabalho e o prefixo Wine usam memória temporária.

Isso reduz o acesso ao PC; não é prova de ausência de malware. Durante o teste
real, o SDK terá acesso de saída à rede Docker, inclusive rotas disponíveis por
ela. Não há filtro de destinos, garantia de criptografia ou auditoria completa
do tráfego. Há amostragem de destinos TCP IPv4, sem conteúdo de pacotes; UDP,
DNS e conexões muito breves não são integralmente auditados.

## Preparar e testar o ambiente

Na raiz do projeto:

```powershell
.venv\Scripts\python.exe scripts/xmeye_sandbox/prepare.py
docker build -t jarvis-xmeye-probe:local .codex-attachments/xmeye-sandbox-build
.venv\Scripts\python.exe scripts/xmeye_sandbox/control.py --check load
.venv\Scripts\python.exe scripts/xmeye_sandbox/control.py --check init
```

Os dois últimos comandos usam `--network=none` e não aceitam credenciais.
A preparação confere hashes das duas DLLs locais e baixa o Python embutido
x86 3.11.9 de python.org, também com hash fixado. Os pacotes Wine/FFmpeg vêm
dos repositórios Debian da imagem oficial bookworm-slim. Não são usados os
EXEs ou scripts daquele repositório de terceiros.

## Testar uma câmera

```powershell
.venv\Scripts\python.exe scripts/xmeye_sandbox/control.py
```

No formulário, informe o Cloud ID/número de série, o usuário e a senha **do
dispositivo**. Esses dados são entregues ao SDK para conexão à câmera pela
nuvem/P2P, não são as credenciais da conta do portal. Use credencial exclusiva
e restrita se a câmera permitir. O teste usa canal 0/substream 1 e faz uma
tentativa de login por clique. Não tenta senhas alternativas, não altera
configurações, não move a câmera, não atualiza firmware e não ativa gravação.

Se existir `config/xmeye_devices.json`, o formulário oferece uma lista por nome
que preenche Cloud ID e usuário. A lista local contém apenas `name`, `cloud_id`
e `username` e está ignorada pelo Git. Foram importados 13 dispositivos a partir
da tabela visível na sessão autenticada do portal, sem copiar senhas ou cookies.
Nomes repetidos são diferenciados pelos últimos quatro caracteres do identificador.
Trocar a câmera limpa o campo de senha. É uma cópia da lista daquele momento;
não há sincronização automática periódica com a conta iCSee.

As credenciais passam por stdin ao contêiner e ficam no seu tmpfs durante o
teste, não em argv, variável de ambiente ou arquivo de requisição do host.
O botão de salvar mantém a credencial na configuração local do Jarvis conforme
descrito acima; essa persistência é separada do transporte para o contêiner.
O SDK pode produzir suas próprias saídas; elas são descartadas. O log Docker
está desativado. Ao terminar, o contêiner é removido. A senha também é limpa
do campo após iniciar. O controlador não promete zerar todas as cópias da
senha na memória do Python.

O teste de captura dura no máximo cerca de 100 segundos. Recebe uma amostra limitada
de vídeo e tenta decodificar um quadro em JPEG dentro do contêiner. Se funcionar,
a imagem aparece só no formulário local, sem envio a IA ou publicação HTTP/RTSP.
O diagnóstico do host omite as credenciais e a imagem e fica no arquivo ignorado
`.codex-attachments/xmeye-probe-status.json`.

`video_verified` significa um quadro decodificado, não uma avaliação de segurança
ou garantia de estabilidade contínua. `login_failed` inclui apenas código numérico
do SDK. `received_decode_failed` significa que chegaram dados, mas não foi
possível validar uma imagem. A conexão contínua do Jarvis usa o fluxo `live`,
decodifica os quadros no contêiner e os envia ao HUD por um pipe local enquadrado.

## Validação realizada em 12/11/2026

- SDK carregou como 32 bits em contêiner sem rede: `loaded`.
- SDK inicializou em contêiner sem rede: `initialized`.
- Estruturas: CLIENTINFO 20 bytes; PACKET_INFO_EX 84 bytes em x86.
- Nove testes do controlador passaram, cobrindo transporte de credenciais,
  ausência de volumes/portas, remoção após timeout, sanitização de relatórios
  e remoção de marcadores privados de vídeo.
- A integração passou em 48 testes focados de controlador, câmeras, descoberta,
  HUD e VMS.
- O fluxo contínuo real do plugin recebeu oito JPEGs da câmera configurada do
  sítio, em 960×540. O primeiro fluxo abriu em cerca de 21 segundos. Ao encerrar,
  o contêiner foi removido. Nenhuma imagem foi enviada à IA nesse teste.
- Um teste sem rede, usando vídeo sintético, validou dez JPEGs através do
  decodificador real e do enquadramento de dados usado pelo HUD.
- Após o preenchimento local pelo usuário, o teste retornou `video_verified`:
  62 callbacks/pacotes de vídeo, 253.239 bytes e codec 2 (H.264), com um JPEG
  decodificado dentro do contêiner e entregue ao formulário local. O campo
  `frames` conta callbacks/pacotes, não necessariamente quadros completos.
  O contêiner foi removido após o teste.
- O usuário confirmou que a câmera testada fica no sítio, em outra rede.
  Isso confirma o acesso remoto para esse teste, sem garantir estabilidade
  contínua. A amostragem não registrou destinos TCP IPv4 nesse teste;
  UDP/P2P não foi auditado por esse mecanismo.

Os tamanhos e as assinaturas foram comparados com o cabeçalho público NetSDK
de https://github.com/hifided/IPCAS/blob/main/netsdk/netsdk.h ; isso não elimina
possíveis diferenças entre a versão instalada e a versão desse cabeçalho.
