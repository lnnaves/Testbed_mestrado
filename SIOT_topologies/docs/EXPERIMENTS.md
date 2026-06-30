# Guia de Experimentos Exploratórios — SIOT_topologies

> **Escopo deste documento:** cenários **exploratórios** que medem **RTT/latência e eventos** dos cenários `topology_*.py` (join, leave, centralized, revocation), salvos em `results/<scenario>-run-N-metrics.csv`.
>
> Para a **campanha de custo de rekeying (naïve vs. LKH)** do paper — `run_campaign.py`, `figure1/figure2`, `--rekey-scheme`, `--num-drones`, `--fast` — veja **[`../README.md`](../README.md)** e **[`../RELATORIO_TESTBED.md`](../RELATORIO_TESTBED.md)**.

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

> Nota: os cenários também aceitam `--rekey-scheme`, `--num-drones`, `--fast` e
> `--wait-scale` (usados pela campanha). Eles não são o foco deste guia
> exploratório; veja o README principal para detalhes.

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
- **Estes CSVs (RTT/eventos) não contêm o custo de rekey.** O custo de
  re-chaveamento (mensagens/operações cripto/tempo) é medido separadamente pelo
  `group_auth.py` dentro do container e consolidado pela campanha
  (`run_campaign.py` → `figure1_rekey_cost.csv`). Veja o README principal.
- **O diretório `--metrics-dir` é criado automaticamente** se não existir.
