# Testbed de Rekeying em Grupo para Drones — Naïve vs. LKH

Avaliação experimental do **custo de re-chaveamento (rekeying) de grupo** em uma rede ad hoc de drones, comparando o esquema **naïve (O(n))** com **LKH — Logical Key Hierarchy (O(log n))**, no momento em que um drone comprometido é **revogado**.

O ambiente usa **Containernet + Mininet-WiFi**: cada drone e a autoridade central são contêineres Docker que também são estações Wi-Fi em uma rede ad hoc (IBSS, sem Access Point).

> 📄 Para uma descrição técnica detalhada (todas as funções, fluxo de dados, decisões de projeto), veja **[`RELATORIO_TESTBED.md`](./RELATORIO_TESTBED.md)**.

---

## Índice

- [O que este testbed responde](#o-que-este-testbed-responde)
- [Como funciona](#como-funciona)
- [Pré-requisitos](#pré-requisitos)
- [Instalação e build das imagens](#instalação-e-build-das-imagens)
- [Como rodar](#como-rodar)
- [O que esperar (resultados)](#o-que-esperar-resultados)
- [Saídas geradas](#saídas-geradas)
- [Solução de problemas](#solução-de-problemas)
- [Estrutura do diretório](#estrutura-do-diretório)

---

## O que este testbed responde

> Quando um drone é revogado de um grupo, **quanto custa** redistribuir a nova chave de grupo aos membros restantes — e **como esse custo cresce** com o tamanho do grupo N?

| Esquema | Estratégia | Custo de mensagens |
|---|---|---|
| **naïve** | Nova chave de grupo cifrada **uma vez por membro restante** | **O(n)** |
| **lkh** | Árvore binária de chaves; re-chaveia só o **caminho** da folha à raiz | **O(log n)** |

A criptografia é **real** (AES-GCM via biblioteca `cryptography`). O protocolo é um **esquema de referência** para *medir* o custo de rekeying — não uma proposta padronizada nova.

---

## Como funciona

```
+-----------------------------------------------------------------+
|  HOST (sua maquina, com sudo)                                   |
|                                                                 |
|  run_campaign.py  --orquestra-->  topology_group_revocation.py  |
|       |                                    |                    |
|       |                              usa funcoes de common.py   |
|       |                                    |                    |
|       |                          +---------+---------+          |
|       |                          v                   v          |
|       |              +-------------------+  +------------------+ |
|       |              | CONTAINER auth1   |  | CONTAINER droneN | |
|       |              | group_auth.py     |  | group_auth.py    | |
|       |              |  (auth-server)    |  | traffic_agent.py | |
|       |              |                   |  | malicious_agent  | |
|       |              | gera:             |  | gera:            | |
|       |              |  protocol_        |  |  traffic_loss.csv| |
|       |              |  latency.csv      |  |                  | |
|       |              +-------------------+  +------------------+ |
|       |                          |                              |
|       |       collect_incontainer_csvs() copia p/ o host        |
|       v                          v                              |
|  figure1_rekey_cost.csv   campaign-results/raw/.../run-N/*.csv  |
|  figure2_packet_loss.csv                                        |
|       |                                                         |
|       v                                                         |
|  plot_figures.py  -->  figure1.png/pdf  +  figure2.png/pdf      |
+-----------------------------------------------------------------+
```

**Cenário de cada execução (`topology_group_revocation.py`):**

1. Cria o grupo: autoridade central `auth1` + N drones em rede ad hoc.
2. Todos os drones autenticam e formam o grupo.
3. Tráfego legítimo começa a fluir.
4. `drone3` passa a se comportar de forma maliciosa (usa chave antiga).
5. A autoridade **revoga `drone3`** → dispara o rekeying (naïve **ou** LKH).
6. Mede-se o **custo do rekey** (mensagens, operações cripto, tempo) e a **perda de pacotes** em torno do revoke.
7. Os CSVs gerados dentro dos contêineres são copiados para o host.

---

## Pré-requisitos

- **Linux** com **Containernet** e **Mininet-WiFi** instalados e funcionando.
- **Docker** funcionando (com permissão para o seu usuário ou via `sudo`).
- **Python 3** no host, com **matplotlib** (para gerar as figuras):
  ```bash
  sudo apt install -y python3-matplotlib
  # ou, em um virtualenv:
  pip install matplotlib
  ```
- Executar a partir da pasta **`SIOT_topologies/`** (os caminhos e o contexto de build dependem disso).

> ⚠️ A campanha sobe contêineres reais e usa o Mininet, portanto **requer `sudo`**.

---

## Instalação e build das imagens

As imagens Docker **congelam** os scripts em `scripts/` no momento do build. Sempre que você alterar um script em `scripts/`, **rebuilde**.

A partir de `SIOT_topologies/`:

```bash
# imagem do drone  (tag obrigatoria: drone-sec:latest)
docker build -t drone-sec:latest   -f docker/drone/Dockerfile .

# imagem da autoridade central  (tag obrigatoria: auth-server:latest)
docker build -t auth-server:latest -f docker/auth-server/Dockerfile .
```

> O `.` no final é o **contexto de build** (= a pasta `SIOT_topologies/`). É ele que permite o `COPY scripts/` enxergar os scripts. **Não** rode de dentro de `docker/drone/`.
>
> As tags **precisam** ser `drone-sec:latest` e `auth-server:latest` — o `common.py` referencia exatamente esses nomes.

Verifique as imagens:

```bash
docker images | grep -E "drone-sec|auth-server"
# o cryptography esta na imagem?
docker run --rm drone-sec:latest python3 -c "import cryptography; print('OK', cryptography.__version__)"
```

---

## Como rodar

### 1) Teste mínimo (valida o pipeline rápido)

```bash
sudo python3 run_campaign.py \
    --schemes naive \
    --sizes 4 \
    --runs 1 \
    --results-dir ./campaign-test \
    --fast
```

Confira que os CSVs agregados têm linhas:

```bash
wc -l ./campaign-test/figure1_rekey_cost.csv ./campaign-test/figure2_packet_loss.csv
```

✔️ Sucesso = `figure1_rekey_cost.csv` com **2 ou mais linhas** (cabeçalho + dados).

### 2) Campanha completa (resultado do paper)

Varre `naive` e `lkh` para N = 4, 8, 16, 32, com 10 repetições cada (**80 execuções**; pode levar **1–2 h**):

```bash
sudo python3 run_campaign.py \
    --schemes naive lkh \
    --sizes 4 8 16 32 \
    --runs 10 \
    --results-dir ./campaign-results \
    --fast
```

### 3) Gerar as figuras

Como a campanha roda com `sudo`, os arquivos pertencem ao root. Devolva a posse e gere as figuras **sem** sudo:

```bash
sudo chown -R "$USER:$USER" ./campaign-results

python3 plot_figures.py --results-dir ./campaign-results --fig1-logy
```

#### Opções úteis do `plot_figures.py`

```bash
# metrica da Figura 1: rekey_msgs (padrao), crypto_ops ou rekey_ms
python3 plot_figures.py --results-dir ./campaign-results --metric crypto_ops

# escolher o N exibido na Figura 2 (padrao: maior N disponivel)
python3 plot_figures.py --results-dir ./campaign-results --figure2-size 32

# recortar o eixo de tempo da Figura 2 (em segundos, t=0 no revoke)
python3 plot_figures.py --results-dir ./campaign-results --t-min -10 --t-max 30

# gerar somente a Figura 1 (ou somente a 2)
python3 plot_figures.py --results-dir ./campaign-results --only 1
```

### Principais flags do `run_campaign.py`

| Flag | Descrição | Padrão |
|---|---|---|
| `--schemes` | Esquemas a varrer (`naive`, `lkh`) | `naive lkh` |
| `--sizes` | Tamanhos de grupo N | `4 8 16 32` |
| `--runs` | Repetições por célula | `10` |
| `--results-dir` | Diretório de saída | `./campaign-results` |
| `--fast` | Encurta as esperas (escala 0.2) p/ acelerar | desligado |
| `--dry-run` | Só imprime os comandos, sem executar | desligado |

---

## O que esperar (resultados)

Ao final da campanha, `figure1_rekey_cost.csv` deve ter **8 linhas de dados** (naïve e lkh × N ∈ {4, 8, 16, 32}).

**Figura 1 — custo de rekey vs N (o resultado central):**

- **naïve:** `rekey_msgs ≈ N − 1` → cresce **linearmente** com o grupo.
- **lkh:** `rekey_msgs ≈ O(log N)` → cresce muito mais devagar.

Com o eixo Y logarítmico (`--fig1-logy`), a separação entre as duas curvas evidencia a vantagem de escalabilidade do LKH. As barras de erro são o desvio padrão sobre os runs.

**Figura 2 — perda de pacotes vs tempo:**

- Eixo X centrado em **t = 0 no instante do revoke** (linha vertical vermelha).
- Mostra a interrupção no tráfego legítimo em torno da revogação, comparando os dois esquemas para um N representativo.

> Exemplo de leitura (N=4, naïve): no evento de revoke o auth re-chaveia os 3 membros restantes → `rekey_msgs = 3`, `crypto_ops = 3`, `rekey_ms` na ordem de ~1 ms.

---

## Saídas geradas

Dentro de `--results-dir`:

| Arquivo | Conteúdo |
|---|---|
| `figure1_rekey_cost.csv` | `rekey_scheme, group_size, run_id, rekey_msgs, crypto_ops, rekey_ms` |
| `figure2_packet_loss.csv` | `rekey_scheme, group_size, run_id, t_relative_s, loss_pct` |
| `figure1_rekey_cost.png` / `.pdf` | Gráfico do custo de rekey vs N |
| `figure2_packet_loss.png` / `.pdf` | Gráfico de perda vs tempo (t=0 no revoke) |
| `raw/<esquema>-N<tamanho>/run-<id>/` | CSVs brutos coletados dos contêineres |

---

## Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| `PermissionError` ao salvar `.png` | CSVs/pastas criados como root (campanha roda com `sudo`) | `sudo chown -R "$USER:$USER" ./campaign-results` e rode o plot **sem** sudo |
| `figure1` com 0 linhas | `protocol_latency.csv` sem o evento `revoke` ou corrompido | confira `raw/.../run-0/auth1-protocol_latency.csv`; rebuilde as imagens |
| `unrecognized arguments` / `TypeError` / `ImportError` no `common.py` | versão desatualizada/incompleta de `common.py` em disco | garanta a versão atual: `grep -c num_drones common.py` e `grep -c collect_incontainer_csvs common.py` (ambos > 0) |
| Mudou um script mas o comportamento não muda | a imagem Docker tem a versão **antiga** congelada | **rebuilde** `drone-sec` e `auth-server` |
| Container não sobe / erro de cápsula Wi-Fi | Containernet/Mininet-WiFi não inicializado | rode com `sudo`; verifique a instalação do Mininet-WiFi |
| N=32 satura a máquina | 33 contêineres simultâneos | rode até N=16 primeiro e N=32 separadamente |

Verificação rápida de sanidade do `common.py` (sem subir contêiner):

```bash
python3 -c "import common; print('OK:', hasattr(common,'collect_incontainer_csvs'), 'num_drones' in common.create_base_group_topology.__code__.co_varnames)"
# esperado: OK: True True
```

---

## Estrutura do diretório

```
SIOT_topologies/
├── README.md                          # este arquivo
├── RELATORIO_TESTBED.md               # relatório técnico detalhado
├── common.py                          # biblioteca de orquestração (host)
├── run_campaign.py                    # orquestrador da campanha + consolidação
├── plot_figures.py                    # geração das figuras
├── topology_group_revocation.py       # cenário de revogação (usado na campanha)
├── topology_group_join.py             # cenários auxiliares
├── topology_group_leave.py
├── topology_group_auth_centralized.py
├── topology_group_auth_distributed.py
├── topology_group_partition_merge.py
├── docker/
│   ├── drone/Dockerfile               # imagem drone-sec:latest
│   └── auth-server/Dockerfile         # imagem auth-server:latest
└── scripts/                           # agentes que rodam DENTRO dos contêineres
    ├── group_auth.py                  # protocolo + naïve/LKH + métricas
    ├── traffic_agent.py               # tráfego legítimo
    ├── metrics_agent.py               # coleta de métricas no nó
    └── malicious_agent.py             # tráfego malicioso (pós-revogação)
```

---

## Fluxo recomendado (resumo)

```bash
# 1) build (uma vez, ou apos mudar scripts/)
docker build -t drone-sec:latest   -f docker/drone/Dockerfile .
docker build -t auth-server:latest -f docker/auth-server/Dockerfile .

# 2) teste minimo
sudo python3 run_campaign.py --schemes naive --sizes 4 --runs 1 --results-dir ./campaign-test --fast

# 3) campanha completa
sudo python3 run_campaign.py --schemes naive lkh --sizes 4 8 16 32 --runs 10 --results-dir ./campaign-results --fast

# 4) figuras
sudo chown -R "$USER:$USER" ./campaign-results
python3 plot_figures.py --results-dir ./campaign-results --fig1-logy
```
