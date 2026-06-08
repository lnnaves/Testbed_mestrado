#!/usr/bin/python3

"""
topology_group_join.py

Cenário:
- Grupo inicial já autenticado.
- Um novo drone entra no grupo durante a missão.

Objetivo:
- Avaliar impacto da entrada dinâmica de um novo drone.
- Medir tempo de join, rekeying e impacto no tráfego dos membros existentes.

Evento principal:
- drone4 entra no alcance e solicita entrada no grupo.

Métricas:
- Tempo de join.
- Tempo de rekeying.
- Perda durante admissão.
- Interrupção do tráfego.
- Mensagens de controle.
- CPU/memória durante o evento.
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
    start_join_request,
    start_group_traffic_receiver,
    start_group_traffic_sender,
    start_metrics_all,
    wait_event,
    dump_logs_to_host,
    open_cli_or_stop
)


SCENARIO = "group_join"


def run(cli=True):
    net = create_network()

    info("*** Creating group join scenario\n")

    add_controller(net)
    add_group_ap(net)

    auth = add_auth_server(net, name="auth", ip="10.0.0.100/24")

    # Grupo inicial
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

    drone3 = add_drone(
        net,
        name="drone3",
        ip="10.0.0.3/24",
        position="60,60,0",
        role="initial_member"
    )

    # Novo drone: começa distante ou logicamente fora do grupo.
    # A posição pode ser ajustada para simular entrada no alcance.
    drone4 = add_drone(
        net,
        name="drone4",
        ip="10.0.0.4/24",
        position="180,180,0",
        role="joining_member"
    )

    nodes = [auth, drone1, drone2, drone3, drone4]

    configure_and_start(net)
    prepare_all(nodes, SCENARIO)

    start_metrics_all(nodes, SCENARIO)

    # t=2: autoridade inicia
    wait_event(2, "starting central authority")
    start_auth_server(auth, scenario_name=SCENARIO)

    # t=5: grupo inicial é autenticado
    wait_event(3, "forming initial group")
    for drone in [drone1, drone2, drone3]:
        start_group_member(drone)

    # t=15: tráfego normal do grupo inicial
    wait_event(10, "starting traffic for initial group")
    for drone in [drone1, drone2, drone3]:
        start_group_traffic_receiver(drone)

    start_group_traffic_sender(drone1, dst="10.0.0.255", port=5001, rate="10pps")

    # t=30: drone4 entra fisicamente no alcance
    wait_event(15, "moving new drone into group range")
    drone4.setPosition("75,55,0")

    # t=35: drone4 solicita entrada
    wait_event(5, "drone4 requesting group join")
    start_group_traffic_receiver(drone4)
    start_join_request(drone4)

    # t=50: tráfego continua já com drone4 no grupo
    wait_event(15, "collecting metrics after join")
    start_group_traffic_sender(drone2, dst="10.0.0.255", port=5001, rate="10pps")

    wait_event(20, "final measurement window")

    dump_logs_to_host(nodes, SCENARIO)
    open_cli_or_stop(net, cli=cli)


if __name__ == "__main__":
    setLogLevel("info")
    run(cli=True)