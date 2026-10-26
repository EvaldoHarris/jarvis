# Canal direto do Jarvis — etapa local, versão Android 0.8.0

O novo transporte faz sincronização diretamente entre dispositivos pela internet, sem relay, STUN, VPN ou servidor externo de descoberta. O PC principal atende uma porta TCP dedicada, 9443. O painel HTTP existente na 8000 não faz parte dessa publicação. Nesta versão, o novo listener oferece **somente sincronização pessoal**; controle de aplicativos, áudio e WebSockets continuam nos mecanismos locais/VPN existentes. Não considere essas funções migradas para a conexão direta.

## Estado desta instalação

Foi confirmada saída IPv6 pública no PC. O IPv4 mostrado pela Vivo coincide com o observado externamente: há um caminho IPv4 público que pode ser testado por encaminhamento de porta. Isso não confirma que a operadora/roteador permite entrada nem substitui um teste pela rede móvel. O endereço IPv4 pode mudar; esta versão não usa DDNS automático. Mudanças de IP exigem atualizar o certificado do servidor e o destino nos aparelhos.

O listener foi preparado para **192.168.15.13:9443**, apenas na interface local do PC. É carregado ao reiniciar o Jarvis. As regras do roteador não foram alteradas. A sessão de trabalho não é administradora do Windows; o script `scripts/Enable-JarvisDirectFirewall.ps1` está preparado para criar uma regra restrita quando executado pelo usuário como administrador. Ele verifica o IP e o perfil Privado da interface, identifica o executável que atende o painel 8000 e permite somente sua entrada TCP na 9443. Não desativa firewall e não altera DMZ ou UPnP.

## Primeiro teste na rede local

1. Reinicie o Jarvis no PC. Abra **CANAL DIRETO PROTEGIDO**. Inicialmente use o endereço `https://192.168.15.13:9443`.
2. Se o Windows bloquear a nova porta, execute o script de firewall em PowerShell como administrador, com o Jarvis aberto. O comando de reversão está no fim do script.
3. No painel do PC, gere um convite. No Android, abra **Configurações → Canal direto protegido**, escaneie o QR ou importe o convite `.jarvis` por um meio local e toque em parear. O primeiro pareamento usa a rede local. O convite é secreto e expira em dez minutos; não o envie a terceiros.
4. Toque em sincronizar e confira o estado do perfil. Somente após esse percurso funcionar, configure e teste o acesso externo.

## Caminho IPv4 do roteador mostrado pelo usuário

Depois do teste local, a regra a revisar no roteador é:

| Campo | Valor |
|---|---|
| Nome da regra | JARVIS_TLS |
| Protocolo | TCP |
| Porta externa | 9443 |
| Porta interna | 9443 |
| IP interno | 192.168.15.13 |
| IP externo/origem | Em branco para clientes em redes móveis; a autenticação obrigatória continua sendo por certificado |

A porta pública de destino fica no IPv4 público **atual** do roteador: `https://IP-PUBLICO:9443`. O IP interno deve permanecer reservado para o PC no DHCP. No Android pareado, o botão **Usar endereço externo HTTPS** atualiza o destino; em outro PC, use o campo de destino HTTPS do cliente. O certificado do servidor precisa conter esse IP: a preparação atual inclui o IPv4 público confirmado e os endereços locais/IPv6 observados. Se o IP mudar, prepare o listener com o novo destino, reinicie o Jarvis e só então atualize os clientes. A CA é preservada, então não é necessário trocar chaves dos aparelhos apenas para atualizar o certificado do servidor.

Faça o teste externo no celular com Wi-Fi desligado, pela rede móvel. Falhas de hairpin NAT podem impedir o uso do endereço público enquanto o celular permanece no Wi-Fi da própria casa. Esta verificação ainda depende da configuração real do roteador e do telefone; não foi marcada como concluída.

## Autenticação e chaves

