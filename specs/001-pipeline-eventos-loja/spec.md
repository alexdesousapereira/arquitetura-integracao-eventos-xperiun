# Feature Specification: Pipeline de Eventos da Loja

**Feature Branch**: `001-pipeline-eventos-loja`

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "requisitos/decisoes.md" — simulação de eventos de uma loja
(recebimento, transporte e entrega de pedidos), ingestão contínua dos arquivos de eventos com
controle operacional da ingestão, disponibilização dos eventos em um barramento de mensagens,
API de consulta sobre os eventos e documentação para operar e testar a arquitetura de ponta a ponta.

## Clarifications

### Session 2026-11-02

- Q: A que se refere o "time de 15 minutos de duração dos arquivos"? → A: Retenção das mensagens
  no tópico (15 minutos).
- Q: Quando os eventos de um pedido saem do tópico após os 15 minutos, a API de consulta também
  deve deixar de mostrar esse pedido? → A: Sim — a API descarta da memória eventos com mais de
  15 minutos (pelo horário do evento); a pedido some quando todos os seus eventos expiram.
- Q: O que deve acontecer com os arquivos JSON já ingeridos? → A: São movidos para uma pasta de
  backup dentro de `dados/` (`dados/backup`), onde ficam guardados sem limpeza automática.
- Q: Ao subir o ambiente, a ingestão começa sozinha ou só após ativação pela API de controle?
  → A: Só por ativação manual via API de controle.
- Q: O teste de pedido deve validar a taxa da spec ou uma taxa maior, com margem? → A: Nenhum dos
  dois: rodar um volume pequeno de dados. O objetivo é simular e validar a arquitetura (fluxo,
  contratos, operação), não desempenho; testes de pedido/estresse ficam fora do escopo.
- Q: Quantos arquivos/eventos as simulações e o cenário de arquivos acumulados devem cobrir? → A:
  10 eventos por simulação (revisado de "10 a 20"); não simular grandes ingestões.
- Q: Como comprovar que os eventos saem do tópico após a retenção? → A: Teste automatizado com
  retenção curta (ex.: 30 s) aplicada só durante o teste, confirmando a expiração em poucos minutos.
- Q: A garantia de "sem perda" cobre a falha dupla (barramento fora e serviço de ingestão
  reiniciado/travado durante a queda)? → A: Não — fora do escopo; risco aceito da simulação local.
- Q: Com a simulação limitada a 10 eventos, o simulador ainda deve permitir execução contínua?
  → A: Sim, como opção explícita; o padrão gera 10 eventos e encerra.
- Q: Em quais plataformas de host o comando único de subida (`make up`) deve funcionar? → A:
  Linux, macOS e Windows via WSL2 + Docker Desktop, inclusive com o repositório clonado pelo Git
  for Windows (`core.autocrlf=true`).
- Q: O que deve acontecer ao rodar `make up` sem o arquivo `.env`? → A: Manter o comportamento
  atual (o comando falha); o README documenta a cópia manual de `.env.example` para `.env` como
  passo obrigatório antes da subida.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Gerar massa de eventos de pedidos (Priority: P1)

Como engenheiro de dados, quero executar um simulador que gere eventos realistas do ciclo de vida
de várias pedidos simultâneos (recebimento, transporte e entrega) e grave cada evento como arquivo
JSON na pasta `dados/eventos`, para ter uma fonte de dados contínua que alimente a arquitetura
orientada a eventos.

**Why this priority**: sem dados de origem nenhuma outra etapa pode ser demonstrada ou testada;
é a base de todo o pipeline.

**Independent Test**: executar o simulador com os parâmetros padrão e verificar que a pasta
`dados/eventos` recebe 10 arquivos JSON válidos, com pedidos diferentes intercaladas e cada pedido
seguindo uma sequência de etapas coerente.

**Acceptance Scenarios**:

1. **Given** a pasta `dados/eventos` vazia, **When** o simulador é iniciado com parâmetros
   padrão, **Then** 10 arquivos JSON de eventos são criados na pasta e o simulador encerra.
2. **Given** o simulador em execução, **When** os eventos de uma mesma pedido são ordenados por
   data/hora, **Then** a sequência respeita o ciclo de vida (recebida → em transporte → entregue,
   com etapas intermediárias opcionais) e nenhuma etapa ocorre antes da anterior.
3. **Given** o simulador configurado para N pedidos simultâneos, **When** ele roda, **Then** os
   eventos de pedidos distintas aparecem intercalados no tempo.
