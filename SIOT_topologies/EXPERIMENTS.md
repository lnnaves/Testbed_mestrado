# Guia de Experimentos — SIOT_topologies

Este documento descreve como executar os cenários de autenticação em grupo com
coleta estruturada de métricas (latência/RTT e eventos de protocolo).

## Cenários disponíveis

| Arquivo | Cenário | Descrição |
|---|---|---|
| `topology_group_auth_centralized.py` | `group_auth_centralized_adhoc` | Formação inicial de grupo com autoridade central |
| `topology_group_join.py` | `group_join_adhoc` | Entrada de novo membro (`drone4`) no grupo |
| `topology_group_leave.py` | `group_leave_adhoc` | Saída voluntária de membro (`drone4`) do grupo |
| `topology_group_revocation.py` | `group_revocation_adhoc` | Revogação de membro comprometido (`drone3`) |

## Argumentos comuns

Todos os cenários aceitam os seguintes argumentos de linha de comando:

| Argumento | Padrão | Descrição |
|---|---|---|
| `--runs N` | `1` | Número de repetições do ensaio |
| `--no-cli` | desligado | Não abre a CLI ao final do último run |
| `--traffic-rate RATE` | `10pps` | Taxa de geração de tráfego |
| `--group-id ID` | `mission-alpha` | Identificador do grupo |
| `--ssid SSID` | `drone-adhoc-net` | SSID da rede ad hoc |
| `--channel N` | `5` | Canal Wi-Fi |
| `--mode MODE` | `g` | Modo Wi-Fi |
| `--movement-steps N` | `1` | Passos de interpolação para movimentos |
| `--movement-interval S` | `1.0` | Intervalo em segundos entre passos |
| `--metrics-dir DIR` | `./results` | Diretório onde os CSVs são salvos |
| `--ping-count N` | `5` | Número de pacotes ping por medição de RTT |
| `--ping-timeout S` | `1` | Timeout por pacote ping (segundos) |

## Onde os CSVs são salvos

Por padrão, os arquivos são criados em `./results/` relativo ao diretório de
execução. Cada run gera um arquivo separado:

```
./results/<scenario>-run-<N>-metrics.csv
```

Exemplos:

```
./results/group_auth_centralized_adhoc-run-0-metrics.csv
./results/group_join_adhoc-run-0-metrics.csv
./results/group_leave_adhoc-run-0-metrics.csv
./results/group_revocation_adhoc-run-0-metrics.csv
```

Para múltiplos runs com `--runs 3`:

```
./results/group_join_adhoc-run-0-metrics.csv
./results/group_join_adhoc-run-1-metrics.csv
./results/group_join_adhoc-run-2-metrics.csv
```

## Exemplos de execução

### Cenário centralizado — execução simples

```bash
sudo python3 topology_group_auth_centralized.py --no-cli
```

### Cenário centralizado — com diretório de métricas e parâmetros de ping

```bash
sudo python3 topology_group_auth_centralized.py \
    --no-cli \
    --metrics-dir /tmp/exp-results \
    --ping-count 10 \
    --ping-timeout 2
```

### Cenário join — 3 repetições

```bash
sudo python3 topology_group_join.py \
    --runs 3 \
    --no-cli \
    --metrics-dir ./results/join-campaign
```

### Cenário leave

```bash
sudo python3 topology_group_leave.py \
    --no-cli \
    --metrics-dir ./results
```

### Cenário revocation

```bash
sudo python3 topology_group_revocation.py \
    --no-cli \
    --metrics-dir ./results
```

## Formato do CSV de métricas

Cada arquivo CSV usa um schema unificado com as seguintes colunas:

| Coluna | Tipo de linha | Descrição |
|---|---|---|
| `timestamp` | todos | Data/hora UTC ISO 8601 do registro |
| `scenario` | todos | Nome do cenário (ex.: `group_join_adhoc`) |
| `run_id` | todos | Identificador do run (0-indexed) |
| `metric_type` | todos | `ping_rtt` ou `event` |
| `phase` | todos | Fase do experimento (ex.: `pre_join`, `post_auth`) |
| `src` | `ping_rtt` | Nome do nó de origem do ping |
| `dst` | `ping_rtt` | Nome do nó de destino do ping |
| `dst_ip` | `ping_rtt` | Endereço IP do destino |
| `success` | `ping_rtt` | `True` se o RTT foi parseado com sucesso |
| `packet_loss_percent` | `ping_rtt` | Percentual de perda de pacotes |
| `rtt_min_ms` | `ping_rtt` | RTT mínimo em ms (vazio se falhou) |
| `rtt_avg_ms` | `ping_rtt` | RTT médio em ms (vazio se falhou) |
| `rtt_max_ms` | `ping_rtt` | RTT máximo em ms (vazio se falhou) |
| `rtt_mdev_ms` | `ping_rtt` | Desvio médio do RTT em ms (vazio se falhou) |
| `event` | `event` | Nome do evento (ex.: `join_requested`) |
| `node` | `event` | Nó que originou o evento |
| `target` | `event` | Nó-alvo do evento (quando aplicável) |
| `status` | `event` | `started` ou `completed` |
| `extra` | `event` | Informação adicional livre |

