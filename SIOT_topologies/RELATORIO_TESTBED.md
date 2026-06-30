# Relatório Técnico — Testbed de Avaliação de *Rekeying* em Grupo (SIOT_topologies)

> **Repositório:** `lnnaves/Testbed_mestrado` · **Pasta:** `SIOT_topologies`
> **Contexto:** redes ad hoc de drones (Containernet + Mininet-WiFi)

---

## 1. Visão geral — o que este testbed faz

Este testbed mede e compara o **custo de *rekeying* (re-chaveamento) de grupo** em uma rede de drones quando um membro é **revogado** (expulso por comportamento malicioso). Ele responde a uma pergunta central de pesquisa:

> *Quando um drone é revogado de um grupo, quanto custa redistribuir a nova chave de grupo aos membros restantes — e como esse custo cresce com o tamanho do grupo N?*

A comparação é entre **dois esquemas de re-chaveamento**:

| Esquema | Estratégia | Custo teórico de mensagens |
|---|---|---|
| **naive** | Gera nova chave de grupo e cifra **uma vez para cada membro restante** | **O(n)** |
| **lkh** (Logical Key Hierarchy) | Mantém uma **árvore binária de chaves**; re-chaveia só os nós no caminho da folha afetada até a raiz | **O(log n)** |

A campanha varre a matriz **{naive, lkh} × N∈{4, 8, 16, 32} × R repetições** e produz dois conjuntos de dados prontos para plotar:

- **Figura 1** — custo de rekey (mensagens, operações criptográficas, tempo) vs N.
- **Figura 2** — perda de pacotes ao longo do tempo, alinhada ao instante do revoke.

Um ponto importante de **honestidade científica** (declarado no próprio código): a **criptografia é real** (AES-GCM via biblioteca `cryptography`), mas o protocolo é um **esquema de referência** para *avaliar* o custo de rekeying, não uma nova proposta padronizada.

---

## 2. Arquitetura — como as peças se encaixam

```
+-----------------------------------------------------------------+
|  HOST (sua maquina, com sudo)                                   |
|                                                                 |
|  run_campaign.py  --orquestra-->  topology_group_revocation.py  |
|       |                                    |                    |
|       |                              usa funcoes de             |
|       |                                 common.py               |
|       |                                    |                    |
|       |                          +---------+---------+          |
|       |                          v                   v          |
|       |              +-------------------+  +------------------+ |
|       |              | CONTAINER auth1   |  | CONTAINER droneN | |
|       |              | (auth-server:     |  | (drone-sec:      | |
|       |              |  latest)          |  |  latest)         | |
|       |              |                   |  |                  | |
|       |              | group_auth.py     |  | group_auth.py    | |
|       |              |  --role           |  |  --role member   | |
|       |              |  auth-server      |  | traffic_agent.py | |
|       |              |                   |  | metrics_agent.py | |
|       |              | gera:             |  | malicious_agent  | |
|       |              |  protocol_        |  |                  | |
|       |              |  latency.csv      |  | gera:            | |
|       |              +-------------------+  |  traffic_loss.csv| |
|       |                          |         +------------------+ |
|       |                          | (CSVs vivem em /tmp/ no      |
|       |                          |  container, invisiveis ao    |
|       |                          |  host)                       |
|       |                          v                              |
|       |         collect_incontainer_csvs() copia p/ o host      |
|       |                          |                              |
|       v                          v                              |
|  figure1_rekey_cost.csv   campaign-results/raw/.../run-N/*.csv  |
|  figure2_packet_loss.csv                                        |
|       |                                                         |
|       v                                                         |
|  plot_figures.py  -->  figure1.png / figure2.png                |
+-----------------------------------------------------------------+
```

**Modelo de rede:** cada drone e a autoridade central são **contêineres Docker** que também são **estações Wi-Fi** do Mininet-WiFi. A rede é **ad hoc (IBSS)**, sem Access Point. A autoridade central (`auth1`) é uma entidade **lógica** — participa da rede ad hoc como qualquer nó, não é infraestrutura.

---

## 3. Os arquivos e suas funções

### 3.1 `scripts/group_auth.py` — o coração do protocolo (roda DENTRO dos contêineres)

É o agente que implementa a autenticação de grupo e os dois esquemas de rekeying. É o arquivo que **gera as métricas de custo** (`protocol_latency.csv`).

**Utilitários de criptografia e log:**

