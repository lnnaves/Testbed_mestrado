#!/usr/bin/python3

"""
common.py

Funções comuns para cenários de autenticação em grupo em redes de drones.

Modelo usado:
- Cada drone é um container Docker.
- Cada drone é uma estação Wi-Fi do Mininet-WiFi.
- A rede é ad hoc, sem Access Point.
- A autoridade central é lógica, não infraestrutura wireless.
"""

import argparse
import csv
import os
import re
from datetime import datetime, timezone
from time import sleep

from containernet.net import Containernet
from containernet.node import DockerSta
from containernet.cli import CLI

from mininet.node import Controller
from mininet.log import info

from mn_wifi.link import adhoc


# ============================================================
# Imagens Docker
# ============================================================

DRONE_IMAGE = "drone-sec:latest"
AUTH_IMAGE = "auth-server:latest"


# ============================================================
# Binários/scripts dentro dos containers
# ============================================================

PROTOCOL_BIN = "/opt/drone-sec/bin/group-auth"
TRAFFIC_BIN = "/opt/drone-sec/bin/traffic-agent"
METRICS_BIN = "/opt/drone-sec/bin/metrics-agent"
MALICIOUS_BIN = "/opt/drone-sec/bin/malicious-agent"


# ============================================================
# Rede
# ============================================================

def create_network():
    """
    Cria a rede Containernet com suporte a estações Wi-Fi containerizadas.
    """
    net = Containernet(
        controller=Controller,
        autoSetMacs=True,
        autoStaticArp=False
    )

    # Modelo simples de propagação.
    # Pode ser ajustado depois para logDistance, friis etc.
    net.setPropagationModel(model="logDistance", exp=2.5)

    return net


def add_controller(net):
    """
    Controlador mínimo para inicialização da rede.
    Mesmo sem AP, manter controlador normalmente não atrapalha.
    """
    info("*** Adding controller\n")
    return net.addController("c0")


def add_drone(
    net,
    name,
    ip,
    position,
    role="member",
    image=DRONE_IMAGE,
    range_=100,
    cpu_shares=128,
    mem_limit="256m"
):
    """
    Cria um drone como container Docker + estação Wi-Fi.

    Ponto importante:
    - cls=DockerSta: o drone é um container.
    - wlans=1: uma interface wireless.
    - position/range: usados pelo Mininet-WiFi para conectividade.
    """

    info(f"*** Adding drone container station: {name}, role={role}\n")

    drone = net.addStation(
        name,
        cls=DockerSta,
        dimage=image,
        ip=ip,
        wlans=1,
        position=position,
        range=range_,
        cpu_shares=cpu_shares,
        mem_limit=mem_limit,
        environment={
            "NODE_TYPE": "drone",
            "DRONE_ID": name,
            "DRONE_ROLE": role
        }
    )

    return drone


def add_auth_server(
    net,
    name="auth1",
    ip="10.0.0.100/24",
    position="50,50,0",
    image=AUTH_IMAGE,
    range_=120
):
    """
    Cria a autoridade central como container + estação Wi-Fi.

    Neste modelo:
    - auth é uma autoridade lógica.
    - auth NÃO é AP.
    - auth participa da rede ad hoc como qualquer outro nó.
    """

    info(f"*** Adding central authority as DockerSta: {name}\n")

    auth = net.addStation(
        name,
        cls=DockerSta,
        dimage=image,
        ip=ip,
        wlans=1,
        position=position,
        range=range_,
        cpu_shares=256,
        mem_limit="512m",
        environment={
            "NODE_TYPE": "auth_server",
            "AUTH_ID": name
        }
    )

    return auth


