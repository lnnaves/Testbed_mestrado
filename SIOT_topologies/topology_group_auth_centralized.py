#!/usr/bin/python3

"""
topology_group_auth_centralized.py

Cenário:
- Formação inicial de grupo com autoridade central lógica.
- Comunicação wireless em modo ad hoc.
- Todos os drones são containers Docker via DockerSta.
"""

from mininet.log import setLogLevel, info

from common import (
    create_network,
    add_controller,
    create_base_group_topology,
    initialize_adhoc_experiment,
    start_group_member,
    start_receiver,
    start_sender,
    wait,
    finish
)


SCENARIO = "group_auth_centralized_adhoc"


def run(cli=True):
    net = create_network()

    info("*** Creating centralized group authentication over ad hoc network\n")

    add_controller(net)

    topology = create_base_group_topology(net)
    auth = topology["auth"]
    drone1 = topology["drone1"]
    drones = topology["drones"]
    stations = topology["stations"]

    initialize_adhoc_experiment(net, stations, SCENARIO, auth=auth)

    wait(3, "drones authenticate with central authority")
    for drone in drones:
        start_group_member(drone)

    wait(10, "starting group traffic")
    for drone in drones:
        start_receiver(drone)

    start_sender(drone1, dst="10.0.0.255", port=5001, rate="10pps")

    wait(30, "steady-state measurement")

    finish(net, cli=cli)


if __name__ == "__main__":
    setLogLevel("info")
    run(cli=True)