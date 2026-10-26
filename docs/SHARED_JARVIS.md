# Um só Jarvis nos dispositivos da mesma pessoa

O PC principal é o ponto de sincronização na rede local ou VPN privada. Cada instalação continua com seu motor de IA e suas ferramentas locais. O perfil compartilhado fornece memórias pessoais, tarefas pessoais e as últimas mensagens de texto para dar continuidade às conversas. Parear dispositivos é o vínculo com o mesmo perfil; reconhecimento facial ou um nome igual não autoriza vincular outra instalação.

## Configurar

1. Reinicie o Jarvis do PC principal com o código atualizado. Em configurações, abra **UM SÓ JARVIS — MEUS DISPOSITIVOS**. O papel inicial deste PC é principal. O servidor de acesso remoto precisa estar funcionando; não abra portas públicas no roteador.
2. No Android 0.7.0, mantenha o PC principal pareado. Em **Configurações → Um só Jarvis**, deixe o compartilhamento ativo e toque em **SINCRONIZAR AGORA**. Fora da mesma rede, use o endereço do PC na VPN privada no pareamento.
3. Em cada outro PC, instale esta versão e abra **UM SÓ JARVIS — MEUS DISPOSITIVOS**. Dê um nome ao computador, informe o endereço do principal e a chave de oito caracteres gerada no acesso remoto do principal. Toque em **Conectar este PC ao meu principal**. O token persistente fica protegido pelo DPAPI do Windows e não entra no prompt nem no repositório.
4. A lista mostra aparelhos que se conectaram recentemente; a presença expira em 90 segundos. O perfil possui um identificador estável, diferente do ID de cada aparelho.

O celular e os outros PCs sincronizam aproximadamente a cada 20 segundos enquanto os respectivos processos estão ativos. O Android pode suspender ou encerrar o app em segundo plano; a fila é persistida e a sincronização retorna quando ele for aberto. **Sincronizar agora** não depende da próxima consulta periódica. Fora de casa, ambos os lados precisam estar na VPN e o principal precisa estar ligado.

## O que é compartilhado

- Categorias pessoais de memória: identidade, preferências, projetos, relações, desejos e notas. No Android, novas memórias simples usam a categoria `notes`; a categoria das importadas é preservada.
- Tarefas pessoais criadas no Android ou pela ferramenta `shared_jarvis` do PC, incluindo conclusão e exclusão. IDs são preservados entre aparelhos. São listas pessoais; os planos executáveis `task_plan`, rotinas e lembretes legados do PC continuam em seus mecanismos próprios.
- Contexto recente das conversas: texto do usuário e da resposta, horário e dispositivo. O assistente recebe até 16 mensagens recentes, dentro do orçamento de contexto, e as tarefas pessoais abertas. O histórico não substitui uma observação atual da tela.

Arquivos e seus caminhos, imagens de tela/câmera, áudio bruto, biometria, chaves de IA, credenciais de Gmail/Tuya/câmeras, configurações de hardware e recibos de execução não são replicados por esta funcionalidade. As integrações locais existentes continuam funcionando. O contexto compartilhado entra na conversa com o motor de IA escolhido em cada instalação, assim como as memórias locais já entravam.

## Offline, conflitos e execução

Sem o principal, cada dispositivo conserva sua memória e fila local e continua independente. Ao voltar a conexão, envia somente alterações pendentes e recebe o estado compartilhado. Repetir uma solicitação de sincronização com o mesmo ID não repete a alteração. Exclusões usam tombstones para não ressuscitar informações em aparelhos que estavam offline.

Se dois aparelhos mudarem o mesmo registro desde a mesma revisão, o segundo mantém sua versão local, o principal mantém a versão recebida e aparece um conflito. A tela de conflitos permite comparar e escolher a versão local ou a do principal. Não há sobrescrita silenciosa; uma mudança posterior do principal pode exigir nova revisão.

**Sincronização não executa ações.** Ela não transfere um navegador aberto, não duplica cliques, não envia novamente mensagens e não retoma automaticamente um plano de execução em outra máquina. Um pedido novo pode usar o contexto compartilhado, mas o assistente precisa observar o dispositivo e conferir o resultado real das ferramentas. O destino continua sendo o aparelho em uso, salvo pedido explícito para controlar o PC/celular pelas ferramentas já disponíveis. Esta versão não faz arbitragem acústica entre vários microfones que escutem simultaneamente a palavra Jarvis.

## Validação no uso real

1. No celular, peça para guardar uma preferência de teste. Sincronize e consulte-a no principal e em um segundo PC pareado.
2. Crie uma tarefa no celular. No PC, liste **tarefas pessoais compartilhadas**, conclua a tarefa e confira a conclusão no celular.
3. Converse no PC e depois pergunte no celular sobre o assunto anterior. Se houver várias conversas possíveis, escolha qual continuar; não repita uma ação já executada.
4. Desligue o principal, altere uma informação no celular, religue-o e sincronize. Confirme que o celular informou a pendência enquanto estava offline.
5. Edite a mesma informação em dois aparelhos offline. Após conectar, revise as duas versões na tela de conflitos.

Testes automatizados cobrem o protocolo, autenticação da API, isolamento de perfil, idempotência, exclusões, conflito, ponte de memória e um percurso Android em emulador com servidor de teste. Conectividade pela VPN e o segundo PC físico ainda dependem da configuração real desses aparelhos.