def create_base_group_topology(
    net,
    drone_positions=None,
    drone_roles=None,
    auth_position="50,50,0",
    auth_range=130,
    drone_range=100,
    num_drones=4
):
    """
    Cria a topologia base reutilizável com auth central e N drones.

    num_drones controla quantos drones são criados (padrão 4, preservando o
    comportamento original). Para num_drones > 4, os drones extras (drone5,
    drone6, ...) são criados programaticamente e ficam disponíveis via a lista
    retornada em "drones". As chaves nomeadas "drone1".."drone4" continuam
    presentes no dicionário de retorno quando num_drones >= 4, para manter
    compatibilidade com os cenários topology_*.py existentes.

    Posições:
    - Os 4 primeiros drones mantêm as posições padrão históricas.
    - Drones adicionais são distribuídos deterministicamente em um círculo ao
      redor da posição do auth, dentro de drone_range, garantindo que comecem
      no alcance de rádio do auth.

    IPs: 10.0.0.<i>/24 para i em 1..N. O auth permanece em 10.0.0.100/24.
    """
    import math as _math

    # Posições/roles padrão históricos para os 4 primeiros drones.
    default_positions = {
        "drone1": "30,50,0",
        "drone2": "40,60,0",
        "drone3": "60,60,0",
        "drone4": "70,50,0"
    }
    default_roles = {
        "drone1": "initial_member",
        "drone2": "initial_member",
        "drone3": "initial_member",
        "drone4": "initial_member"
    }

    # Centro (posição do auth) para gerar drones extras em círculo.
    try:
        ax, ay, az = [float(v) for v in str(auth_position).split(",")]
    except Exception:
        ax, ay, az = 50.0, 50.0, 0.0

    # Raio do círculo dos drones extras: metade do alcance do drone, para
    # garantir que fiquem confortavelmente dentro do alcance do auth.
    ring_radius = max(10.0, drone_range / 2.0)

    # Gera posições/roles padrão para drones além de 4 (determinístico).
    for i in range(5, num_drones + 1):
        name = f"drone{i}"
        # Distribui em círculo; ângulo determinístico pelo índice.
        angle = 2.0 * _math.pi * ((i - 1) / max(1, num_drones))
        x = ax + ring_radius * _math.cos(angle)
        y = ay + ring_radius * _math.sin(angle)
        default_positions[name] = f"{x:.1f},{y:.1f},0"
        default_roles[name] = "initial_member"

    if drone_positions:
        default_positions.update(drone_positions)

    if drone_roles:
        default_roles.update(drone_roles)

    auth = add_auth_server(
        net,
        name="auth1",
        ip="10.0.0.100/24",
        position=auth_position,
        range_=auth_range
    )

    drones = []
    named = {}
    for i in range(1, num_drones + 1):
        name = f"drone{i}"
        drone = add_drone(
            net,
            name=name,
            ip=f"10.0.0.{i}/24",
            position=default_positions[name],
            role=default_roles[name],
            range_=drone_range
        )
        drones.append(drone)
        named[name] = drone

    stations = [auth] + drones

    result = {
        "auth": auth,
        "drones": drones,
        "stations": stations,
    }
    # Preserva as chaves nomeadas para compatibilidade (quando existirem).
    result.update(named)

    return result


def configure_adhoc_network(
    net,
    stations,
    ssid="drone-adhoc-net",
    channel=5,
    mode="g"
):
    """
    Configura todos os nós em uma mesma rede ad hoc.

    Este é o substituto do AP.

    Todos os drones e o auth entram no mesmo IBSS/ad hoc SSID.
    """

    info("*** Configuring WiFi nodes\n")
    net.configureWifiNodes()

    info("*** Configuring ad hoc wireless network\n")

    for sta in stations:
        intf = f"{sta.name}-wlan0"

        info(f"*** Adding ad hoc link for {sta.name} on {intf}\n")

        net.addLink(
            sta,
            cls=adhoc,
            intf=intf,
            ssid=ssid,
            mode=mode,
            channel=channel
        )


def start_network(net):
    """
    Inicia a rede.
    """

    info("*** Building network\n")
    net.build()

    for controller in net.controllers:
        controller.start()

    info("*** Network started\n")

def initialize_adhoc_experiment(
    net,
    stations,
    scenario,
    connectivity_nodes=None,
    auth=None,
    rekey_scheme="naive",
    ssid="drone-adhoc-net",
    channel=5,
    mode="g",
    connectivity_wait=3,
    auth_start_wait=2
):
    """
    Executa o bootstrap comum do experimento em rede ad hoc.
    """

    configure_adhoc_network(
        net,
        stations,
        ssid=ssid,
        channel=channel,
        mode=mode
    )

    start_network(net)
    prepare_all(stations, scenario)
    start_metrics_all(stations, scenario)

    if connectivity_nodes is None:
        connectivity_nodes = stations

    wait(connectivity_wait, "testing ad hoc connectivity")
    test_connectivity(connectivity_nodes)

    if auth is not None:
        wait(auth_start_wait, "starting central authority")
        start_auth_server(auth, scenario, rekey_scheme=rekey_scheme)


