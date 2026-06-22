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
    drone_range=100
):
    """
    Cria a topologia base reutilizável com auth central e quatro drones.
    """

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

    drone1 = add_drone(
        net,
        name="drone1",
        ip="10.0.0.1/24",
        position=default_positions["drone1"],
        role=default_roles["drone1"],
        range_=drone_range
    )
    drone2 = add_drone(
        net,
        name="drone2",
        ip="10.0.0.2/24",
        position=default_positions["drone2"],
        role=default_roles["drone2"],
        range_=drone_range
    )
    drone3 = add_drone(
        net,
        name="drone3",
        ip="10.0.0.3/24",
        position=default_positions["drone3"],
        role=default_roles["drone3"],
        range_=drone_range
    )
    drone4 = add_drone(
        net,
        name="drone4",
        ip="10.0.0.4/24",
        position=default_positions["drone4"],
        role=default_roles["drone4"],
        range_=drone_range
    )

    drones = [drone1, drone2, drone3, drone4]
    stations = [auth] + drones

    return {
        "auth": auth,
        "drones": drones,
        "stations": stations,
        "drone1": drone1,
        "drone2": drone2,
        "drone3": drone3,
        "drone4": drone4
    }


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
        start_auth_server(auth, scenario)


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

def start_auth_server(auth, scenario):
    """
    Inicia a autoridade central dentro do container auth.
    """

    info(f"*** Starting auth server in {auth.name}\n")

    auth.cmd(
        f"{PROTOCOL_BIN} "
        f"--role auth-server "
        f"--scenario {scenario} "
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

def wait(seconds, message):
    info(f"\n*** Waiting {seconds}s: {message}\n")
    sleep(seconds)


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
