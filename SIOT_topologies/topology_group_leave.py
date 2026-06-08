#!/usr/bin/python3

"""
topology_group_leave.py

Cenário:
- Grupo inicial autenticado.
- Um drone sai voluntariamente do grupo.

Objetivo:
- Avaliar o custo de saída voluntária.
- Medir rekeying, continuidade da comunicação e impacto nos membros restantes.

Evento principal:
- drone4 envia evento de leave.
- Grupo atualiza estado/chave.
- drone4 deixa de participar da comunicação segura.

Métricas:
- Tempo de leave.
- Tempo de rekeying.
- Perda durante atualização.
- Continuidade da comunicação.
- Mensagens de controle.
- Capacidade do ex-membro de acessar mensagens futuras.
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
    start_leave_request,
    start_group_traffic_receiver,
    start_group_traffic_sender,
    start_metrics_all,
    wait_event,
    dump_logs_to_host,
    open_cli_or_stop
)


SCENARIO = "group_leave"


def run(cli=True):
    net = create_network()

    info("*** Creating group leave scenario\n")

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
        role="leaving_member"
    )

    nodes = [auth, drone1, drone2, drone3, drone4]

    configure_and_start(net)
    prepare_all(nodes, SCENARIO)

    start_metrics_all(nodes, SCENARIO)

    # t=2: iniciar autoridade
    wait_event(2, "starting central authority")
    start_auth_server(auth, scenario_name=SCENARIO)

    # t=5: formar grupo completo
    wait_event(3, "forming group with four drones")
    for drone in [drone1, drone2, drone3, drone4]:
        start_group_member(drone)

    # t=15: iniciar tráfego normal
    wait_event(10, "starting normal group traffic")
    for drone in [drone1, drone2, drone3, drone4]:
        start_group_traffic_receiver(drone)

    start_group_traffic_sender(drone1, dst="10.0.0.255", port=5001, rate="10pps")

    # t=30: drone4 sai voluntariamente
    wait_event(15, "drone4 sending leave request")
    start_leave_request(drone4)

    # Opcional: mover drone4 para fora do alcance após saída
    wait_event(5, "moving drone4 away after voluntary leave")
    drone4.setPosition("180,180,0")

    # t=45: tráfego continua entre membros restantes
    wait_event(10, "continuing traffic among remaining members")
    start_group_traffic_sender(drone2, dst="10.0.0.255", port=5001, rate="10pps")

    wait_event(20, "final measurement window")

    dump_logs_to_host(nodes, SCENARIO)
    open_cli_or_stop(net, cli=cli)


if __name__ == "__main__":
    setLogLevel("info")
    run(cli=True)