4. **Given** o simulador em execução contínua (opção explícita), **When** o usuário o interrompe, **Then** ele encerra sem
   deixar arquivos parcialmente escritos na pasta.

---

### User Story 2 - Ingerir arquivos de eventos com controle operacional (Priority: P2)

Como operador do pipeline, quero que um serviço de ingestão leia automaticamente os arquivos JSON
à medida que aparecem em `dados/eventos` e publique os eventos no barramento de mensagens, e quero
uma API de controle para monitorar, ativar, pausar e retomar essa ingestão.

**Why this priority**: é o elo entre a origem dos dados e o barramento; sem ele os eventos não
fluem pela arquitetura. A API de controle permite demonstrar e operar o pipeline.

**Independent Test**: com o simulador gerando arquivos e o barramento disponível, ativar a
ingestão pela API de controle, verificar que o status indica "em execução", pausar e confirmar
que novos arquivos não são ingeridos até a retomada.

**Acceptance Scenarios**:

1. **Given** a ingestão ativa, **When** um novo arquivo de evento é criado em `dados/eventos`,
   **Then** o evento é publicado no barramento em até 30 segundos.
2. **Given** a ingestão ativa, **When** o operador consulta o status pela API de controle,
   **Then** recebe o estado atual (ativa, pausada, com falha) e informações de saúde da ingestão.
3. **Given** a ingestão ativa, **When** o operador solicita a pausa, **Then** nenhum novo evento é
   publicado enquanto pausada, e os arquivos criados nesse período são ingeridos após a retomada.
4. **Given** a ingestão não configurada, **When** o operador solicita a ativação, **Then** a
   ingestão é criada com a configuração versionada do projeto e passa a processar os arquivos.
5. **Given** um arquivo já ingerido, **When** a ingestão é reiniciada, **Then** o arquivo não é
   publicado novamente.
6. **Given** um arquivo com conteúdo inválido, **When** a ingestão o processa, **Then** ele é
   desviado para um destino de erros e o fluxo dos demais arquivos continua.

---

### User Story 3 - Disponibilizar eventos em um tópico do barramento (Priority: P3)

Como engenheiro de dados, quero um cluster de mensageria mínimo (um único nó) rodando localmente,
com um tópico de eventos da loja configurado, para que os eventos ingeridos fiquem
disponíveis para consumidores.

**Why this priority**: é a infraestrutura de distribuição dos eventos; necessária para a API de
consulta, mas pode ser validada isoladamente publicando e lendo mensagens.

**Independent Test**: subir o cluster, verificar que o tópico existe com a configuração esperada,
publicar um evento de teste e lê-lo de volta.

**Acceptance Scenarios**:

1. **Given** o ambiente iniciado, **When** o operador lista os tópicos, **Then** o tópico de
   eventos da loja existe com a retenção configurada.
2. **Given** eventos publicados no tópico, **When** um consumidor lê o tópico, **Then** os eventos
   de uma mesma pedido são entregues na ordem em que foram publicados.
3. **Given** a retenção configurada, **When** o tempo de retenção expira, **Then** os eventos mais
   antigos deixam de estar disponíveis no tópico. A verificação é automatizada com uma retenção
   curta (ex.: 30 s) aplicada só durante o teste, sem esperar os 15 minutos reais.

---

### User Story 4 - Consultar eventos e status de pedidos via API (Priority: P4)

Como analista ou sistema cliente, quero uma API que consuma o tópico de eventos e ofereça
endpoints de consulta, para saber o status atual de cada pedido, seu histórico de eventos e
indicadores agregados.

**Why this priority**: entrega o valor final ao consumidor dos dados, mas depende das etapas
anteriores para ter dados reais.

**Independent Test**: com eventos no tópico, consultar a API e verificar que o status e o
histórico retornados correspondem aos eventos publicados.

**Acceptance Scenarios**:

1. **Given** eventos de um pedido consumidos, **When** o cliente consulta esse pedido, **Then**
   recebe seu status atual e o histórico de eventos em ordem cronológica.
2. **Given** várias pedidos em etapas diferentes, **When** o cliente lista pedidos filtrando por
   status, **Then** recebe apenas as pedidos naquele status, com paginação.
3. **Given** eventos consumidos, **When** o cliente consulta o resumo, **Then** recebe a contagem
   de pedidos por status e o total de eventos processados.
4. **Given** um pedido inexistente, **When** o cliente a consulta, **Then** recebe uma resposta de
   "não encontrado" em formato de erro padronizado.
