#!/usr/bin/env python3

"""
traffic_agent.py

UDP sender/receiver para medir latência fim-a-fim entre drones.

- sender: manda pacotes JSON com timestamp_unix.
- receiver: calcula (recv_time - timestamp_unix) e grava CSV.

Saídas:
  - Log em texto em stdout (capturado pelo redirect na topologia).
  - CSV em /tmp/drone-logs/traffic_latency.csv (apenas no receiver).
"""

import argparse
import csv
import json
import os
import socket
import threading
import time
from datetime import datetime


CSV_PATH = os.environ.get(
    "TRAFFIC_CSV",
    "/tmp/drone-logs/traffic_latency.csv",
)
SCENARIO = os.environ.get("SCENARIO", "default")

_CSV_LOCK = threading.Lock()


def now():
    return datetime.utcnow().isoformat() + "Z"


def log(msg):
    print(f"[{now()}] [traffic-agent] {msg}", flush=True)


def emit_rx(
    receiver,
    sender,
    seq,
    nbytes,
    latency_ms,
    src_ip,
    src_port,
):
    new_file = not os.path.exists(CSV_PATH)
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

    with _CSV_LOCK:
        with open(CSV_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow([
                    "timestamp_utc",
                    "scenario",
                    "receiver",
                    "sender",
                    "src_ip",
                    "src_port",
                    "seq",
                    "bytes",
                    "latency_ms",
                ])
            w.writerow([
                now(),
                SCENARIO,
                receiver,
                sender if sender is not None else "",
                src_ip,
                src_port,
                seq if seq is not None else "",
                nbytes,
                f"{latency_ms:.3f}" if latency_ms is not None else "",
            ])


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
    sock.settimeout(1.0)

    receiver_name = socket.gethostname()
    log(f"receiver started on 0.0.0.0:{args.port} as {receiver_name}")

    received = 0
    start_t = time.time()

    while True:
        if args.duration and (time.time() - start_t) >= args.duration:
            log(f"receiver duration reached, exiting (received={received})")
            return

        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue

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
            try:
                latency_ms = (recv_time - float(sent_ts)) * 1000
            except Exception:
                latency_ms = None

        log(
            f"received count={received} "
            f"from={addr[0]}:{addr[1]} "
            f"sender={sender} "
            f"seq={seq} "
            f"bytes={len(data)} "
            f"latency_ms={latency_ms if latency_ms is not None else 'NA'}"
        )

        emit_rx(
            receiver=receiver_name,
            sender=sender,
            seq=seq,
            nbytes=len(data),
            latency_ms=latency_ms,
            src_ip=addr[0],
            src_port=addr[1],
        )


def run_sender(args):
    interval = parse_rate(args.rate)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Mantém broadcast permitido para quem precisar usar 10.0.0.255.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    log(
        f"sender started dst={args.dst}:{args.port} "
        f"rate={args.rate} interval={interval}s"
    )

    seq = 0
    start_time = time.time()

    while True:
        if args.duration and (time.time() - start_time) >= args.duration:
            log(f"sender duration reached, exiting (sent={seq})")
            return

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
        try:
            sock.sendto(data, (args.dst, args.port))
        except Exception as exc:
            log(f"sender error seq={seq} error={exc}")
            time.sleep(interval)
            continue

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
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="0 = run forever; >0 = seconds before exit",
    )

    args = parser.parse_args()

    if args.role == "receiver":
        run_receiver(args)
    elif args.role == "sender":
        run_sender(args)


if __name__ == "__main__":
    main()