# ============================================================
# Preparação dos containers
# ============================================================

def prepare_node(node, scenario):
    node.cmd("mkdir -p /tmp/drone-logs")
    node.cmd(f"echo scenario={scenario} > /tmp/drone-logs/context.txt")
    node.cmd(f"echo node={node.name} >> /tmp/drone-logs/context.txt")
    node.cmd("hostname >> /tmp/drone-logs/context.txt")
    node.cmd("ip addr >> /tmp/drone-logs/context.txt")
    node.cmd("ip route >> /tmp/drone-logs/context.txt")
    node.cmd("iw dev >> /tmp/drone-logs/context.txt 2>&1")


def prepare_all(nodes, scenario):
    for node in nodes:
        prepare_node(node, scenario)


# ============================================================
# Protocolo de autenticação em grupo
# ============================================================

def start_auth_server(auth, scenario, rekey_scheme="naive"):
    """
    Inicia a autoridade central dentro do container auth.
    rekey_scheme é repassado ao agente (naive ou lkh).
    """

    info(f"*** Starting auth server in {auth.name} (rekey_scheme={rekey_scheme})\n")

    auth.cmd(
        f"{PROTOCOL_BIN} "
        f"--role auth-server "
        f"--scenario {scenario} "
        f"--rekey-scheme {rekey_scheme} "
        f"--listen 0.0.0.0 "
        f"--port 9000 "
        f"> /tmp/drone-logs/auth-server.log 2>&1 &"
    )


def start_group_member(drone, auth_ip="10.0.0.100", group_id="mission-alpha"):
    """
    Inicia o protocolo no drone como membro do grupo.
    """

    info(f"*** Starting group member protocol in {drone.name}\n")

    drone.cmd(
        f"{PROTOCOL_BIN} "
        f"--role member "
        f"--drone-id {drone.name} "
        f"--group-id {group_id} "
        f"--auth-server {auth_ip}:9000 "
        f"> /tmp/drone-logs/group-auth.log 2>&1 &"
    )


def request_join(drone, auth_ip="10.0.0.100", group_id="mission-alpha"):
    """
    Solicitação de entrada no grupo.
    """

    info(f"*** {drone.name} requesting group join\n")

    drone.cmd(
        f"{PROTOCOL_BIN} "
        f"--role joiner "
        f"--event join "
        f"--drone-id {drone.name} "
        f"--group-id {group_id} "
        f"--auth-server {auth_ip}:9000 "
        f"> /tmp/drone-logs/join.log 2>&1 &"
    )


def request_leave(drone, auth_ip="10.0.0.100", group_id="mission-alpha"):
    """
    Solicitação de saída voluntária.
    """

    info(f"*** {drone.name} requesting group leave\n")

    drone.cmd(
        f"{PROTOCOL_BIN} "
        f"--role member "
        f"--event leave "
        f"--drone-id {drone.name} "
        f"--group-id {group_id} "
        f"--auth-server {auth_ip}:9000 "
        f"> /tmp/drone-logs/leave.log 2>&1 &"
    )


def revoke_member(auth, target, group_id="mission-alpha"):
    """
    Revogação disparada pela autoridade central.
    """

    info(f"*** Revoking {target}\n")

    auth.cmd(
        f"{PROTOCOL_BIN} "
        f"--role auth-server "
        f"--event revoke "
        f"--target {target} "
        f"--group-id {group_id} "
        f"--auth-server 127.0.0.1:9000 "
        f"> /tmp/drone-logs/revoke-{target}.log 2>&1 &"
    )


# ============================================================
# Tráfego
# ============================================================

def start_receiver(drone, port=5001):
    info(f"*** Starting traffic receiver on {drone.name}\n")

    drone.cmd(
        f"{TRAFFIC_BIN} "
        f"--role receiver "
        f"--port {port} "
        f"> /tmp/drone-logs/traffic-receiver.log 2>&1 &"
    )