- **`now()`** — timestamp UTC ISO-8601 (usado em todas as linhas de CSV/log).
- **`log()`** — imprime mensagens de log em stdout.
- **`_new_key()`** — gera uma chave AES-GCM de 128 bits.
- **`_encrypt()`** — cifra dados com AES-GCM e nonce aleatório; **conta como uma operação criptográfica real** (é assim que `crypto_ops` é medido de forma honesta).
- **`emit_event()`** — escreve **uma linha por evento** no `protocol_latency.csv`, com as colunas de custo (`rekey_msgs`, `crypto_ops`, `rekey_ms`, `group_size`, etc.). É a fonte da Figura 1.

**Implementação do LKH (árvore de chaves):**

- **`LKHNode`** (classe) — um nó da árvore binária de chaves. Folhas = KEK individual de um drone; nós internos = KEKs intermediárias persistentes; raiz = origem da chave de grupo.
  - **`LKHNode.is_leaf()`** — indica se o nó é folha.
- **`LKHTree`** (classe) — a Logical Key Hierarchy propriamente dita.
  - **`_build_balanced()`** — constrói uma árvore binária **balanceada** sobre as folhas (altura ~ log2(N)).
  - **`_rebuild()`** — reconstrói a topologia a partir das folhas atuais, **preservando as KEKs individuais** dos membros.
  - **`_path_to_root()`** — lista os nós internos da folha até a raiz (o caminho a ser re-chaveado).
  - **`_rekey_path()`** — **re-chaveia** os nós no caminho: gera chave nova para cada nó e a cifra sob a chave de cada filho. **Cada cifragem conta como 1 mensagem e 1 operação cripto** -> é aqui que o custo O(log n) é medido.
  - **`add_member()`** — adiciona membro (cria folha, reconstrói, re-chaveia caminho).
  - **`remove_member()`** — remove membro e re-chaveia para que o removido **não** derive as novas chaves.
  - **`group_key_fingerprint()`** — hash curto da chave de grupo (para correlação em logs, sem expor a chave).
  - **`height()`** — altura atual da árvore.

**Estado do grupo no servidor:**

- **`GroupState`** (classe) — mantém membros, revogados, época (epoch) e o estado criptográfico.
  - **`_rekey_naive_add()` / `_rekey_naive_remove()`** — rekey naive: nova chave de grupo cifrada para **cada** membro (O(n)); mede msgs/ops/tempo.
  - **`_rekey_lkh_add()` / `_rekey_lkh_remove()`** — rekey via árvore LKH (O(log n)); mede msgs/ops/tempo.
  - **`_do_rekey_add()` / `_do_rekey_remove()`** — despacham para naive **ou** lkh conforme o esquema configurado.
  - **`register()`** — registro inicial de um membro (**não** dispara rekey).
  - **`join()`** — entrada de membro (dispara rekey de adição).
  - **`leave()`** — saída voluntária (dispara rekey de remoção).
  - **`revoke()`** — **revogação** pela autoridade: remove o alvo, marca como revogado e dispara rekey de remoção. **É o evento central medido na campanha.**
  - **`status()`** — retorna estado atual do grupo (usado nos heartbeats).

**Servidor e cliente TCP:**

- **`AuthTCPHandler`** (classe) — handler TCP que recebe requisições JSON e chama `register/join/leave/revoke/status`.
  - **`AuthTCPHandler.handle()`** — processa uma requisição e responde.
- **`parse_host_port()`** — separa `host:porta`.
- **`send_request()`** — envia uma requisição JSON ao auth e mede o tempo de resposta.

**Modos de execução (escolhidos por `--role`/`--event`):**

- **`run_auth_server()`** — sobe o servidor TCP 9000 e mantém o `GroupState`.
- **`run_member()`** — registra o drone e entra em loop de **heartbeat**.
- **`run_join()`** — executa um **join**.
- **`run_leave()`** — executa um **leave**.
- **`run_revoke()`** — executa um **revoke** (rodado dentro do contêiner do auth).
- **`main()`** — *entry point*: faz o parsing dos argumentos e roteia para o modo correto.

---

### 3.2 `common.py` — biblioteca de orquestração da topologia (roda no HOST)

Concentra todas as funções reutilizadas pelos cenários `topology_*.py`.

**Construção da rede e dos nós:**

