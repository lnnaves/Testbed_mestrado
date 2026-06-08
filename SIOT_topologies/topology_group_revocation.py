#!/usr/bin/python3

"""
topology_group_revocation.py

Cenário:
- Grupo inicial autenticado.
- Um drone inicialmente legítimo é considerado comprometido.
- A autoridade central revoga esse drone.
- O drone revogado tenta continuar se comunicando.

Objetivo:
- Avaliar capacidade do protocolo de isolar membro comprometido.
- Medir revogação, rekeying e rejeição de mensagens inválidas.

Evento principal:
- auth server revoga drone3.
- drone3 tenta continuar enviando tráfego ou mensagens de grupo.

Métricas:
- Tempo de revogação.
- Tempo de rekeying.
- Mensagens maliciosas aceitas antes da revogação.
- Mensagens rejeitadas após a revogação.
- Impacto nos membros legítimos.
- Overhead de controle.
"""

from mininet.log import setLogLevel, info

from common import (
    create_network,
    add_controller,
    add_group_ap,
    add_auth_server,
    add_drone,
    configure_and_start,
    prepare_all,
    start_auth_server,
    start_group_member,
    start_revocation,
    start_group_traffic_receiver,
    start_group_traffic_sender,
    start_metrics_all,
    wait_event,
    dump_logs_to_host,
    open_cli_or_stop
)


SCENARIO = "group_revocation"


def start_malicious_behavior(drone):
    """
    Hook para comportamento malicioso.

    Substitua por algo mais específico, por exemplo:
    - replay de mensagens antigas;
    - envio com chave antiga;
    - flooding;
    - envio de comando falso;
    - tentativa de rejoin usando credencial revogada.
    """
    info(f"*** Starting malicious behavior on {drone.name}\n")

    drone.cmd(
        f"/opt/drone-sec/bin/malicious-agent "
        f"--drone-id {drone.name} "
        f"--mode old-key-traffic "
        f"--dst 10.0.0.255 "
        f"--port 5001 "
        f"> /tmp/drone-logs/malicious.log 2>&1 &"
    )


def run(cli=True):
    net = create_network()

    info("*** Creating group revocation scenario\n")

    add_controller(net)
    add_group_ap(net)

    auth = add_auth_server(net, name="auth", ip="10.0.0.100/24")

    drone1 = add_drone(
        net,
        name="drone1",
        ip="10.0.0.1/24",
        position="30,50,0",
        role="initial_member"
    )

    drone2 = add_drone(
        net,
        name="drone2",
        ip="10.0.0.2/24",
        position="40,60,0",
        role="initial_member"
    )

    # drone3 começa legítimo, mas depois será comprometido/revogado.
    drone3 = add_drone(
        net,
        name="drone3",
        ip="10.0.0.3/24",
        position="60,60,0",
        role="compromised_member",
        compromised="true"
    )

    drone4 = add_drone(
        net,
        name="drone4",
        ip="10.0.0.4/24",
        position="70,50,0",
        role="initial_member"
    )

    nodes = [auth, drone1, drone2, drone3, drone4]

    configure_and_start(net)
    prepare_all(nodes, SCENARIO)

    start_metrics_all(nodes, SCENARIO)

    # t=2: iniciar autoridade
    wait_event(2, "starting central authority")
    start_auth_server(auth, scenario_name=SCENARIO)

    # t=5: formar grupo completo, incluindo drone3 ainda aceito
    wait_event(3, "forming group before compromise is detected")
    for drone in [drone1, drone2, drone3, drone4]:
        start_group_member(drone)

    # t=15: tráfego normal
    wait_event(10, "starting normal group traffic")
    for drone in [drone1, drone2, drone3, drone4]:
        start_group_traffic_receiver(drone)

    start_group_traffic_sender(drone1, dst="10.0.0.255", port=5001, rate="10pps")

    # t=30: drone3 começa comportamento malicioso
    wait_event(15, "drone3 starts malicious behavior")
    start_malicious_behavior(drone3)

    # t=35: autoridade revoga drone3
    wait_event(5, "auth server revokes drone3")
    start_revocation(auth, revoked_drone_id="drone3")

    # t=45: membros legítimos continuam comunicação após rekey/revogação
    wait_event(10, "legitimate members continue after revocation")
    start_group_traffic_sender(drone2, dst="10.0.0.255", port=5001, rate="10pps")

    # drone3 permanece no alcance para testar se continua recebendo/enviando.
    # Isso é importante para validar revogação lógica, não apenas remoção física.
    wait_event(25, "final measurement window with revoked drone still nearby")

    dump_logs_to_host(nodes, SCENARIO)
    open_cli_or_stop(net, cli=cli)


if __name__ == "__main__":
    setLogLevel("info")
    run(cli=True)