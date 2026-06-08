#!/usr/bin/python3

"""
common.py

Funções comuns para os cenários de autenticação em grupo.

Neste projeto:
- cada drone é um container Docker;
- cada drone também é uma estação Wi-Fi do Mininet-WiFi;
- os protocolos de autenticação rodam dentro do container;
- a rede wireless é emulada pelo Mininet-WiFi/Containernet.
"""

from time import sleep

from containernet.net import Containernet
from containernet.node import DockerSta
from containernet.cli import CLI

from mininet.node import Controller
from mininet.log import info


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
# Criação da rede
# ============================================================

def create_network():
    """
    Cria uma rede Containernet com suporte às estações Wi-Fi.
    """
    net = Containernet(
        controller=Controller,
        autoSetMacs=True,
        autoStaticArp=True
    )
    return net


def add_controller(net):
    info("*** Adding controller\n")
    return net.addController("c0")


def add_access_point(net):
    """
    Ponto de acesso sem fio usado para conectar os drones.
    Para o artigo, ele representa a infraestrutura wireless emulada.
    """
    info("*** Adding access point\n")

    ap1 = net.addAccessPoint(
        "ap1",
        ssid="drone-group-net",
        mode="g",
        channel="1",
        position="50,50,0",
        range=130
    )

    return ap1


def add_drone(
    net,
    name,
    ip,
    position,
    role="member",
    image=DRONE_IMAGE,
    range_=90,
    cpu_shares=128,
    mem_limit="256m"
):
    """
    Cria um drone como container Docker + estação Wi-Fi.

    Este é o ponto mais importante:
    - cls=DockerSta transforma a estação Wi-Fi em container Docker.
    - dimage define a imagem com os protocolos instalados.
    """

    info(f"*** Adding drone container station: {name}, role={role}\n")

    drone = net.addStation(
        name,
        cls=DockerSta,
        dimage=image,
        ip=ip,
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
    name="auth",
    ip="10.0.0.100/24",
    position="50,45,0",
    image=AUTH_IMAGE
):
    """
    Cria a autoridade central também como container wireless.

    Você pode interpretar este nó como:
    - GCS;
    - servidor de autenticação;
    - KDC;
    - controlador de grupo;
    - autoridade da missão.

    Ele também é DockerSta para manter tudo containerizado.
    """

    info(f"*** Adding central authority container station: {name}\n")

    auth = net.addStation(
        name,
        cls=DockerSta,
        dimage=image,
        ip=ip,
        position=position,
        range=130,
        cpu_shares=256,
        mem_limit="512m",
        environment={
            "NODE_TYPE": "auth_server",
            "AUTH_ID": name
        }
    )

    return auth


def configure_wifi_and_links(net, stations, ap):
    """
    Configura os nós Wi-Fi e associa as estações ao AP.

    No exemplo oficial do Containernet com Mininet-WiFi,
    as estações DockerSta são criadas com addStation e associadas
    ao AP usando addLink(sta, ap).
    """

    info("*** Configuring WiFi nodes\n")
    net.configureWifiNodes()

    info("*** Associating stations to AP\n")
    for sta in stations:
        net.addLink(sta, ap)


def start_network(net):
    info("*** Starting network\n")
    net.build()

    for controller in net.controllers:
        controller.start()

    for ap in net.aps:
        ap.start(net.controllers)

    info("*** Network started\n")


# ============================================================
# Preparação dos containers
# ============================================================

def prepare_node(node, scenario):
    node.cmd("mkdir -p /tmp/drone-logs")
    node.cmd(f"echo scenario={scenario} > /tmp/drone-logs/context.txt")
    node.cmd(f"echo node={node.name} >> /tmp/drone-logs/context.txt")
    node.cmd("ip addr >> /tmp/drone-logs/context.txt")
    node.cmd("ip route >> /tmp/drone-logs/context.txt")


def prepare_all(nodes, scenario):
    for node in nodes:
        prepare_node(node, scenario)


# ============================================================
# Hooks de protocolo
# ============================================================

def start_auth_server(auth, scenario):
    """
    Inicia o servidor/autoridade do protocolo pronto.

    Substitua os argumentos pelo protocolo real.
    """
    info(f"*** Starting auth server in container {auth.name}\n")

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
    Inicia o cliente/membro do protocolo de grupo.
    """
    info(f"*** Starting group protocol in {drone.name}\n")

    drone.cmd(
        f"{PROTOCOL_BIN} "
        f"--role member "
        f"--drone-id {drone.name} "
        f"--group-id {group_id} "
        f"--auth-server {auth_ip}:9000 "
        f"> /tmp/drone-logs/group-auth.log 2>&1 &"
    )


def request_join(drone, auth_ip="10.0.0.100", group_id="mission-alpha"):
    info(f"*** {drone.name} requesting join\n")

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
    info(f"*** {drone.name} requesting leave\n")

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
    info(f"*** Revoking {target}\n")

    auth.cmd(
        f"{PROTOCOL_BIN} "
        f"--role auth-server "
        f"--event revoke "
        f"--target {target} "
        f"--group-id {group_id} "
        f"> /tmp/drone-logs/revoke-{target}.log 2>&1 &"
    )


# ============================================================
# Hooks de tráfego
# ============================================================

def start_receiver(drone, port=5001):
    info(f"*** Starting receiver on {drone.name}\n")

    drone.cmd(
        f"{TRAFFIC_BIN} "
        f"--role receiver "
        f"--port {port} "
        f"> /tmp/drone-logs/traffic-receiver.log 2>&1 &"
    )


def start_sender(drone, dst="10.0.0.255", port=5001, rate="10pps"):
    info(f"*** Starting sender on {drone.name}\n")

    drone.cmd(
        f"{TRAFFIC_BIN} "
        f"--role sender "
        f"--dst {dst} "
        f"--port {port} "
        f"--rate {rate} "
        f"> /tmp/drone-logs/traffic-sender.log 2>&1 &"
    )


def start_malicious_traffic(drone, dst="10.0.0.255", port=5001):
    info(f"*** Starting malicious behavior on {drone.name}\n")

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


def finish(net, cli=True):
    if cli:
        info("*** Opening CLI\n")
        CLI(net)

    info("*** Stopping network\n")
    net.stop()