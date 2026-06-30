# O que está sendo mensurado nas métricas do testbed

> **Escopo deste documento:** as métricas de **RTT/latência e eventos** dos
> cenários exploratórios (`results/<scenario>-run-N-metrics.csv`).
>
> Para o **custo de rekeying (naïve vs. LKH)** medido pela campanha — mensagens,
> operações criptográficas e tempo de re-chaveamento — veja
> **[`../README.md`](../README.md)** e **[`../RELATORIO_TESTBED.md`](../RELATORIO_TESTBED.md)**.

As métricas geradas por estes cenários têm dois objetivos principais:

1. **registrar eventos importantes do experimento**;
2. **medir a latência de comunicação entre os nós da rede ad hoc**.

Os resultados são salvos em arquivos CSV, um arquivo por cenário e por execução:

```text
./results/<scenario>-run-<N>-metrics.csv
```

---

## 1. Métricas de eventos

As linhas com:

```text
metric_type = event
```

registram marcos temporais importantes do experimento.

Elas indicam **quando uma ação relevante foi disparada**, por exemplo:

- início do cenário;
- fim do cenário;
- início da autoridade central;
- início da autenticação dos drones;
- solicitação de entrada no grupo;
- solicitação de saída do grupo;
- solicitação de revogação;
- início de tráfego normal;
- início de tráfego malicioso.

Essas métricas servem para reconstruir a linha do tempo do experimento.

Importante: elas **não confirmam sozinhas que o protocolo terminou com sucesso**. Elas registram o momento em que a ação foi solicitada no cenário.

Exemplo conceitual:

```text
scenario_start
auth_server_start
member_auth_requested
traffic_start
join_requested
leave_requested
revocation_requested
scenario_end
```

---

## 2. Métricas de RTT / latência de rede

As linhas com:

```text
metric_type = ping_rtt
```

registram medições de latência entre dois nós da rede.

Essas medições são feitas com `ping`, executado dentro do nó de origem, por exemplo:

```bash
ping -c 5 -W 1 10.0.0.2
```

Isso mede o tempo de ida e volta entre dois nós:

```text
src -> dst -> src
```

Ou seja, mede **RTT — Round Trip Time**.

---

## 3. O que significa cada campo principal

| Campo | Significado |
|---|---|
| `timestamp` | Momento em que a métrica foi registrada |
| `scenario` | Nome do cenário executado |
| `run_id` | Número da repetição do experimento |
| `metric_type` | Tipo da métrica: `event` ou `ping_rtt` |
| `phase` | Fase do experimento em que a métrica foi coletada |
| `event` | Nome do evento registrado |
| `node` | Nó associado ao evento |
| `target` | Alvo do evento, quando aplicável |
| `status` | Estado do evento registrado |
| `src` | Nó de origem do ping |
| `dst` | Nó de destino do ping |
| `dst_ip` | Endereço IP do destino |
| `success` | Indica se a medição foi interpretada com sucesso |
| `packet_loss_percent` | Percentual de perda de pacotes |
| `rtt_min_ms` | Menor RTT medido, em milissegundos |
| `rtt_avg_ms` | RTT médio, em milissegundos |
| `rtt_max_ms` | Maior RTT medido, em milissegundos |
| `rtt_mdev_ms` | Variação/desvio do RTT, em milissegundos |

---

## 4. O que o RTT representa

O RTT representa o tempo total para uma mensagem sair de um nó, chegar ao destino e retornar.

Exemplo:

```text
drone1 -> drone2 -> drone1
```

Se o RTT médio for:

```text
rtt_avg_ms = 12.4
```

significa que, em média, o caminho de ida e volta entre `drone1` e `drone2` levou `12.4 ms`.

Uma aproximação simples da latência unidirecional seria:

```text
latência aproximada ≈ RTT / 2
```

Mas essa aproximação só é válida se o caminho de ida e volta for relativamente simétrico.

---

## 5. O que é medido em cada cenário

### Cenário centralizado

Arquivo:

```text
topology_group_auth_centralized.py
```

Mede RTT em fases como:

- após autenticação dos membros;
- durante o estado estável de comunicação.

Objetivo:

```text
avaliar a latência da rede após a formação inicial do grupo
```

---

### Cenário join

Arquivo:

```text
topology_group_join.py
```

Mede RTT em fases como:

- antes da entrada do `drone4`;
- depois que o `drone4` entra no alcance;
- depois da solicitação de join;
- durante o tráfego após o join.

Objetivo:

```text
avaliar o impacto da entrada de um novo drone na rede
```

---

### Cenário leave

Arquivo:

```text
topology_group_leave.py
```

Mede RTT em fases como:

- antes da saída do `drone4`;
- depois da solicitação de leave;
- depois que o `drone4` se afasta;
- entre os drones restantes.

Objetivo:

```text
avaliar o impacto da saída voluntária de um drone
```

---

### Cenário revocation

Arquivo:

```text
topology_group_revocation.py
```

Mede RTT em fases como:

- antes da revogação;
- depois da revogação;
- entre os drones legítimos após a revogação.

Objetivo:

```text
avaliar o impacto da revogação lógica de um drone malicioso
```

---

## 6. O que estas métricas (RTT/eventos) não medem

Estas métricas de RTT/eventos, por si só, **não medem**:

- throughput real;
- jitter de aplicação;
- consumo de CPU/memória.

> Atenção: o **custo criptográfico de rekeying** (tempo de re-chaveamento
> `rekey_ms`, número de operações AES-GCM `crypto_ops` e de mensagens
> `rekey_msgs`) **passou a ser medido** pelo `group_auth.py` dentro do container
> e é consolidado pela campanha (`run_campaign.py` → `figure1_rekey_cost.csv`).
> Ele simplesmente não aparece neste CSV de RTT/eventos. Veja o README principal.

---

## 7. Como interpretar os resultados

Para análise inicial, observe principalmente:

```text
rtt_avg_ms
packet_loss_percent
phase
scenario
run_id
```

Exemplo de perguntas que os CSVs ajudam a responder:

- o RTT aumenta depois do join?
- há mais perda durante mobilidade?
- a revogação afeta a comunicação dos drones legítimos?
- o tráfego mais intenso aumenta a latência?
- movimentos graduais causam mais instabilidade que movimentos diretos?
- a rede fica estável após saída ou entrada de drones?

---

## 8. Resumo em uma frase

As métricas exploratórias medem **a linha do tempo dos eventos do cenário** e a
**latência RTT entre os nós da rede ad hoc**, permitindo avaliar como eventos de
grupo, mobilidade e tráfego afetam a comunicação. O **custo de rekeying** é
medido à parte, pela campanha naïve-vs-LKH.
