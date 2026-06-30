#!/usr/bin/python3

"""
topology_group_revocation.py

Cenário:
- Grupo em rede ad hoc.
- drone3 começa como membro legítimo.
- drone3 passa a agir de forma maliciosa.
- autoridade central revoga drone3.
- drone3 permanece no alcance tentando comunicar.

Suporta varredura de campanha:
- --num-drones N para variar o tamanho do grupo (4, 8, 16, 32).
- --rekey-scheme naive|lkh para escolher o esquema de rekey medido.
- --fast / --wait-scale para encurtar os waits em campanhas grandes.
Ao final de cada run, os CSVs in-container (protocol_latency.csv,
traffic_loss.csv) são copiados para <metrics-dir>/run-<id>/ para que o
run_campaign.py possa consolidá-los.
"""

from mininet.log import setLogLevel, info

from common import (
    create_network,
    add_controller,
    create_base_group_topology,
    initialize_adhoc_experiment,
    start_group_member,
    revoke_member,
    start_receiver,
    start_sender,
    start_malicious_traffic,
    test_connectivity,
    wait,
    finish,
    parse_experiment_args,
    run_experiment_runs,
    build_metrics_file,
    record_event_metric,
    measure_rtt_matrix,
    collect_incontainer_csvs,
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
    num_drones=4,
    rekey_scheme="naive",
):
    net = create_network()

    info("*** Creating group revocation over ad hoc network\n")

    add_controller(net)

    topology = create_base_group_topology(
        net,
        drone_roles={"drone3": "compromised_member"},
        num_drones=num_drones
    )
    auth = topology["auth"]
    drone1 = topology["drone1"]
    drone2 = topology["drone2"]
    drone3 = topology["drone3"]
    drone4 = topology["drone4"]
    drones = topology["drones"]
    stations = topology["stations"]
    # Legítimos após a revogação: todos os drones menos o revogado (drone3).
    legitimate_after_revocation = [d for d in drones if d.name != "drone3"]

    metrics_file = build_metrics_file(SCENARIO, run_id=run_id, output_dir=metrics_dir)
    info(f"*** Metrics file: {metrics_file}\n")

    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="scenario_start", phase="bootstrap",
        node="orchestrator", status="started",
        extra=f"num_drones={num_drones},rekey_scheme={rekey_scheme}"
    )

    initialize_adhoc_experiment(
        net, stations, SCENARIO, auth=auth,
        rekey_scheme=rekey_scheme,
        ssid=ssid, channel=channel, mode=mode
    )

    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="auth_server_start", phase="bootstrap",
        node=auth.name, status="started",
        extra=f"rekey_scheme={rekey_scheme}"
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

    wait(10, "starting normal group traffic")
    for drone in drones:
        start_receiver(drone)

    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="traffic_start", phase="pre_revocation_traffic",
        node=drone1.name, status="started"
    )
    start_sender(drone1, dst="10.0.0.255", port=5001, rate=traffic_rate)

    wait(15, "drone3 starts malicious behavior")
    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="malicious_traffic_start", phase="compromise",
        node=drone3.name, status="started"
    )
    start_malicious_traffic(drone3, dst="10.0.0.255", port=5001)

    wait(5, "central authority revokes drone3")
    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="revocation_requested", phase="revocation",
        node=auth.name, target=drone3.name, status="started"
    )
    revoke_member(auth, target="drone3", group_id=group_id)

    measure_rtt_matrix(
        stations,
        count=ping_count, timeout=ping_timeout,
        metrics_file=metrics_file, scenario=SCENARIO, run_id=run_id,
        phase="post_revocation"
    )

    wait(10, "legitimate drones continue after revocation")
    record_event_metric(
        metrics_file, SCENARIO, run_id,
        event="traffic_start", phase="post_revocation_traffic",
        node=drone2.name, status="started"
    )
    start_sender(drone2, dst="10.0.0.255", port=5001, rate=traffic_rate)

    wait(15, "testing connectivity after revocation")
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

    # Coleta os CSVs gerados dentro dos containers para o host, para que o
    # run_campaign.py consiga consolidar figure1/figure2.
    collect_incontainer_csvs(
        [auth] + drones,
        run_id=run_id,
        output_dir=metrics_dir,
    )

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
            num_drones=args.num_drones,
            rekey_scheme=args.rekey_scheme,
        )

    run_experiment_runs(run_once, runs=args.runs, cli=not args.no_cli)