5. **Given** um pedido cujo evento mais recente ocorreu há mais de 15 minutos, **When** o cliente
   a consulta (com ou sem restart da API no intervalo), **Then** recebe "não encontrado" e ela não
   aparece na listagem nem no resumo.
6. **Given** o mesmo evento entregue mais de uma vez, **When** a API o consome, **Then** o
   histórico do pedido não apresenta duplicidade.

---

### User Story 5 - Documentação para operar e testar a arquitetura (Priority: P5)

Como membro do time, quero um README que explique como subir toda a infraestrutura, executar a
simulação, rodar os testes e verificar o status de cada etapa, para conseguir reproduzir e
demonstrar a arquitetura sem ajuda.

**Why this priority**: viabiliza a adoção e a demonstração, mas só agrega valor após as demais
etapas existirem.

**Independent Test**: uma pessoa que não participou do desenvolvimento segue apenas o README em
uma máquina limpa (com os pré-requisitos instalados) e consegue ver eventos fluindo até a API.

**Acceptance Scenarios**:

1. **Given** uma máquina com os pré-requisitos listados, **When** a pessoa segue o README,
   **Then** consegue subir o ambiente completo com um único comando.
2. **Given** o ambiente em execução, **When** a pessoa segue a seção de verificação, **Then**
   consegue checar o status do simulador, da ingestão, do tópico e da API de consulta.
3. **Given** o repositório, **When** a pessoa segue a seção de testes, **Then** consegue executar
   os testes automatizados e interpretar o resultado.
4. **Given** o repositório clonado no Windows pelo Git for Windows com `core.autocrlf=true`,
   **When** a pessoa executa o comando de subida pelo WSL2, **Then** todos os serviços sobem
   (incluindo a criação dos tópicos) sem erros causados por fim de linha CRLF.

---

### Edge Cases

- Arquivo JSON malformado ou fora do contrato de evento em `dados/eventos`: deve ir para o destino
  de erros, sem interromper a ingestão.
- Arquivo ainda sendo escrito quando a ingestão o detecta: não pode ser lido parcialmente.
- Barramento indisponível com a ingestão ativa: a ingestão deve reportar falha no status e retomar
  sem perda de eventos quando o barramento voltar. A garantia vale com o serviço de ingestão em
  execução durante a queda; a falha simultânea do serviço de ingestão é risco aceito, fora do
  escopo.
- API de consulta reiniciada: deve reconstruir o estado a partir dos eventos ainda disponíveis no
  tópico.
- Eventos de um pedido que expiraram por retenção: a API de consulta remove esses eventos do
  histórico; o status passa a refletir o evento mais recente ainda retido, e a pedido deixa de
  existir (consulta retorna "não encontrado") quando todos os seus eventos expiram. O resultado é
  o mesmo antes e depois de um restart da API.
- Evento duplicado (mesmo identificador): deve ser ignorado pela API de consulta.
- Pedido de pausa com a ingestão já pausada (ou retomada com ela ativa): deve responder sem erro
  e sem alterar o estado.
- Arquivos acumulados na pasta (ex.: criados durante uma pausa, até 10 arquivos): a ingestão deve
  processar o acúmulo sem falhar. Grandes volumes de ingestão estão fora do escopo.
- Evento de pedido recebido fora de ordem (ex.: "entregue" sem "em transporte"): deve ser aceito e
  registrado, refletindo a etapa mais recente pela data/hora do evento.

## Requirements *(mandatory)*

### Functional Requirements

**Simulação de dados**

- **FR-001**: O simulador MUST gerar eventos do ciclo de vida de pedidos de uma loja,
  cobrindo no mínimo as etapas: pedido recebida, saída para transporte, em trânsito (atualização
  de posição), saída para entrega, entregue e falha na entrega.
- **FR-002**: O simulador MUST manter várias pedidos em andamento simultaneamente, com quantidade
  de pedidos e intervalo entre eventos configuráveis.
- **FR-003**: Cada evento MUST seguir o contrato de evento do projeto: identificador único do
  evento, tipo, versão do contrato, data/hora de ocorrência em UTC, origem, identificador do pedido
  e dados específicos da etapa (ex.: origem, destino, peso, localização, motivo de falha).
- **FR-004**: O simulador MUST gravar cada evento como um arquivo JSON individual em
  `dados/eventos`, de forma que nenhum arquivo seja visível em estado parcialmente escrito.