### Eventos registrados por cenário

#### Todos os cenários

| Evento | Fase | Descrição |
|---|---|---|
| `scenario_start` | `bootstrap` | Início do run |
| `auth_server_start` | `bootstrap` | Autoridade central iniciada |
| `member_auth_requested` | `auth` | Drone inicia protocolo de membro |
| `traffic_start` | varia | Início do gerador de tráfego |
| `scenario_end` | `teardown` | Fim do run |

#### `topology_group_join.py`

| Evento | Fase | Descrição |
|---|---|---|
| `join_requested` | `join` | `drone4` solicita entrada no grupo |

#### `topology_group_leave.py`

| Evento | Fase | Descrição |
|---|---|---|
| `leave_requested` | `leave` | `drone4` solicita saída do grupo |

#### `topology_group_revocation.py`

| Evento | Fase | Descrição |
|---|---|---|
| `malicious_traffic_start` | `compromise` | `drone3` inicia tráfego malicioso |
| `revocation_requested` | `revocation` | Autoridade central revoga `drone3` |

### Fases de RTT medidas por cenário

| Cenário | Fase | Nós medidos |
|---|---|---|
| centralized | `post_auth` | todos (auth + drone1-4) |
| centralized | `steady_state` | todos |
| join | `pre_join_initial_group` | auth + drone1-3 |
| join | `drone4_in_range` | todos |
| join | `post_join` | todos |
| leave | `pre_leave` | todos |
| leave | `post_leave_request` | todos |
| leave | `post_leave_remaining` | auth + drone1-3 |
| revocation | `pre_revocation` | todos |
| revocation | `post_revocation` | todos |
| revocation | `legitimate_only` | auth + drone1, drone2, drone4 |

## Notas importantes

- **Falhas de ping não interrompem o experimento.** Se o ping falhar ou o
  parsing não for possível, ainda é registrada uma linha com `success=False`
  e `packet_loss_percent=100`.
- **Execução sem argumentos continua funcionando** com os valores padrão.
  A única diferença é que os CSVs serão criados em `./results/`.
- **Os CSVs não contêm informações de criptografia ou protocolo interno.**
  Apenas registram marcos temporais e medições de rede observáveis externamente.
- **O diretório `--metrics-dir` é criado automaticamente** se não existir.


---

## Avaliação de rekeying: naïve vs. LKH

Esta seção documenta a comparação experimental entre dois esquemas de
re-chaveamento de grupo (rekeying), usados para avaliar o custo de manter a
chave de grupo atualizada sob eventos de associação (join/leave/revoke).

### Esquemas disponíveis (`--rekey-scheme`)

| Valor | Esquema | Custo de mensagens | Descrição |
|---|---|---|---|
| `naive` (padrão) | Rekey par-a-par | O(n) | Gera uma nova chave de grupo e a cifra individualmente (AES-GCM) para cada membro restante. Em leave/revoke emite N−1 mensagens; em join, N. |
| `lkh` | Logical Key Hierarchy | O(log n) | Mantém uma árvore binária de chaves real, com folhas = KEKs por membro e nós internos = KEKs intermediárias persistentes. A cada evento, re-chaveiam-se os nós no caminho da folha afetada até a raiz, cifrando (AES-GCM) a nova chave de cada nó para cada subárvore filha. Emite ~⌈log₂N⌉ mensagens por evento. |

O argumento é aceito pelo agente (`scripts/group_auth.py`) e repassado pelo
auth-server. Os cenários `topology_group_revocation.py` aceitam
`--rekey-scheme naive|lkh`.

> **Nota de honestidade científica.** A criptografia é **real** (AES-GCM via a
> biblioteca `cryptography`) e a LKH é uma **árvore de chaves de fato**, com
> nós internos persistentes re-chaveados ao longo do caminho a cada evento. O
> protocolo em si é um **esquema de referência** usado para avaliar o custo de
> rekeying — não é uma nova proposta padronizada.

### Convenção de contagem de mensagens (`rekey_msgs`)

Conta-se o número de **mensagens de rekey emitidas pela autoridade**:
- `naive`: N−1 (membros restantes) em leave/revoke; N em join.
- `lkh`: uma mensagem por cifragem de chave de nó destinada a cada subárvore
  filha ao longo do caminho re-chaveado (~O(log n)).

