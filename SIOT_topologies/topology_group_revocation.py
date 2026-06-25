#!/usr/bin/python3

"""
topology_group_revocation.py

Cenário:
- Grupo em rede ad hoc.
- drone3 começa como membro legítimo.
- drone3 passa a agir de forma maliciosa.
- autoridade central revoga drone3.
- drone3 permanece no alcance tentando comunicar.
- Modo de missão realista: todos os membros legítimos atuais enviam e recebem UDP.
"""

from mininet.log import setLogLevel, info

from common_multi_sender import (
    create_network,
    add_controller,
    create_base_group_topology,
    initialize_adhoc_experiment,
    start_group_member,
    revoke_member,
    start_receivers_for,
    start_senders_for,
    stop_sender,
    start_malicious_traffic,
    test_connectivity,
    wait,
    finish,
    parse_experiment_args,
    run_experiment_runs,
    build_metrics_file,
    record_event_metric,
    measure_rtt_matrix,
)


SCENARIO = "group_revocation_adhoc"


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

    info("*** Creating group revocation over ad hoc network\n")

    add_controller(net)

    topology = create_base_group_topology(
        net,
        drone_roles={"drone3": "compromised_member"}
    )
    auth = topology["auth"]
    drone1 = topology["drone1"]
    drone2 = topology["drone2"]
    drone3 = topology["drone3"]
    drone4 = topology["drone4"]
    drones = topology["drones"]
    stations = topology["stations"]
    legitimate_after_revocation = [drone1, drone2, drone4]

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

    wait(3, "forming group before compromise detection")
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
        phase="pre_revocation"
    )

    wait(10, "starting normal group traffic with all current members")
    start_receivers_for(drones)

    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="traffic_start", phase="pre_revocation_traffic",
        node="all_members", status="started",
        extra="drone1, drone2, drone3 and drone4 are legitimate UDP senders and receivers"
    )
    start_senders_for(drones, dst="10.0.0.255", port=5001, rate=traffic_rate)

    wait(15, "drone3 starts malicious behavior while legitimate mission traffic continues")
    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="malicious_traffic_start", phase="compromise",
        node=drone3.name, status="started"
    )
    start_malicious_traffic(drone3, dst="10.0.0.255", port=5001)

    wait(5, "central authority revokes drone3 while traffic continues")
    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="revocation_requested", phase="revocation",
        node=auth.name, target=drone3.name, status="started"
    )
    revoke_member(auth, target="drone3", group_id=group_id)

    wait(2, "allowing revocation to complete before stopping drone3 legitimate traffic")
    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="traffic_membership_update", phase="post_revocation_traffic",
        node=drone3.name, status="stopped",
        extra="drone3 stops legitimate UDP sender after revocation; malicious-agent may continue"
    )
    stop_sender(drone3)

    measure_rtt_matrix(
        stations,
        count=ping_count, timeout=ping_timeout,
        metrics_file=metrics_file, scenario=SCENARIO, run_id=run_id,
        phase="post_revocation"
    )

    wait(10, "legitimate drones continue after revocation")

    test_connectivity([auth] + legitimate_after_revocation)

    measure_rtt_matrix(
        [auth] + legitimate_after_revocation,
        count=ping_count, timeout=ping_timeout,
        metrics_file=metrics_file, scenario=SCENARIO, run_id=run_id,
        phase="legitimate_only"
    )

    # drone3 continua fisicamente perto.
    # Isso é intencional: queremos testar exclusão lógica, não desconexão física.
    wait(25, "revoked drone remains nearby for validation")

    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="scenario_end", phase="teardown",
        node="orchestrator", status="completed"
    )

    finish(net, cli=cli)


if __name__ == "__main__":
    setLogLevel("info")
    args = parse_experiment_args("Group revocation experiment")

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