def start_sender(drone, dst="10.0.0.255", port=5001, rate="10pps"):
    info(f"*** Starting traffic sender on {drone.name}\n")

    drone.cmd(
        f"{TRAFFIC_BIN} "
        f"--role sender "
        f"--dst {dst} "
        f"--port {port} "
        f"--rate {rate} "
        f"> /tmp/drone-logs/traffic-sender.log 2>&1 &"
    )


def start_malicious_traffic(drone, dst="10.0.0.255", port=5001):
    info(f"*** Starting malicious traffic on {drone.name}\n")

    drone.cmd(
        f"{MALICIOUS_BIN} "
        f"--drone-id {drone.name} "
        f"--mode old-key-traffic "
        f"--dst {dst} "
        f"--port {port} "
        f"> /tmp/drone-logs/malicious.log 2>&1 &"
    )


# ============================================================
# Métricas
# ============================================================

def start_metrics(node, scenario):
    info(f"*** Starting metrics on {node.name}\n")

    node.cmd(
        f"{METRICS_BIN} "
        f"--scenario {scenario} "
        f"--node {node.name} "
        f"> /tmp/drone-logs/metrics.log 2>&1 &"
    )


def start_metrics_all(nodes, scenario):
    for node in nodes:
        start_metrics(node, scenario)


# ============================================================
# Utilidades
# ============================================================

# Escala global aplicada a todas as chamadas de wait().
# Padrão 1.0 (comportamento idêntico ao original). Campanhas com --fast usam
# um valor menor (ex.: 0.2) para reduzir a duração total sem alterar a lógica.
_WAIT_SCALE = 1.0

def set_wait_scale(scale):
    """Define o multiplicador global de wait(). Use 1.0 para comportamento normal."""
    global _WAIT_SCALE
    try:
        scale = float(scale)
    except Exception:
        scale = 1.0
    if scale <= 0:
        scale = 1.0
    _WAIT_SCALE = scale

def wait(seconds, message):
    scaled = seconds * _WAIT_SCALE
    info(f"\n*** Waiting {scaled:.2f}s: {message} (scale={_WAIT_SCALE})\n")
    sleep(scaled)

def test_connectivity(nodes):
    """
    Teste básico de conectividade.
    Útil para validar a rede ad hoc antes de iniciar protocolo.
    """

    info("*** Testing basic ad hoc connectivity\n")

    for src in nodes:
        for dst in nodes:
            if src != dst:
                dst_ip = dst.IP()
                info(f"*** {src.name} -> {dst.name} ({dst_ip})\n")
                result = src.cmd(f"ping -c 1 -W 1 {dst_ip}")
                info(result)


def finish(net, cli=True):
    try:
        if cli:
            info("*** Opening CLI\n")
            CLI(net)
    finally:
        info("*** Stopping network\n")
        net.stop()


# ============================================================
# Métricas estruturadas
# ============================================================

# Fieldnames canônicos para o CSV de métricas.
# Todos os tipos de linha (ping_rtt e event) usam este schema,
# deixando em branco os campos que não se aplicam a cada tipo.
_METRIC_CSV_FIELDNAMES = [
    "timestamp", "scenario", "run_id", "metric_type", "phase",
    # campos para linhas de tipo ping_rtt
    "src", "dst", "dst_ip", "success", "packet_loss_percent",
    "rtt_min_ms", "rtt_avg_ms", "rtt_max_ms", "rtt_mdev_ms",
    # campos para linhas de tipo event
    "event", "node", "target", "status", "extra",
]


def ensure_metrics_dir(path):
    """
    Garante que o diretório de métricas exista.
    Cria o diretório e os pais se necessário.
    """
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        info(f"*** Warning: could not create metrics directory '{path}': {e}\n")


def build_metrics_file(scenario, run_id=None, output_dir="./results"):
    """
    Retorna o caminho do arquivo CSV de métricas para um cenário/run.

    Formato: <output_dir>/<scenario>-run-<run_id>-metrics.csv
    Garante que o diretório de saída exista.
    """
    ensure_metrics_dir(output_dir)
    if run_id is not None:
        filename = f"{scenario}-run-{run_id}-metrics.csv"
    else:
        filename = f"{scenario}-metrics.csv"
    return os.path.join(output_dir, filename)