`crypto_ops` conta as cifragens AES-GCM efetivamente realizadas.

### Novas colunas em `protocol_latency.csv`

O CSV `/tmp/drone-logs/protocol_latency.csv` ganhou cinco colunas, posicionadas
antes da coluna `extra` (preenchidas apenas para eventos join/leave/revoke;
em branco para register/heartbeat):

| Coluna | Descrição |
|---|---|
| `rekey_scheme` | `naive` ou `lkh` |
| `group_size` | Tamanho do grupo após o evento |
| `rekey_msgs` | Mensagens de rekey emitidas pela autoridade |
| `crypto_ops` | Número de cifragens AES-GCM realizadas |
| `rekey_ms` | Tempo de parede do rekey em milissegundos (`time.perf_counter()`) |

A ordem das colunas é estável e o cabeçalho é escrito apenas na criação do
arquivo, de modo que leitores antigos não quebram.

### Novo arquivo `traffic_loss.csv` (perda por janela)

O receiver de tráfego (`scripts/traffic_agent.py`) agrega os pacotes recebidos
em janelas fixas de tempo (`--loss-window`, padrão 1.0 s) e deriva a perda a
partir dos números de sequência. Cada janela fechada vira uma linha em
`/tmp/drone-logs/traffic_loss.csv` (caminho sobrescrevível via a variável de
ambiente `TRAFFIC_LOSS_CSV`):

| Coluna | Descrição |
|---|---|
| `timestamp_utc` | Data/hora UTC do fechamento da janela |
| `scenario` | Nome do cenário |
| `receiver` | Hostname do receiver |
| `window_start` | Início da janela (epoch, segundos) |
| `expected` | `last_seq - first_seq + 1` na janela |
| `received` | Pacotes efetivamente recebidos na janela |
| `lost` | `max(0, expected - received)` |
| `loss_pct` | `100 * lost / expected` (0 se a janela estiver vazia) |

O CSV de latência por pacote (`traffic_latency.csv`) permanece inalterado; esta
métrica é puramente aditiva.

### Script de campanha (`run_campaign.py`)

`run_campaign.py` automatiza a matriz de experimentos e produz dois CSVs
prontos para plotar.

Varredura: `rekey_scheme ∈ {naive, lkh}` × `N ∈ {4, 8, 16, 32}` × `R`
repetições (padrão R = 10), executando o cenário de **revogação** para cada
célula.

Exemplo:

```bash
sudo python3 run_campaign.py \
    --schemes naive lkh \
    --sizes 4 8 16 32 \
    --runs 10 \
    --results-dir ./campaign-results \
    --fast
```

Argumentos úteis:

| Argumento | Padrão | Descrição |
|---|---|---|
| `--schemes` | `naive lkh` | Esquemas a varrer |
| `--sizes` | `4 8 16 32` | Tamanhos de grupo N |
| `--runs` | `10` | Repetições por célula |
| `--results-dir` | `./campaign-results` | Saída bruta e CSVs agregados |
| `--fast` | desligado | Encurta os `wait()` do cenário (escala 0.2) para a campanha não levar horas |
| `--dry-run` | desligado | Só imprime os comandos/plano sem executar |

Saídas (em `--results-dir`):

```
campaign-results/figure1_rekey_cost.csv
campaign-results/figure2_packet_loss.csv
campaign-results/raw/<scheme>-N<size>/...   # saídas por run
```

- `figure1_rekey_cost.csv` — colunas
  `rekey_scheme, group_size, run_id, rekey_msgs, crypto_ops, rekey_ms`
  (uma linha por evento de revoke por run). Ideal para plotar média ± desvio de
  `rekey_msgs` e `rekey_ms` vs. `group_size`.
- `figure2_packet_loss.csv` — colunas
  `rekey_scheme, group_size, run_id, t_relative_s, loss_pct`
  (janelas de perda alinhadas no tempo em torno do revoke). Ideal para plotar a
  perda ao longo do tempo para um N representativo (ex.: 32), naïve vs. lkh.

**Como os dados fluem.** O custo de rekey é produzido pelo auth-server dentro
do container (em `protocol_latency.csv`) e a perda por janela vem de
`traffic_loss.csv`, também no container. O cenário de revogação copia esses
arquivos para `<metrics-dir>/run-<id>/<node>-<arquivo>` ao final de cada run
(via `collect_incontainer_csvs`), e o `run_campaign.py` os consolida nos dois
CSVs agregados.

### Escala de wait (`--fast` / `--wait-scale`)

Para reduzir o tempo total de campanhas (80 runs podem levar horas), os
cenários aceitam `--fast` (atalho para `--wait-scale 0.2`) ou um
`--wait-scale` explícito. O padrão é `1.0`, preservando exatamente o
comportamento original quando nenhuma das flags é usada.
