#!/usr/bin/python3

"""
topology_group_leave.py

Cenário:
- Grupo em rede ad hoc.
- drone4 sai voluntariamente do grupo.
"""

from mininet.log import setLogLevel, info

from common import (
    create_network,
    add_controller,
    create_base_group_topology,
    initialize_adhoc_experiment,
    start_group_member,
    request_leave,
    start_receiver,
    start_sender,
    test_connectivity,
    wait,
    finish
)


SCENARIO = "group_leave_adhoc"


def run(cli=True):
    net = create_network()

    info("*** Creating group leave over ad hoc network\n")

    add_controller(net)

    topology = create_base_group_topology(
        net,
        drone_roles={"drone4": "leaving_member"}
    )
    auth = topology["auth"]
    drone1 = topology["drone1"]
    drone2 = topology["drone2"]
    drone3 = topology["drone3"]
    drone4 = topology["drone4"]
    drones = topology["drones"]
    stations = topology["stations"]
    remaining_drones = [drone1, drone2, drone3]

    initialize_adhoc_experiment(net, stations, SCENARIO, auth=auth)

    wait(3, "forming group with four drones")
    for drone in drones:
        start_group_member(drone)

    wait(10, "starting group traffic")
    for drone in drones:
        start_receiver(drone)

    start_sender(drone1, dst="10.0.0.255", port=5001, rate="10pps")

    wait(15, "drone4 voluntarily leaves")
    request_leave(drone4)

    wait(5, "moving drone4 away after leave")
    drone4.setPosition("220,220,0")

    wait(10, "remaining drones continue communication")
    start_sender(drone2, dst="10.0.0.255", port=5001, rate="10pps")

    wait(20, "testing remaining connectivity")
    test_connectivity([auth] + remaining_drones)

    wait(20, "final measurement window")

    finish(net, cli=cli)


if __name__ == "__main__":
    setLogLevel("info")
    run(cli=True)