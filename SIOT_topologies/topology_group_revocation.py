#!/usr/bin/python3

"""
topology_group_revocation.py

Cenário:
- Grupo em rede ad hoc.
- drone3 começa como membro legítimo.
- drone3 passa a agir de forma maliciosa.
- autoridade central revoga drone3.
- drone3 permanece no alcance tentando comunicar.
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
    run_experiment_runs
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
    movement_interval=1.0  # accepted for interface uniformity; not used in this scenario
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

    initialize_adhoc_experiment(
        net, stations, SCENARIO, auth=auth,
        ssid=ssid, channel=channel, mode=mode
    )

    wait(3, "forming group before compromise detection")
    for drone in drones:
        start_group_member(drone, group_id=group_id)

    wait(10, "starting normal group traffic")
    for drone in drones:
        start_receiver(drone)

    start_sender(drone1, dst="10.0.0.255", port=5001, rate=traffic_rate)

    wait(15, "drone3 starts malicious behavior")
    start_malicious_traffic(drone3, dst="10.0.0.255", port=5001)

    wait(5, "central authority revokes drone3")
    revoke_member(auth, target="drone3", group_id=group_id)

    wait(10, "legitimate drones continue after revocation")
    start_sender(drone2, dst="10.0.0.255", port=5001, rate=traffic_rate)

    wait(15, "testing connectivity after revocation")
    test_connectivity([auth] + legitimate_after_revocation)

    # drone3 continua fisicamente perto.
    # Isso é intencional: queremos testar exclusão lógica, não desconexão física.
    wait(25, "revoked drone remains nearby for validation")

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
        )

    run_experiment_runs(run_once, runs=args.runs, cli=not args.no_cli)