- **FR-005**: Por padrão, o simulador MUST gerar 10 eventos e encerrar. Ele MUST permitir também
  execução por outra quantidade/duração e execução contínua até interrupção (ambas por opção
  explícita), e MUST encerrar de forma limpa ao ser interrompido.

**Ingestão e controle**

- **FR-006**: A ingestão MUST detectar e processar automaticamente novos arquivos em
  `dados/eventos`, publicando cada evento no tópico de eventos da loja.
- **FR-007**: A ingestão MUST usar o identificador do pedido como chave de particionamento, para
  preservar a ordem dos eventos por pedido.
- **FR-008**: Cada arquivo MUST ser ingerido no máximo uma vez em operação normal; após
  processado, o arquivo MUST ser movido para a pasta de backup `dados/backup` (ou para
  `dados/erros`, se inválido). Os arquivos de backup MUST ser mantidos sem limpeza automática;
  a remoção é manual e documentada.
- **FR-009**: Eventos inválidos MUST ser direcionados a um destino de erros com o motivo da falha.
- **FR-010**: A ingestão MUST NOT ser ativada automaticamente na subida do ambiente; ela só
  começa após a ação de ativação na API de controle. A API de controle MUST permitir:
  consultar status da ingestão, criar/ativar a ingestão, pausar, retomar, reiniciar e remover a
  ingestão.
- **FR-011**: A API de controle MUST expor verificações de saúde (processo vivo e pronto, este
  último checando a disponibilidade do serviço de ingestão e do barramento).
- **FR-012**: Operações que alteram estado na API de controle MUST exigir uma chave de acesso
  configurável; consultas de status e saúde podem ser abertas no ambiente local.
- **FR-013**: Operações idempotentes (pausar algo pausado, retomar algo ativo) MUST retornar
  sucesso sem efeito colateral.

**Barramento de mensagens**

- **FR-014**: O ambiente MUST incluir um cluster de mensageria com um único nó, adequado apenas
  para simulação local.
- **FR-015**: O tópico de eventos da loja MUST ser criado automaticamente na subida do
  ambiente, com partições, retenção e nome declarados no repositório.
- **FR-016**: As mensagens do tópico de eventos da loja MUST ser retidas por 15 minutos;
  após esse período, eventos mais antigos deixam de estar disponíveis no tópico. O valor MUST ser
  configurável, inclusive para uma retenção curta usada nos testes automatizados de expiração.

**API de consulta**

- **FR-017**: A API de consulta MUST consumir continuamente o tópico de eventos e manter uma visão
  atualizada do status de cada pedido.
- **FR-018**: A API de consulta MUST oferecer: detalhe de um pedido (status atual e última
  atualização), histórico de eventos de um pedido em ordem cronológica, listagem paginada de
  pedidos com filtro por status, e resumo com contagem de pedidos por status e total de eventos.
- **FR-019**: A API de consulta MUST descartar eventos duplicados com base no identificador único
  do evento.
- **FR-020**: Erros da API de consulta MUST seguir um formato padronizado, com códigos semânticos
  (ex.: não encontrado, parâmetro inválido).
- **FR-021**: A API de consulta MUST expor verificações de saúde e o atraso (lag) de consumo em
  relação ao tópico.
- **FR-022**: Ao reiniciar, a API de consulta MUST reconstruir sua visão a partir dos eventos
  ainda retidos no tópico.
- **FR-022a**: A API de consulta MUST descartar continuamente (verificação no máximo a cada
  1 minuto) os eventos cuja data/hora de ocorrência seja mais antiga que a janela de retenção
  (mesmo valor configurado para o tópico, padrão 15 minutos), recalculando status, histórico,
  listagem e resumo; pedidos sem eventos restantes MUST ser removidas.

**Operação, observabilidade e documentação**

- **FR-023**: Todos os componentes de infraestrutura e as APIs MUST subir juntos com um único
  comando e expor verificações de saúde que indiquem quando estão prontos; o simulador MUST ser
  executável sob demanda com um único comando documentado.
- **FR-023a**: O comando único de subida MUST funcionar em Linux, macOS e Windows (WSL2 + Docker
  Desktop), independentemente da configuração de fim de linha do Git do host; scripts e arquivos
  executados dentro dos containers MUST manter fim de linha LF no checkout.
- **FR-024**: Todos os componentes de aplicação (simulador e APIs) MUST emitir logs estruturados contendo o identificador do
  evento e um identificador de correlação propagado da origem até a API de consulta.