- TLS 1.2 ou superior, com certificado do servidor verificado contra a CA privada do PC e validação normal do hostname/IP. Não há trust-all nem hostname verifier permissivo.
- O listener exige certificado de cliente na negociação TLS. Cada pedido também inclui assinatura ECDSA P-256/SHA-256 vinculada ao dispositivo, método, caminho, corpo, timestamp e nonce; a aplicação verifica o cadastro e a revogação em cada requisição.
- Nonces persistidos rejeitam repetição; timestamps têm janela de 90 segundos. Dispositivos autenticados têm limite de pedidos e o corpo é limitado a 2 MB. A sincronização mantém os IDs de mutação para evitar duplicatas após perda da resposta.
- Android gera a chave privada no Android Keystore; ela não é exportada. O Windows protege chaves e credenciais persistidas com DPAPI. Arquivos temporários de chave do Windows existem apenas durante o carregamento para OpenSSL e são removidos antes de atender conexões.
- O convite transfere uma chave aleatória de 256 bits pela tela/arquivo do PC. A troca inicial na rede local é selada com AES-GCM; a chave do convite nunca é enviada pelo HTTP. O aparelho apresenta sua chave pública e prova de posse; a resposta também é autenticada e cifrada. Um convite só aceita um pedido, com repetição idêntica permitida para recuperar resposta perdida.
- Certificados de cliente duram 180 dias; o re-pareamento após expiração é manual nesta etapa. Revogar no PC bloqueia pedidos novos mesmo em uma conexão TLS já estabelecida. Não há replay de comandos ou fila de execução neste listener.

As estruturas de TLS e chaves seguem as APIs de [SSL do Python](https://docs.python.org/3/library/ssl.html) e do [Android Keystore](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec.Builder#setDigests(java.lang.String...)). Para o uso da chave EC no TLS Android, é autorizado também `DIGEST_NONE`, pois a pilha TLS já calcula o digest; as assinaturas dos pedidos continuam usando SHA-256.

## Testes executados

Testes Python usam TLS real para verificar recusa sem certificado, CA incorreta, assinatura/corpo alterado, replay, expiração de pedido, revogação e ausência de rotas de login/controle na porta dedicada. O emulador Android pareou com a implementação Python real, usando chave do Keystore, sincronizou e foi recusado após revogação. Um PC cliente também pareou, recarregou credenciais DPAPI, sincronizou e foi recusado após revogação. Esses testes não representam uma auditoria independente nem demonstram alcance externo através da operadora.

Para reproduzir a interoperabilidade, `python -m core.direct_fixture` inicia serviços temporários somente em loopback, usados pelo teste Android `DirectChannelIntegrationTest` com `adb reverse` nas portas 18888/19443. A fixture nunca é importada pelo aplicativo. Não deve ser publicada na internet.


## Correção de pareamento com painel HTTPS — 0.8.3

O painel HTTPS padrão usa 8001. O convite usa a porta HTTP configurada (`dashboard.server.PORT`, padrão 8000) para a troca inicial selada com AES-GCM, inclusive quando o painel HTTPS está ativo. Essa rota não redireciona nem usa o certificado autoassinado do painel: o segredo do convite autentica a troca. O restante das páginas continua redirecionando para HTTPS. Não publique a porta de pareamento na internet. A sincronização continua em 9443 com mTLS.

Reinicie primeiro o Jarvis e só depois gere um convite novo. Convites ficam em memória, expiram em dez minutos e deixam de existir ao reiniciar. A versão Android 0.8.3 distingue convite expirado/perdido, já usado e rede local exigida. Não reinicie o PC entre escanear e confirmar o pareamento.


## QR reduzido — Android 0.8.4

O QR exibido pelo PC contém o convite e o SHA-256 do certificado da CA, sem carregar o certificado inteiro. O cliente busca o certificado público em `/api/direct/ca` na mesma origem local do convite, sem redirecionamentos, e verifica o SHA-256 antes de usá-lo. Substituição do certificado bloqueia o pareamento. A chave secreta do convite permanece no QR; a troca de credenciais continua selada com AES-GCM. O arquivo .jarvis preserva o formato completo anterior. Atualize o Android, reinicie o PC e gere outro QR.


## Endereço local e externo — Android 0.8.5

Em Canal direto protegido → Usar endereço externo HTTPS, salve o endereço público atual do PC. Essa configuração preserva o destino local. Ao sincronizar, o aplicativo tenta o local e, se houver falha de transporte, tenta o externo com uma assinatura e nonce novos, sempre com mTLS e validação de certificado. Falha de certificado ou recusa HTTP não provoca troca de destino. O primeiro endereço tem prazo de conexão de dois segundos quando há alternativa. Não existe descoberta automática de IP público; se ele mudar, atualize o certificado no PC e o destino externo. A regra de entrada do roteador e do Windows continua necessária.


## Endereços separados — Android 0.8.6

O painel do canal permite editar o endereço local HTTPS separadamente do externo. Isso corrige configurações migradas em que o IP público foi salvo nos dois campos. Novos pareamentos preservam o endereço local a partir da origem do convite, mesmo quando o destino direto escolhido no PC é público. A verificação normal de hostname e certificado continua obrigatória em ambos os destinos. O teste instrumentado DirectConnectionDiagnosticTest é opt-in e não imprime chaves, convites ou conteúdo sincronizado.
