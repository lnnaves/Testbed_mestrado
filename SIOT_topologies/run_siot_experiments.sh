#!/usr/bin/env bash

# ============================================================
# Roteiro de execução dos cenários SIOT_topologies
# ============================================================
#
# Este script mostra como executar os cenários de drones ad hoc
# com os novos parâmetros experimentais adicionados na etapa B.
#
# Execute a partir da pasta SIOT_topologies:
#
#   cd SIOT_topologies
#   chmod +x run_siot_experiments.sh
#   sudo ./run_siot_experiments.sh
#
# Observação:
# - Use sudo porque Containernet/Mininet-WiFi geralmente precisam de privilégios.
# - Use --no-cli para rodar experimentos automaticamente sem cair na CLI.
# - Use --runs N para repetir o mesmo cenário várias vezes.
#
# ============================================================

# ============================================================
# Cenários disponíveis
# ============================================================
#
# 1) topology_group_auth_centralized.py
#    Formação inicial do grupo com autoridade central lógica.
#
# 2) topology_group_join.py
#    drone4 começa fora do alcance, entra na rede e solicita join.
#
# 3) topology_group_leave.py
#    drone4 sai voluntariamente do grupo e depois se afasta.
#
# 4) topology_group_revocation.py
#    drone3 se comporta como malicioso, é revogado, mas continua próximo.
#
# ============================================================

# ============================================================
# Parâmetros aceitos
# ============================================================
#
# --runs N
#   Número de repetições do mesmo ensaio.
#   Padrão: 1
#
#   Recomendado:
#     1      para teste rápido/debug
#     5      para checagem inicial
#     10     para experimento simples
#     30+    para avaliação estatística mais séria
#
#
# --no-cli
#   Não abre a CLI interativa do Mininet/Containernet ao final.
#   Padrão: falso, ou seja, abre CLI no último run.
#
#   Recomendado:
#     usar --no-cli em execuções automatizadas e com --runs > 1.
#
#
# --traffic-rate TAXA
#   Taxa de geração de tráfego usada pelo traffic-agent.
#   Padrão: 10pps
#
#   Exemplos:
#     1pps
#     5pps
#     10pps
#     20pps
#     50pps
#     100pps
#
#   Recomendado:
#     10pps   baseline leve
#     20pps   carga moderada
#     50pps   carga mais forte
#     100pps  cuidado: pode saturar dependendo do ambiente
#
#
# --group-id ID
#   Identificador lógico do grupo de drones.
#   Padrão: mission-alpha
#
#   Exemplos:
#     mission-alpha
#     mission-beta
#     group-pqc-test
#     revocation-test
#
#   Recomendado:
#     usar nomes diferentes quando quiser separar logs/experimentos.
#
#
# --ssid SSID
#   Nome da rede ad hoc.
#   Padrão: drone-adhoc-net
#
#   Exemplo:
#     --ssid drone-adhoc-net
#     --ssid siot-testbed
#
#   Recomendado:
#     manter o padrão, a menos que você queira comparar redes/cenários.
#
#
# --channel CANAL
#   Canal Wi-Fi usado na rede ad hoc.
#   Padrão: 5
#
#   Exemplos:
#     1
#     5
#     6
#     11
#
#   Recomendado:
#     5 para manter o baseline atual.
#     1, 6 ou 11 se quiser testar canais diferentes.
#
#
# --mode MODO
#   Modo Wi-Fi usado pelo Mininet-WiFi.
#   Padrão: g
#
#   Exemplos comuns:
#     b
#     g
#     n
#
#   Recomendado:
#     g para manter compatibilidade com o cenário atual.
#     n se seu ambiente Mininet-WiFi suportar bem e você quiser maior capacidade.
#
#
# --movement-steps N
#   Número de passos para movimentos simulados.
#   Padrão: 1
#
#   Se N=1:
#     o movimento é direto, como antes.
#
#   Se N>1:
#     o drone é movido em etapas até o destino.
#
#   Afeta principalmente:
#     topology_group_join.py
#     topology_group_leave.py
#
#   Recomendado:
#     1    baseline compatível com comportamento antigo
#     5    mobilidade simples
#     10   mobilidade mais suave
#     20+  cuidado: aumenta duração do experimento
#
#
# --movement-interval SEGUNDOS
#   Intervalo entre passos de movimento.
#   Padrão: 1.0
#
#   Exemplos:
#     0.2
#     0.5
#     1.0
#     2.0
#
#   Recomendado:
#     0.5 para movimento relativamente rápido
#     1.0 para movimento simples e legível nos logs
#     2.0 se quiser observar transições mais lentas
#
# ============================================================

# ============================================================
# Configurações recomendadas
# ============================================================

RUNS_DEBUG=1
RUNS_QUICK=3
RUNS_EXPERIMENT=10

TRAFFIC_LOW="5pps"
TRAFFIC_BASELINE="10pps"
TRAFFIC_MEDIUM="20pps"
TRAFFIC_HIGH="50pps"

SSID="drone-adhoc-net"
CHANNEL=5
MODE="g"