- **`create_network()`** — cria a rede Containernet com modelo de propagação logDistance.
- **`add_controller()`** — adiciona o controlador mínimo.
- **`add_drone()`** — cria **um drone** = contêiner Docker + estação Wi-Fi.
- **`add_auth_server()`** — cria a **autoridade central** como contêiner + estação Wi-Fi.
- **`create_base_group_topology()`** — monta a topologia base com o auth + **N drones** (parâmetro `num_drones`). Para N>4, distribui drones extras em círculo ao redor do auth.

**Configuração e bootstrap da rede ad hoc:**

- **`configure_adhoc_network()`** — coloca todos os nós no mesmo SSID ad hoc (substitui o AP).
- **`start_network()`** — constrói e inicia a rede.
- **`initialize_adhoc_experiment()`** — faz o **bootstrap completo**: configura ad hoc, inicia rede, prepara contêineres, inicia métricas, testa conectividade e sobe o auth-server (repassando `rekey_scheme`).

**Preparação dos contêineres:**

- **`prepare_node()` / `prepare_all()`** — criam diretórios de log e registram contexto (IP, rotas, interfaces) em cada nó.

**Disparo do protocolo (chamam o `group_auth.py` dentro dos contêineres):**

- **`start_auth_server()`** — sobe o auth-server com `--rekey-scheme`.
- **`start_group_member()`** — inicia um drone como membro.
- **`request_join()` / `request_leave()`** — disparam join/leave.
- **`revoke_member()`** — dispara a **revogação** de um drone pela autoridade.

**Tráfego (chamam `traffic_agent.py` / `malicious_agent.py`):**

- **`start_receiver()` / `start_sender()`** — iniciam recepção/envio de tráfego legítimo.
- **`start_malicious_traffic()`** — inicia tráfego malicioso (drone usando chave antiga após revogação).

**Métricas e utilidades:**

- **`start_metrics()` / `start_metrics_all()`** — iniciam o agente de métricas em cada nó.
- **`set_wait_scale()` / `wait()`** — controlam a duração das esperas; o `--fast` aplica escala 0.2 para encurtar a campanha.
- **`test_connectivity()`** — teste básico de ping entre nós.
- **`finish()`** — encerra a rede (e abre CLI se solicitado).

**Métricas estruturadas (geram CSV no host):**

- **`ensure_metrics_dir()` / `build_metrics_file()`** — gerenciam o diretório/arquivo de métricas.
- **`append_metric_csv()`** — grava uma linha no CSV de métricas.
- **`record_event_metric()`** — registra eventos de protocolo (start, revoke, etc.).
- **`measure_ping_rtt()` / `measure_rtt_matrix()`** — medem RTT entre pares de nós e registram.

**Configuração experimental e execução:**

- **`parse_experiment_args()`** — define **todos** os argumentos de linha de comando (incluindo `--rekey-scheme`, `--num-drones`, `--fast`, `--wait-scale`).
- **`run_experiment_runs()`** — executa N repetições do cenário.
- **`move_node_in_steps()`** — move um nó por interpolação (mobilidade simulada; não usado no cenário de revogação).

**Coleta de artefatos:**

- **`collect_incontainer_csvs()`** — copia os CSVs gerados **dentro** dos contêineres (`protocol_latency.csv`, `traffic_loss.csv`) para o host. Inclui limpeza de lixo de terminal (sequências de escape ANSI e CR) que poderiam corromper o cabeçalho dos CSVs.

---

### 3.3 `topology_group_revocation.py` — o cenário experimental (roda no HOST)

Orquestra **um run** do cenário de revogação, usando as funções do `common.py`.

- **`run()`** — executa o cenário completo de um run:
  1. cria a topologia com N drones (`drone3` marcado como `compromised_member`);
  2. inicia o experimento ad hoc e o auth-server com o esquema de rekey escolhido;
  3. forma o grupo (todos os drones fazem join);
  4. inicia tráfego normal;
  5. `drone3` passa a emitir **tráfego malicioso**;
  6. a autoridade **revoga `drone3`** (evento medido);
  7. mede RTT/perda antes e depois da revogação;
  8. coleta os CSVs in-container para o host (`collect_incontainer_csvs`);
  9. encerra a rede.
- **`run_once()`** (função interna) — adapta `run()` para a interface de repetições.
- Bloco **`__main__`** — faz o parsing dos argumentos e chama `run_experiment_runs()`.

---

### 3.4 `run_campaign.py` — orquestrador da campanha completa (roda no HOST)

Varre a matriz **esquema × N × repetições**, executa o cenário de revogação para cada célula e consolida os CSVs finais.