- **FR-025**: Cada componente de aplicação MUST expor métricas de eventos produzidos/consumidos,
  erros e eventos desviados para o destino de erros.
- **FR-026**: O README MUST conter: pré-requisitos, o passo obrigatório de copiar `.env.example`
  para `.env` antes da primeira subida, como subir e derrubar o ambiente, como
  executar o simulador, como operar a ingestão via API de controle, como consultar a API de
  consulta, como rodar os testes e como verificar o status de cada etapa.

### Key Entities *(include if feature involves data)*

- **Pedido**: unidade transportada. Atributos: identificador, origem, destino, peso, descrição,
  status atual, data/hora da última atualização. Possui muitos eventos.
- **Evento de Pedido**: fato imutável ocorrido no ciclo de vida do pedido. Atributos: identificador
  único, tipo de evento, versão do contrato, data/hora de ocorrência (UTC), origem do evento,
  identificador de correlação, identificador do pedido e dados específicos da etapa (localização,
  veículo, motivo de falha etc.).
- **Status da Pedido**: estado derivado do evento mais recente: recebida, em transporte, em
  trânsito, saiu para entrega, entregue, falha na entrega.
- **Ingestão (conector)**: processo que lê os arquivos e publica no barramento. Atributos: nome,
  estado (ativa, pausada, iniciando, com falha, inexistente), configuração versionada, contagem de
  arquivos pendentes, em backup e com erro.
- **Tópico de Eventos**: canal onde os eventos são publicados. Atributos: nome, número de
  partições, retenção.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Uma pessoa nova no projeto sobe o ambiente completo e vê eventos chegando à API de
  consulta em até 15 minutos seguindo apenas o README.
- **SC-002**: Um evento gerado pelo simulador fica visível na API de consulta em até 60 segundos
  em 95% dos casos com a ingestão ativa.
- **SC-003**: Com um volume pequeno de simulação (10 eventos por execução), o
  pipeline entrega 100% dos eventos à API de consulta sem perda. Testes de pedido, estresse, longa
  duração ou grandes ingestões estão fora do escopo.
- **SC-004**: 100% dos eventos gerados durante uma execução de teste são encontrados no histórico
  da API de consulta (enquanto dentro do período de retenção), sem duplicidades.
- **SC-005**: Após pausar a ingestão, nenhum evento novo é publicado; após retomar, 100% dos
  arquivos acumulados durante a pausa são ingeridos.
- **SC-006**: 100% dos arquivos inválidos são desviados ao destino de erros sem interromper a
  ingestão dos arquivos válidos.
- **SC-007**: O status de cada etapa (simulador, ingestão, tópico, API de consulta) pode ser
  verificado em menos de 1 minuto usando os comandos documentados.
- **SC-008**: As consultas de detalhe e de listagem respondem em menos de 1 segundo com o volume
  de simulação (até algumas centenas de pedidos em memória).

## Assumptions

- O objetivo é demonstrar e simular a arquitetura localmente com volumes pequenos de dados (10
  eventos por simulação); alta disponibilidade, múltiplos nós, operação em produção e testes de pedido/estresse estão fora do
  escopo.
- Plataformas de host suportadas: Linux, macOS e Windows via WSL2 + Docker Desktop (inclusive com
  clone feito pelo Git for Windows); Windows sem WSL2 está fora do escopo.
- Restrições tecnológicas definidas pelo solicitante e pela constituição do projeto: Python,
  FastAPI para as APIs, Kafka (cluster com 1 broker) como barramento, Kafka Connect para ingestão
  dos arquivos e Docker/Docker Compose para executar todos os componentes.
- O simulador é executado pelo próprio usuário (localmente ou em container) e grava na pasta
  `dados/eventos` compartilhada com o serviço de ingestão.
- Os arquivos ingeridos são movidos para `dados/backup` e os inválidos para `dados/erros`,
  evitando reprocessamento e acúmulo na pasta de entrada; o crescimento de `dados/backup` é
  aceito no contexto de simulação local.
- A API de consulta mantém sua visão em memória, limitada à mesma janela de retenção do tópico;
  persistência em banco de dados está fora do escopo desta feature.
- A chave de acesso da API de controle é configurada por variável de ambiente; não há gestão de
  usuários nem perfis de acesso.
- Os dados gerados são fictícios; não há dados pessoais reais nem requisitos de conformidade.
- Interface gráfica (dashboard) está fora do escopo; a interação é via API e linha de comando.
