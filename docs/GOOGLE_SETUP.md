# Conectar Google Agenda e Gmail ao Jarvis

O codigo da integracao esta pronto. A conta so fica conectada depois de voce
criar um cliente OAuth e autorizar o Jarvis na pagina oficial do Google.
Nao use a chave Gemini para isso e nao envie senha, token ou JSON de credenciais
na conversa. O JSON e importado diretamente no programa do PC.

1. Abra o [Google Cloud Console](https://console.cloud.google.com/) e crie ou
   selecione um projeto seu.
2. Em APIs e servicos, ative **Gmail API** e **Google Calendar API** nesse projeto.
3. Configure a plataforma Google Auth: nome do aplicativo e email de suporte.
   Para conta Gmail pessoal, escolha publico externo; em modo de testes,
   adicione sua propria conta em usuarios de teste.
4. Em Google Auth > Clientes, crie um cliente OAuth do tipo **App para
   computador / Desktop app**. Baixe o JSON.
5. Reabra o Jarvis atualizado. Em Configuracoes, abra **GOOGLE AGENDA E GMAIL**,
   escolha **Importar cliente OAuth Google (.json)** e selecione esse arquivo.
6. Clique em **Conectar minha conta Google**. Escolha sua conta na pagina do
   Google, revise as permissoes e conclua o consentimento. Se o Google bloquear
   a autorizacao, confira o erro e a configuracao do projeto; nao contorne
   bloqueios de seguranca.
7. Apos conectar, experimente "Liste meus proximos compromissos" ou
   "Liste meus emails nao lidos".

O Jarvis solicita leitura do Gmail, envio de email e acesso aos eventos do
calendario. Enviar uma mensagem ou criar um compromisso exibe uma previa
concreta no PC e so acontece apos confirmar no painel. Nao ha exclusao de emails
ou eventos, envio de convites a participantes, leitura automatica de anexos ou
alteracao automatica de mensagens nesta versao.

Os tokens sao criptografados pelo Windows DPAPI para o usuario atual e ficam
fora do Git. Os dados de mensagens/eventos que voce pedir para consultar entram
na conversa com o provedor configurado do assistente. O arquivo de cliente OAuth
tambem fica fora do Git. O consentimento em modo de testes pode precisar ser
renovado conforme as regras do Google.

Referencias oficiais:

- [Configuracao e OAuth Desktop para Gmail](https://developers.google.com/workspace/gmail/api/quickstart/python)
- [Configuracao do Google Calendar](https://developers.google.com/workspace/calendar/api/quickstart/python)
