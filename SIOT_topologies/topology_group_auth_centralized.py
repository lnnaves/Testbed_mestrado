#!/usr/bin/python3

"""
topology_group_auth_centralized.py

Cenário:
- Formação inicial de grupo com autoridade central.

Objetivo:
- Avaliar o custo de formar um grupo autenticado de drones.
- A autoridade central pode representar GCS, Auth Server ou KDC.

Evento principal:
- Todos os drones se autenticam com a autoridade central.
- Após a formação do grupo, o tráfego de missão é iniciado.

Métricas:
- Tempo de formação do grupo.
- Tempo médio de autenticação por drone.
- Número de mensagens de controle.
- Bytes de controle.
- CPU/memória da autoridade.
- Latência e perda após formação.
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
    start_group_traffic_receiver,
    start_group_traffic_sender,
    start_metrics_all,
    wait_event,
    dump_logs_to_host,
    open_cli_or_stop
)


SCENARIO = "centralized_group_auth"


def run(cli=True):
    net = create_network()

    info("*** Creating centralized group authentication scenario\n")

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

    drone3 = add_drone(
        net,
        name="drone3",
        ip="10.0.0.3/24",
        position="60,60,0",
        role="initial_member"
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

    # t=0: iniciar coleta de métricas
    start_metrics_all(nodes, SCENARIO)

    # t=2: iniciar autoridade central
    wait_event(2, "starting central authority")
    start_auth_server(auth, scenario_name=SCENARIO)

    # t=5: drones iniciam autenticação/formação do grupo
    wait_event(3, "starting group authentication for initial members")
    for drone in [drone1, drone2, drone3, drone4]:
        start_group_member(drone)

    # t=15: tráfego seguro de grupo começa
    wait_event(10, "starting group traffic after authentication")
    for drone in [drone1, drone2, drone3, drone4]:
        start_group_traffic_receiver(drone)

    start_group_traffic_sender(drone1, dst="10.0.0.255", port=5001, rate="10pps")

    # t=45: janela de medição
    wait_event(30, "collecting steady-state metrics")

    dump_logs_to_host(nodes, SCENARIO)
    open_cli_or_stop(net, cli=cli)


if __name__ == "__main__":
    setLogLevel("info")
    run(cli=True)