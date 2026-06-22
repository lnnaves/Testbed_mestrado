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
    finish,
    parse_experiment_args,
    run_experiment_runs
)


SCENARIO = "group_auth_centralized_adhoc"


def run(
    cli=True,
    traffic_rate="10pps",
    group_id="mission-alpha",
    ssid="drone-adhoc-net",
    channel=5,
    mode="g",
    movement_steps=1,    # accepted for interface uniformity; not used in this scenario
    movement_interval=1.0  # accepted for interface uniformity; not used in this scenario
):
    net = create_network()

    info("*** Creating centralized group authentication over ad hoc network\n")

    add_controller(net)

    topology = create_base_group_topology(net)
    auth = topology["auth"]
    drone1 = topology["drone1"]
    drones = topology["drones"]
    stations = topology["stations"]

    initialize_adhoc_experiment(
        net, stations, SCENARIO, auth=auth,
        ssid=ssid, channel=channel, mode=mode
    )

    wait(3, "drones authenticate with central authority")
    for drone in drones:
        start_group_member(drone, group_id=group_id)

    wait(10, "starting group traffic")
    for drone in drones:
        start_receiver(drone)

    start_sender(drone1, dst="10.0.0.255", port=5001, rate=traffic_rate)

    wait(30, "steady-state measurement")

    finish(net, cli=cli)


if __name__ == "__main__":
    setLogLevel("info")
    args = parse_experiment_args("Centralized group authentication experiment")

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