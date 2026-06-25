#!/usr/bin/python3

"""
common_multi_sender.py

Extensões para executar tráfego de missão em modo mais realista.

Este módulo reexporta as funções de common.py e sobrescreve/adiciona
helpers de tráfego para permitir:
- todos os membros legítimos como receivers;
- todos os membros legítimos como senders UDP;
- parada explícita do sender legítimo quando um drone sai ou é revogado.
"""

from common import *  # noqa: F401,F403


# ============================================================
# Tráfego multi-emissor
# ============================================================

def start_sender(
    drone,
    dst="10.0.0.255",
    port=5001,
    rate="10pps",
    message="simulated telemetry message",
    pid_name="traffic-sender.pid",
    log_name=None,
):
    """
    Inicia um sender UDP legítimo no drone e salva o PID.

    Salvar o PID permite parar o tráfego legítimo em cenários como:
    - leave: drone que saiu deixa de transmitir como membro legítimo;
    - revocation: drone revogado deixa de transmitir como membro legítimo.
    """
    info(f"*** Starting traffic sender on {drone.name}\n")

    if log_name is None:
        log_name = f"traffic-sender-{drone.name}.log"

    safe_message = str(message).replace('"', '\\"')

    drone.cmd(
        f"sh -c '{TRAFFIC_BIN} "
        f"--role sender "
        f"--dst {dst} "
        f"--port {port} "
        f"--rate {rate} "
        f"--message \"{safe_message}\" "
        f"> /tmp/drone-logs/{log_name} 2>&1 & "
        f"echo $! > /tmp/drone-logs/{pid_name}'"
    )


def stop_sender(drone, pid_name="traffic-sender.pid"):
    """
    Para o sender UDP legítimo de um drone, se existir.

    Importante: esta função não para malicious-agent. O tráfego malicioso
    é separado do tráfego legítimo da missão.
    """
    info(f"*** Stopping traffic sender on {drone.name}\n")

    drone.cmd(
        f"if [ -f /tmp/drone-logs/{pid_name} ]; then "
        f"kill $(cat /tmp/drone-logs/{pid_name}) 2>/dev/null || true; "
        f"rm -f /tmp/drone-logs/{pid_name}; "
        f"fi"
    )


def start_receivers_for(drones, port=5001):
    """
    Inicia receivers UDP para todos os drones informados.
    """
    for drone in drones:
        start_receiver(drone, port=port)


def start_senders_for(
    drones,
    dst="10.0.0.255",
    port=5001,
    rate="10pps",
    message_prefix="simulated telemetry message",
):
    """
    Inicia senders UDP legítimos para todos os drones informados.
    """
    for drone in drones:
        start_sender(
            drone,
            dst=dst,
            port=port,
            rate=rate,
            message=f"{message_prefix} from {drone.name}",
        )


def stop_senders_for(drones):
    """
    Para os senders UDP legítimos dos drones informados.
    """
    for drone in drones:
        stop_sender(drone)
