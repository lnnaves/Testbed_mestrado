#!/usr/bin/env python3

import argparse
import json
import socket
import time
from datetime import datetime


def now():
    return datetime.utcnow().isoformat() + "Z"


def log(msg):
    print(f"[{now()}] [traffic-agent] {msg}", flush=True)


def parse_rate(rate):
    """
    Aceita:
    - 10pps
    - 1pps
    - 0.5pps
    """
    rate = str(rate).lower().strip()

    if rate.endswith("pps"):
        value = float(rate.replace("pps", ""))
        if value <= 0:
            return 1.0
        return 1.0 / value

    return 1.0


def run_receiver(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))

    log(f"receiver started on 0.0.0.0:{args.port}")

    received = 0

    while True:
        data, addr = sock.recvfrom(65535)
        received += 1
        recv_time = time.time()

        try:
            payload = json.loads(data.decode("utf-8"))
        except Exception:
            payload = {
                "raw": data.decode("utf-8", errors="replace")
            }

        seq = payload.get("seq")
        sender = payload.get("sender")
        sent_ts = payload.get("timestamp_unix")

        latency_ms = None
        if sent_ts is not None:
            latency_ms = (recv_time - float(sent_ts)) * 1000

        log(
            f"received count={received} "
            f"from={addr[0]}:{addr[1]} "
            f"sender={sender} "
            f"seq={seq} "
            f"bytes={len(data)} "
            f"latency_ms={latency_ms if latency_ms is not None else 'NA'} "
            f"payload={payload}"
        )


def run_sender(args):
    interval = parse_rate(args.rate)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Necessário para envio para 10.0.0.255 ou 255.255.255.255.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    log(
        f"sender started dst={args.dst}:{args.port} "
        f"rate={args.rate} interval={interval}s"
    )

    seq = 0
    start_time = time.time()

    while True:
        seq += 1

        payload = {
            "type": "group_traffic",
            "sender": socket.gethostname(),
            "seq": seq,
            "timestamp": now(),
            "timestamp_unix": time.time(),
            "message": args.message,
        }

        data = json.dumps(payload).encode("utf-8")
        sock.sendto(data, (args.dst, args.port))

        log(
            f"sent seq={seq} dst={args.dst}:{args.port} "
            f"bytes={len(data)} elapsed_s={time.time() - start_time:.3f}"
        )

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="UDP traffic generator/receiver")

    parser.add_argument("--role", required=True, choices=["sender", "receiver"])
    parser.add_argument("--dst", default="10.0.0.255")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--rate", default="10pps")
    parser.add_argument("--message", default="simulated telemetry message")

    args = parser.parse_args()

    if args.role == "receiver":
        run_receiver(args)
    elif args.role == "sender":
        run_sender(args)


if __name__ == "__main__":
    main()