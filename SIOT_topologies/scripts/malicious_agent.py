#!/usr/bin/env python3

import argparse
import json
import socket
import time
from datetime import datetime


def now():
    return datetime.utcnow().isoformat() + "Z"


def log(msg):
    print(f"[{now()}] [malicious-agent] {msg}", flush=True)


def parse_rate(rate):
    rate = str(rate).lower().strip()

    if rate.endswith("pps"):
        value = float(rate.replace("pps", ""))
        if value <= 0:
            return 1.0
        return 1.0 / value

    return 0.2


def run_old_key_traffic(args):
    interval = parse_rate(args.rate)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    seq = 0
    start = time.time()

    log(
        f"malicious traffic started "
        f"drone_id={args.drone_id} "
        f"mode={args.mode} "
        f"dst={args.dst}:{args.port} "
        f"rate={args.rate}"
    )

    while True:
        seq += 1

        payload = {
            "type": "malicious_group_traffic",
            "mode": args.mode,
            "drone_id": args.drone_id,
            "seq": seq,
            "timestamp": now(),
            "timestamp_unix": time.time(),
            "claim": "using_old_group_key_or_revoked_credentials",
            "command": "FAKE_COMMAND_CHANGE_ROUTE",
        }

        data = json.dumps(payload).encode("utf-8")
        sock.sendto(data, (args.dst, args.port))

        log(
            f"sent malicious seq={seq} "
            f"dst={args.dst}:{args.port} "
            f"bytes={len(data)} "
            f"elapsed_s={time.time() - start:.3f}"
        )

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Simulated malicious drone behavior")

    parser.add_argument("--drone-id", required=True)
    parser.add_argument("--mode", default="old-key-traffic")
    parser.add_argument("--dst", default="10.0.0.255")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--rate", default="5pps")

    args = parser.parse_args()

    if args.mode in ["old-key-traffic", "flood", "fake-command"]:
        run_old_key_traffic(args)
    else:
        log(f"unsupported malicious mode={args.mode}")


if __name__ == "__main__":
    main()