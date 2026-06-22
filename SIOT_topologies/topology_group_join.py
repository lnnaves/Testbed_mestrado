#!/usr/bin/python3

"""
topology_group_join.py

Cenário:
- Grupo inicial em rede ad hoc.
- drone4 começa fora do alcance.
- drone4 entra no alcance e solicita entrada no grupo.
"""

from mininet.log import setLogLevel, info

from common import (
    create_network,
    add_controller,
    create_base_group_topology,
    initialize_adhoc_experiment,
    start_group_member,
    request_join,
    start_receiver,
    start_sender,
    test_connectivity,
    wait,
    finish,
    parse_experiment_args,
    run_experiment_runs,
    move_node_in_steps
)


SCENARIO = "group_join_adhoc"


def run(
    cli=True,
    traffic_rate="10pps",
    group_id="mission-alpha",
    ssid="drone-adhoc-net",
    channel=5,
    mode="g",
    movement_steps=1,
    movement_interval=1.0
):
    net = create_network()

    info("*** Creating group join over ad hoc network\n")

    add_controller(net)

    topology = create_base_group_topology(
        net,
        drone_positions={
            "drone1": "35,50,0",
            "drone2": "45,60,0",
            "drone3": "60,55,0",
            "drone4": "220,220,0"
        },
        drone_roles={
            "drone1": "initial_member",
            "drone2": "initial_member",
            "drone3": "initial_member",
            "drone4": "joining_member"
        }
    )
    auth = topology["auth"]
    drone1 = topology["drone1"]
    drone2 = topology["drone2"]
    drone3 = topology["drone3"]
    drone4 = topology["drone4"]
    stations = topology["stations"]
    initial_drones = [drone1, drone2, drone3]

    initialize_adhoc_experiment(
        net,
        stations,
        SCENARIO,
        connectivity_nodes=[auth] + initial_drones,
        auth=auth,
        ssid=ssid,
        channel=channel,
        mode=mode
    )

    wait(3, "forming initial group")
    for drone in initial_drones:
        start_group_member(drone, group_id=group_id)

    wait(10, "starting initial group traffic")
    for drone in initial_drones:
        start_receiver(drone)

    start_sender(drone1, dst="10.0.0.255", port=5001, rate=traffic_rate)

    wait(15, "moving drone4 into ad hoc network range")
    move_node_in_steps(drone4, "75,55,0", steps=movement_steps, interval=movement_interval)

    wait(5, "testing connectivity after drone4 movement")
    test_connectivity([auth, drone1, drone2, drone3, drone4])

    wait(2, "drone4 requests group join")
    start_receiver(drone4)
    request_join(drone4, group_id=group_id)

    wait(20, "measurement after join")
    start_sender(drone2, dst="10.0.0.255", port=5001, rate=traffic_rate)

    wait(20, "final measurement window")

    finish(net, cli=cli)


if __name__ == "__main__":
    setLogLevel("info")
    args = parse_experiment_args("Group join experiment")

    def run_once(run_id, open_cli):
        run(
            cli=open_cli,
            traffic_rate=args.traffic_rate,
            group_id=args.group_id,
            ssid=args.ssid,
            channel=args.channel,
            mode=args.mode,
            movement_steps=args.movement_steps,
            movement_interval=args.movement_interval,
        )

    run_experiment_runs(run_once, runs=args.runs, cli=not args.no_cli)