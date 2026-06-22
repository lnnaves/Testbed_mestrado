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
    run_experiment_runs,
    build_metrics_file,
    record_event_metric,
    measure_rtt_matrix,
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
    movement_interval=1.0,  # accepted for interface uniformity; not used in this scenario
    run_id=0,
    metrics_dir="./results",
    ping_count=5,
    ping_timeout=1,
):
    net = create_network()

    info("*** Creating centralized group authentication over ad hoc network\n")

    add_controller(net)

    topology = create_base_group_topology(net)
    auth = topology["auth"]
    drone1 = topology["drone1"]
    drones = topology["drones"]
    stations = topology["stations"]

    metrics_file = build_metrics_file(SCENARIO, run_id=run_id, output_dir=metrics_dir)
    info(f"*** Metrics file: {metrics_file}\n")

    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="scenario_start", phase="bootstrap",
        node="orchestrator", status="started"
    )

    initialize_adhoc_experiment(
        net, stations, SCENARIO, auth=auth,
        ssid=ssid, channel=channel, mode=mode
    )

    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="auth_server_start", phase="bootstrap",
        node=auth.name, status="started"
    )

    wait(3, "drones authenticate with central authority")
    for drone in drones:
        record_event_metric(
            metrics_file, SCENARIO, run_id,
            event="member_auth_requested", phase="auth",
            node=drone.name, target=auth.name, status="started"
        )
        start_group_member(drone, group_id=group_id)

    measure_rtt_matrix(
        stations,
        count=ping_count, timeout=ping_timeout,
        metrics_file=metrics_file, scenario=SCENARIO, run_id=run_id,
        phase="post_auth"
    )

    wait(10, "starting group traffic")
    for drone in drones:
        start_receiver(drone)

    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="traffic_start", phase="steady_state",
        node=drone1.name, status="started"
    )
    start_sender(drone1, dst="10.0.0.255", port=5001, rate=traffic_rate)

    wait(15, "steady-state measurement (first window)")
    measure_rtt_matrix(
        stations,
        count=ping_count, timeout=ping_timeout,
        metrics_file=metrics_file, scenario=SCENARIO, run_id=run_id,
        phase="steady_state"
    )

    wait(15, "steady-state measurement (second window)")

    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="scenario_end", phase="teardown",
        node="orchestrator", status="completed"
    )

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
            run_id=run_id,
            metrics_dir=args.metrics_dir,
            ping_count=args.ping_count,
            ping_timeout=args.ping_timeout,
        )

    run_experiment_runs(run_once, runs=args.runs, cli=not args.no_cli)