GROUP_ID="mission-alpha"

MOVEMENT_DIRECT=1
MOVEMENT_SMOOTH=10
MOVEMENT_INTERVAL=0.5

# ============================================================
# Função auxiliar
# ============================================================

run_scenario() {
  local scenario="$1"
  shift

  echo
  echo "============================================================"
  echo "Executando cenário: ${scenario}"
  echo "Parâmetros extras: $*"
  echo "============================================================"
  echo

  sudo python3 "${scenario}" "$@"
}

# ============================================================
# 1) Teste rápido: um cenário, sem CLI
# ============================================================
#
# Use isto para validar se o ambiente está funcionando.

run_scenario "topology_group_auth_centralized.py" \
  --runs "${RUNS_DEBUG}" \
  --no-cli \
  --traffic-rate "${TRAFFIC_BASELINE}" \
  --group-id "${GROUP_ID}" \
  --ssid "${SSID}" \
  --channel "${CHANNEL}" \
  --mode "${MODE}"

# ============================================================
# 2) Baseline dos quatro cenários
# ============================================================
#
# Este bloco roda todos os cenários uma vez, sem CLI.
# Bom para verificar se tudo está executando corretamente.

run_scenario "topology_group_auth_centralized.py" \
  --runs 1 \
  --no-cli \
  --traffic-rate "10pps"

run_scenario "topology_group_join.py" \
  --runs 1 \
  --no-cli \
  --traffic-rate "10pps" \
  --movement-steps 1 \
  --movement-interval 1.0

run_scenario "topology_group_leave.py" \
  --runs 1 \
  --no-cli \
  --traffic-rate "10pps" \
  --movement-steps 1 \
  --movement-interval 1.0

run_scenario "topology_group_revocation.py" \
  --runs 1 \
  --no-cli \
  --traffic-rate "10pps"

# ============================================================
# 3) Experimento com repetições
# ============================================================
#
# Use quando quiser começar a coletar dados mais consistentes.
# Sugestão inicial: 10 runs.

run_scenario "topology_group_auth_centralized.py" \
  --runs "${RUNS_EXPERIMENT}" \
  --no-cli \
  --traffic-rate "${TRAFFIC_BASELINE}" \
  --group-id "mission-baseline"

run_scenario "topology_group_join.py" \
  --runs "${RUNS_EXPERIMENT}" \
  --no-cli \
  --traffic-rate "${TRAFFIC_BASELINE}" \
  --group-id "mission-join" \
  --movement-steps "${MOVEMENT_SMOOTH}" \
  --movement-interval "${MOVEMENT_INTERVAL}"

run_scenario "topology_group_leave.py" \
  --runs "${RUNS_EXPERIMENT}" \
  --no-cli \
  --traffic-rate "${TRAFFIC_BASELINE}" \
  --group-id "mission-leave" \
  --movement-steps "${MOVEMENT_SMOOTH}" \
  --movement-interval "${MOVEMENT_INTERVAL}"

run_scenario "topology_group_revocation.py" \
  --runs "${RUNS_EXPERIMENT}" \
  --no-cli \
  --traffic-rate "${TRAFFIC_BASELINE}" \
  --group-id "mission-revocation"

# ============================================================
# 4) Variação de taxa de tráfego
# ============================================================
#
# Útil para avaliar impacto de carga na rede.
# Rode o mesmo cenário com diferentes taxas.

for rate in "5pps" "10pps" "20pps" "50pps"; do
  run_scenario "topology_group_auth_centralized.py" \
    --runs 5 \
    --no-cli \
    --traffic-rate "${rate}" \
    --group-id "traffic-${rate}"
done

# ============================================================
# 5) Variação de mobilidade no cenário join
# ============================================================
#
# Compara entrada direta versus entrada gradual.

for steps in 1 5 10 20; do
  run_scenario "topology_group_join.py" \
    --runs 5 \
    --no-cli \
    --traffic-rate "10pps" \
    --group-id "join-steps-${steps}" \
    --movement-steps "${steps}" \
    --movement-interval 0.5
done

# ============================================================
# 6) Variação de mobilidade no cenário leave
# ============================================================
#
# Compara saída direta versus saída gradual.

for steps in 1 5 10 20; do
  run_scenario "topology_group_leave.py" \
    --runs 5 \
    --no-cli \
    --traffic-rate "10pps" \
    --group-id "leave-steps-${steps}" \
    --movement-steps "${steps}" \
    --movement-interval 0.5
done

# ============================================================
# 7) Variação de canal Wi-Fi
# ============================================================
#
# Útil para testar se o canal impacta algum comportamento
# no ambiente emulado.

for channel in 1 5 6 11; do
  run_scenario "topology_group_auth_centralized.py" \
    --runs 3 \
    --no-cli \
    --traffic-rate "10pps" \
    --group-id "channel-${channel}" \
    --channel "${channel}" \
    --mode "g"
done

# ============================================================
# Fim
# ============================================================

echo
echo "============================================================"
echo "Roteiro de experimentos finalizado."
echo "============================================================"