def append_metric_csv(metrics_file, row, fieldnames=None):
    """
    Escreve uma linha no CSV de métricas.

    Cria o arquivo com cabeçalho se ainda não existir.
    Falhas de escrita são logadas mas não interrompem o experimento.
    """
    if metrics_file is None:
        return
    if fieldnames is None:
        fieldnames = _METRIC_CSV_FIELDNAMES
    try:
        file_exists = os.path.isfile(metrics_file)
        with open(metrics_file, "a", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=fieldnames,
                extrasaction="ignore", restval=""
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        info(f"*** Warning: could not write metric to '{metrics_file}': {e}\n")


def record_event_metric(
    metrics_file, scenario, run_id, event, phase,
    node=None, target=None, status="started", extra=None
):
    """
    Registra um evento de protocolo no CSV de métricas.

    Parâmetros:
    - metrics_file: caminho do arquivo CSV.
    - scenario: nome do cenário.
    - run_id: identificador do run.
    - event: nome do evento (ex.: 'auth_server_start', 'join_requested').
    - phase: fase do experimento (ex.: 'bootstrap', 'join').
    - node: nó que originou o evento.
    - target: nó-alvo do evento (opcional).
    - status: 'started' ou 'completed'.
    - extra: informação adicional livre (opcional).
    """
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario or "",
        "run_id": run_id if run_id is not None else "",
        "metric_type": "event",
        "phase": phase,
        "event": event,
        "node": node or "",
        "target": target or "",
        "status": status,
        "extra": extra or "",
    }
    append_metric_csv(metrics_file, row)