- **`info()`** — log padronizado da campanha.
- **`run_cell()`** — executa o cenário para um par **(esquema, N)** com R repetições, gravando os CSVs por run num diretório próprio da célula (`raw/<esquema>-N<tamanho>/`).
- **`_find_protocol_csvs()` / `_find_loss_csvs()`** — localizam recursivamente os CSVs coletados de cada célula.
- **`_run_id_from_path()`** — infere o `run_id` a partir do caminho (ex.: `.../run-2/...`).
- **`_iso_to_epoch()`** — converte timestamp ISO-8601 para epoch (segundos).
- **`_revoke_epoch_by_run()`** — mapeia cada run ao **instante do revoke** (lido do `protocol_latency.csv`), usado para alinhar a Figura 2 em t=0 no momento da revogação.
- **`consolidate_figure1()`** — lê os `protocol_latency.csv`, filtra eventos **`revoke`** e escreve uma linha por evento em `figure1_rekey_cost.csv` (`rekey_scheme, group_size, run_id, rekey_msgs, crypto_ops, rekey_ms`).
- **`consolidate_figure2()`** — lê os `traffic_loss.csv` e escreve janelas de perda com **tempo relativo ao revoke** em `figure2_packet_loss.csv`. Se não achar o instante do revoke, cai num *fallback* (alinha pela primeira janela) e avisa.
- **`main()`** — define os argumentos da campanha (`--schemes`, `--sizes`, `--runs`, `--fast`, `--dry-run`, etc.), executa o sweep e escreve os dois CSVs agregados.

---

### 3.5 Demais arquivos

- **`plot_figures.py`** — lê `figure1_rekey_cost.csv` e `figure2_packet_loss.csv` e gera os PNGs (`plot_figure1`, `plot_figure2`, `_savefig`).
- **`docker/drone/Dockerfile` e `docker/auth-server/Dockerfile`** — definem as imagens `drone-sec:latest` e `auth-server:latest`, instalando `python3-cryptography` e copiando os scripts (`scripts/`) para `/opt/drone-sec/bin/`. **O contexto de build deve ser a pasta `SIOT_topologies/`.**
- **`scripts/`** — `group_auth.py`, `traffic_agent.py`, `metrics_agent.py`, `malicious_agent.py` (todos congelados dentro das imagens no momento do build).
- Outros cenários: `topology_group_join.py`, `topology_group_leave.py`, `topology_group_auth_centralized.py`, `topology_group_auth_distributed.py`, `topology_group_partition_merge.py`.

---

## 4. Fluxo de dados (de onde vem cada número)

1. O **auth-server** (`group_auth.py` dentro do contêiner `auth1`), ao processar o `revoke`, mede o custo (`rekey_msgs`, `crypto_ops`, `rekey_ms`) e grava em `/tmp/drone-logs/protocol_latency.csv`.
2. Os **drones** geram `traffic_loss.csv` (perda por janela) via agente de tráfego.
3. Esses CSVs vivem **dentro** dos contêineres -> invisíveis ao host.
4. Ao fim de cada run, **`collect_incontainer_csvs()`** copia esses CSVs para `campaign-results/raw/<esquema>-N<tamanho>/run-<id>/`.
5. **`run_campaign.py`** lê esses arquivos e consolida em `figure1_rekey_cost.csv` (custo de rekey) e `figure2_packet_loss.csv` (perda alinhada ao revoke).
6. **`plot_figures.py`** transforma os dois CSVs nos gráficos finais.

### Esquema do `protocol_latency.csv` (gerado pelo auth-server)

```
timestamp_utc, scenario, role, event, drone_id, group_id, epoch,
elapsed_ms, status, rekey_scheme, group_size, rekey_msgs, crypto_ops,
rekey_ms, extra
```

A linha relevante para a Figura 1 é a do evento `revoke`, que carrega `rekey_msgs`, `crypto_ops` e `rekey_ms`.

---

## 5. Estado atual e problemas resolvidos

O pipeline está **funcionando de ponta a ponta**. Resumo da depuração realizada:

| # | Problema | Causa raiz | Solução |
|---|---|---|---|
| 1 | `pip` *externally-managed* | Python do sistema protegido (PEP 668) | usar apt/venv |
| 2 | `unrecognized arguments` | `common.py` sem `--rekey-scheme/--num-drones/--fast` no parser | restaurar `parse_experiment_args` completo |
| 3 | `TypeError: num_drones` | `create_base_group_topology` sem o parâmetro `num_drones` | versão do branch `copilot/lkh-rekeying-evaluation` |
| 4 | `ImportError: collect_incontainer_csvs` | função ausente nessa versão do `common.py` | **unir** as duas metades do `common.py` (cada branch tinha uma) |
| 5 | imagens Docker antigas | scripts congelados na imagem | **rebuild** de `drone-sec` e `auth-server` |
| 6 | `figure1` com 0 linhas + "revoke not found" | **lixo de terminal** no topo dos CSVs coletados quebrava o `csv.DictReader` | limpeza robusta em `collect_incontainer_csvs` (descartar linhas até o cabeçalho real) |
| 7 | `PermissionError` no PNG | CSVs/pastas criados como **root** (campanha roda com `sudo`) | `chown -R "$USER:$USER"` + rodar `plot_figures.py` sem sudo |

**Lição estrutural importante:** o `common.py` correto estava **fragmentado** entre dois branches (`copilot/lkh-rekeying-evaluation` tinha `num_drones`; `lkh-rekeying-evaluation` tinha `collect_incontainer_csvs` + `rekey_scheme`). A versão final unificada juntou as duas metades — encerrando o ciclo de "resolve um erro, aparece outro".

---

## 6. Como executar (referência rápida)

```bash
# 1) (uma vez) buildar as imagens — a partir de SIOT_topologies/
docker build -t drone-sec:latest   -f docker/drone/Dockerfile .
docker build -t auth-server:latest -f docker/auth-server/Dockerfile .

# 2) teste minimo (1 esquema, N=4, 1 run)
sudo python3 run_campaign.py --schemes naive --sizes 4 --runs 1 --results-dir ./campaign-test --fast

# 3) campanha completa (naive vs lkh, N=4..32, 10 runs) — pode levar 1-2h
sudo python3 run_campaign.py --schemes naive lkh --sizes 4 8 16 32 --runs 10 --results-dir ./campaign-results --fast

# 4) devolver posse (porque rodou com sudo) e gerar figuras SEM sudo
sudo chown -R "$USER:$USER" ./campaign-results
python3 plot_figures.py --results-dir ./campaign-results --fig1-logy
```

### Verificações úteis

```bash
# o common.py local tem tudo? (todos devem ser > 0)
grep -c "num_drones" common.py
grep -c "collect_incontainer_csvs" common.py
grep -c "rekey_scheme" common.py

# import sanity check (sem subir container) — deve imprimir "OK: True True"
python3 -c "import common; print('OK:', hasattr(common,'collect_incontainer_csvs'), 'num_drones' in common.create_base_group_topology.__code__.co_varnames)"

# os CSVs agregados tem dados?
wc -l ./campaign-results/figure1_rekey_cost.csv ./campaign-results/figure2_packet_loss.csv
cat ./campaign-results/figure1_rekey_cost.csv
```

---

## 7. Resultado esperado da campanha

Ao final, `figure1_rekey_cost.csv` deve ter **8 linhas de dados** (naive e lkh × N∈{4,8,16,32}), evidenciando a diferença de escalabilidade:

- **naive:** `rekey_msgs ~ N-1` (cresce **linearmente** com o grupo).
- **lkh:** `rekey_msgs ~ O(log N)` (cresce muito mais devagar).

Esse contraste — visível na Figura 1, especialmente com eixo Y logarítmico (`--fig1-logy`) — é o **resultado central** que valida a vantagem do LKH sobre o re-chaveamento ingênuo em grupos de drones. A Figura 2 complementa mostrando a perda de pacotes em torno do instante da revogação.

---

## 8. Observações finais e recomendações

- **Escalabilidade do teste:** N=32 sobe **33 contêineres** simultâneos. Se a máquina ficar saturada em N=32, rode até N=16 primeiro e N=32 separadamente.
- **Versionamento:** mantenha a `main` como fonte única e correta. Cuidado com `git pull` que possa trazer versões antigas de branches paralelos por cima.
- **Higiene de saída:** os diretórios `campaign-results/`, `campaign-test/` e `results/` são **saídas** — convém mantê-los no `.gitignore` (não versionar CSVs/PNGs gerados).
- **Rebuild de imagem:** sempre que alterar qualquer script em `scripts/`, **rebuilde as imagens Docker** (os scripts são congelados na imagem em tempo de build).

---

*Documento gerado para o trabalho de mestrado. Atualize-o conforme o testbed evoluir.*
