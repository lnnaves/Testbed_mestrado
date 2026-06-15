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
    add_auth_server,
    add_drone,
    configure_adhoc_network,
    start_network,
    prepare_all,
    start_metrics_all,
    start_auth_server,
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

    auth = add_auth_server(
        net,
        name="auth1",
        ip="10.0.0.100/24",
        position="50,50,0",
        range_=130
    )

    drone1 = add_drone(
        net,
        name="drone1",
        ip="10.0.0.1/24",
        position="30,50,0",
        role="initial_member",
        range_=100
    )

    drone2 = add_drone(
        net,
        name="drone2",
        ip="10.0.0.2/24",
        position="40,60,0",
        role="initial_member",
        range_=100
    )

    drone3 = add_drone(
        net,
        name="drone3",
        ip="10.0.0.3/24",
        position="60,60,0",
        role="initial_member",
        range_=100
    )

    drone4 = add_drone(
        net,
        name="drone4",
        ip="10.0.0.4/24",
        position="70,50,0",
        role="leaving_member",
        range_=100
    )

    stations = [auth, drone1, drone2, drone3, drone4]
    drones = [drone1, drone2, drone3, drone4]
    remaining_drones = [drone1, drone2, drone3]

    configure_adhoc_network(
        net,
        stations,
        ssid="drone-adhoc-net",
        channel=5,
        mode="g"
    )

    start_network(net)

    prepare_all(stations, SCENARIO)
    start_metrics_all(stations, SCENARIO)

    wait(3, "testing ad hoc connectivity")
    test_connectivity(stations)

    wait(2, "starting central authority")
    start_auth_server(auth, SCENARIO)

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