def measure_ping_rtt(
    src, dst,
    count=5, timeout=1,
    metrics_file=None, scenario=None, run_id=None,
    phase="connectivity"
):
    """
    Mede RTT/ping de src para dst e registra no CSV de métricas.

    Parseia estatísticas min/avg/max/mdev quando disponíveis.
    Falhas de ping ou de parsing não interrompem o experimento:
    nesse caso ainda registra uma linha com success=False.

    Retorna o dicionário da linha registrada.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        dst_ip = dst.IP()
    except Exception:
        dst_ip = str(dst)

    src_name = getattr(src, "name", str(src))
    dst_name = getattr(dst, "name", str(dst))

    row = {
        "timestamp": timestamp,
        "scenario": scenario or "",
        "run_id": run_id if run_id is not None else "",
        "metric_type": "ping_rtt",
        "phase": phase,
        "src": src_name,
        "dst": dst_name,
        "dst_ip": dst_ip or "",
        "success": False,
        "packet_loss_percent": 100.0,
        "rtt_min_ms": "",
        "rtt_avg_ms": "",
        "rtt_max_ms": "",
        "rtt_mdev_ms": "",
    }

    try:
        info(f"*** Measuring RTT: {src_name} -> {dst_name} ({dst_ip})\n")
        result = src.cmd(f"ping -c {count} -W {timeout} {dst_ip}")

        loss_match = re.search(r"(\d+)% packet loss", result)
        if loss_match:
            row["packet_loss_percent"] = float(loss_match.group(1))

        rtt_match = re.search(
            r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms",
            result
        )
        if rtt_match:
            row["rtt_min_ms"] = float(rtt_match.group(1))
            row["rtt_avg_ms"] = float(rtt_match.group(2))
            row["rtt_max_ms"] = float(rtt_match.group(3))
            row["rtt_mdev_ms"] = float(rtt_match.group(4))
            row["success"] = True
        else:
            row["success"] = False

    except Exception as e:
        info(
            f"*** Warning: ping measurement failed "
            f"({src_name} -> {dst_name}): {e}\n"
        )
        row["success"] = False

    append_metric_csv(metrics_file, row)
    return row


def measure_rtt_matrix(
    nodes,
    count=5, timeout=1,
    metrics_file=None, scenario=None, run_id=None,
    phase="rtt_matrix"
):
    """
    Mede RTT entre todos os pares direcionais de nós (src != dst).

    Usa measure_ping_rtt internamente para cada par.
    """
    info(f"*** Measuring RTT matrix for {len(nodes)} nodes (phase={phase})\n")
    for src in nodes:
        for dst in nodes:
            if src is not dst:
                measure_ping_rtt(
                    src, dst,
                    count=count, timeout=timeout,
                    metrics_file=metrics_file,
                    scenario=scenario,
                    run_id=run_id,
                    phase=phase
                )


# ============================================================
# Configuração experimental
# ============================================================

def parse_experiment_args(description="Drone group experiment"):
    """
    Analisa argumentos de linha de comando para configuração experimental.

    Parâmetros:
    - --runs: número de repetições do ensaio (padrão: 1).
    - --no-cli: desabilita abertura da CLI ao final.
    - --traffic-rate: taxa de tráfego (padrão: 10pps).
    - --group-id: identificador do grupo (padrão: mission-alpha).
    - --ssid: SSID da rede ad hoc (padrão: drone-adhoc-net).
    - --channel: canal Wi-Fi (padrão: 5).
    - --mode: modo Wi-Fi (padrão: g).
    - --movement-steps: número de passos para movimentos simulados (padrão: 1).
    - --movement-interval: intervalo entre passos de movimento em segundos (padrão: 1.0).
    """

    parser = argparse.ArgumentParser(description=description)

    parser.add_argument(
        "--runs", type=int, default=1,
        help="Number of experiment repetitions (default: 1)"
    )
    parser.add_argument(
        "--no-cli", action="store_true",
        help="Disable CLI at the end of the last run"
    )
    parser.add_argument(
        "--traffic-rate", default="10pps",
        help="Traffic generation rate (default: 10pps)"
    )
    parser.add_argument(
        "--group-id", default="mission-alpha",
        help="Group identifier (default: mission-alpha)"
    )
    parser.add_argument(
        "--ssid", default="drone-adhoc-net",
        help="Ad hoc network SSID (default: drone-adhoc-net)"
    )
    parser.add_argument(
        "--channel", type=int, default=5,
        help="Wi-Fi channel (default: 5)"
    )
    parser.add_argument(
        "--mode", default="g",
        help="Wi-Fi mode (default: g)"
    )
    parser.add_argument(
        "--movement-steps", type=int, default=1,
        help="Number of interpolation steps for simulated movement (default: 1)"
    )
    parser.add_argument(
        "--movement-interval", type=float, default=1.0,
        help="Interval in seconds between movement steps (default: 1.0)"
    )
    parser.add_argument(
        "--metrics-dir", default="./results",
        help="Directory where per-run CSV metric files are saved (default: ./results)"
    )
    parser.add_argument(
        "--ping-count", type=int, default=5,
        help="Number of ping packets per RTT measurement (default: 5)"
    )
    parser.add_argument(
        "--ping-timeout", type=int, default=1,
        help="Ping wait timeout in seconds per packet (default: 1)"
    )

    parser.add_argument(
        "--rekey-scheme", choices=["naive", "lkh"], default="naive",
        help="Group rekeying scheme passed to the auth server: naive (O(n)) or lkh (O(log n)) (default: naive)"
    )
    parser.add_argument(
        "--num-drones", type=int, default=4,
        help="Number of drones in the topology (default: 4)"
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Shorten wait() durations to speed up large campaigns (default: off)"
    )
    parser.add_argument(
        "--wait-scale", type=float, default=1.0,
        help="Multiplier applied to every wait() duration (default: 1.0). --fast sets this to 0.2"
    )
    args = parser.parse_args()
    # --fast é um atalho para encurtar drasticamente os waits da campanha.
    if getattr(args, "fast", False) and args.wait_scale == 1.0:
        args.wait_scale = 0.2
    set_wait_scale(args.wait_scale)
    return args


def run_experiment_runs(run_once, runs=1, cli=True):
    """
    Executa run_once(run_id, open_cli) para cada repetição do ensaio.

    Parâmetros:
    - run_once: callable(run_id, open_cli) executado a cada repetição.
    - runs: número total de repetições (deve ser >= 1).
    - cli: se True, abre a CLI somente no último run.

    O segundo argumento passado a run_once (open_cli) é True apenas no
    último run quando cli=True, permitindo que o callback decida se deve
    abrir a interface interativa.
    """

    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")

    for run_id in range(runs):
        is_last_run = (run_id == runs - 1)
        open_cli = cli and is_last_run
        info(f"\n*** Starting run {run_id + 1} of {runs}\n")
        run_once(run_id, open_cli)

    info(f"\n*** All {runs} run(s) completed\n")


def move_node_in_steps(node, target_position, steps=1, interval=1.0):
    """
    Move um nó até a posição alvo, opcionalmente em múltiplos passos.

    Parâmetros:
    - node: nó Mininet-WiFi/DockerSta a ser movido.
    - target_position: posição alvo no formato "x,y,z".
    - steps: número de passos de interpolação (padrão: 1, movimento direto).
    - interval: intervalo em segundos entre passos (padrão: 1.0).

    Se steps <= 1, usa setPosition diretamente (comportamento atual).
    Se steps > 1, interpola linearmente da posição atual até o alvo.
    Se a posição atual não puder ser obtida, cai para setPosition direto.
    """

    if steps <= 1:
        info(f"*** Moving {node.name} to {target_position}\n")
        node.setPosition(target_position)
        return

    try:
        raw_pos = node.params.get("position", "0,0,0")
        if callable(raw_pos):
            info(
                f"*** Warning: position attribute of {node.name} is callable, "
                f"falling back to direct movement\n"
            )
            node.setPosition(target_position)
            return
        cx, cy, cz = [float(v) for v in str(raw_pos).split(",")]
    except Exception:
        info(
            f"*** Could not read current position of {node.name}, "
            f"moving directly to {target_position}\n"
        )
        node.setPosition(target_position)
        return

    try:
        tx, ty, tz = [float(v) for v in target_position.split(",")]
    except Exception:
        info(
            f"*** Invalid target position '{target_position}' for {node.name}, "
            f"moving directly\n"
        )
        node.setPosition(target_position)
        return

    info(
        f"*** Moving {node.name} from {cx:.1f},{cy:.1f},{cz:.1f} "
        f"to {tx:.1f},{ty:.1f},{tz:.1f} in {steps} step(s)\n"
    )

    for step in range(1, steps + 1):
        fraction = step / steps
        x = cx + (tx - cx) * fraction
        y = cy + (ty - cy) * fraction
        z = cz + (tz - cz) * fraction
        pos = f"{x:.1f},{y:.1f},{z:.1f}"
        info(f"*** {node.name} movement step {step}/{steps}: {pos}\n")
        node.setPosition(pos)
        if step < steps:
            sleep(interval)

# ============================================================
# Coleta de CSVs in-container para o host
# ============================================================

def collect_incontainer_csvs(
    nodes,
    run_id,
    output_dir="./results",
    files=("protocol_latency.csv", "traffic_loss.csv"),
    logs_dir="/tmp/drone-logs",
):
    """
    Copia CSVs gerados DENTRO dos containers (em logs_dir) para o host.

    Para cada nó e cada arquivo em `files`, lê o conteúdo com `node.cmd("cat ...")`
    e grava em:
        <output_dir>/<scenario-run-dir>/<node.name>-<arquivo>
    O run_id é embutido no nome para não sobrescrever entre runs.

    Isso é necessário porque o orquestrador NÃO enxerga o /tmp do container
    automaticamente. Falhas (arquivo ausente) são ignoradas silenciosamente.
    """
    dest_dir = os.path.join(output_dir, f"run-{run_id}")
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except Exception as e:
        info(f"*** Warning: could not create CSV dest dir '{dest_dir}': {e}\n")
        return

    for node in nodes:
        for fname in files:
            src = f"{logs_dir}/{fname}"
            try:
                content = node.cmd(f"cat {src} 2>/dev/null")
            except Exception as e:
                info(f"*** Warning: failed to read {src} from {node.name}: {e}\n")
                continue
            if not content or not content.strip():
                continue
            # Nome de saída inclui run e nó; run_campaign sabe inferir o run_id
            # a partir do diretório run-<id>.
            base, ext = os.path.splitext(fname)
            out_name = f"{node.name}-{base}{ext}"
            out_path = os.path.join(dest_dir, out_name)
            try:
                with open(out_path, "w") as f:
                    f.write(content)
                info(f"*** Collected {src} from {node.name} -> {out_path}\n")
            except Exception as e:
                info(f"*** Warning: could not write {out_path}: {e}\n")


