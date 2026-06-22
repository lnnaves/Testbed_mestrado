#!/usr/bin/env python3

"""
group_auth.py

Agente do protocolo de autenticação em grupo.

Modos (--role):
  auth-server  : sobe o servidor TCP 9000 e mantém GroupState.
  member       : registra no auth e entra em loop de heartbeat.
  joiner       : faz join (ou --event join em qualquer role).
  member --event leave : faz leave.
  auth-server --event revoke --target X : revoga um drone (executado dentro do auth).

Saídas:
  - Log em texto livre em stdout (capturado pelo redirect na topologia).
  - CSV estruturado em /tmp/drone-logs/protocol_latency.csv com uma linha
    por evento medido. Esse é o arquivo que você usa para análise.
"""

import argparse
import csv
import json
import os
import socket
import socketserver
import threading
import time
from datetime import datetime


# ============================================================
# Logging / utilidades
# ============================================================

CSV_PATH = os.environ.get(
    "PROTO_CSV",
    "/tmp/drone-logs/protocol_latency.csv",
)
SCENARIO = os.environ.get("SCENARIO", "default")

_CSV_LOCK = threading.Lock()


def now():
    return datetime.utcnow().isoformat() + "Z"


def log(msg):
    print(f"[{now()}] [group-auth] {msg}", flush=True)


def emit_event(
    event_type,
    role,
    drone_id,
    group_id,
    epoch,
    elapsed_ms,
    status,
    extra="",
):
    """
    Escreve uma linha CSV por evento medido.
    Cabeçalho é escrito apenas na primeira vez que o arquivo é criado.
    """
    new_file = not os.path.exists(CSV_PATH)

    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

    with _CSV_LOCK:
        with open(CSV_PATH, "a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow([
                    "timestamp_utc",
                    "scenario",
                    "role",
                    "event",
                    "drone_id",
                    "group_id",
                    "epoch",
                    "elapsed_ms",
                    "status",
                    "extra",
                ])
            w.writerow([
                now(),
                SCENARIO,
                role,
                event_type,
                drone_id if drone_id is not None else "",
                group_id if group_id is not None else "",
                epoch if epoch is not None else "",
                f"{elapsed_ms:.3f}" if elapsed_ms is not None else "",
                status if status is not None else "",
                extra,
            ])


# ============================================================
# Estado do grupo (no servidor)
# ============================================================

class GroupState:
    def __init__(self, group_id):
        self.group_id = group_id
        self.members = set()
        self.revoked = set()
        self.epoch = 1
        self.lock = threading.Lock()

    def register(self, drone_id):
        with self.lock:
            if drone_id in self.revoked:
                return {
                    "status": "denied",
                    "reason": "drone_revoked",
                    "group_id": self.group_id,
                    "epoch": self.epoch,
                }

            self.members.add(drone_id)
            return {
                "status": "accepted",
                "event": "register",
                "drone_id": drone_id,
                "group_id": self.group_id,
                "epoch": self.epoch,
                "members": sorted(self.members),
            }

    def join(self, drone_id):
        with self.lock:
            if drone_id in self.revoked:
                return {
                    "status": "denied",
                    "reason": "drone_revoked",
                    "group_id": self.group_id,
                    "epoch": self.epoch,
                }

            self.members.add(drone_id)
            self.epoch += 1

            return {
                "status": "accepted",
                "event": "join",
                "drone_id": drone_id,
                "group_id": self.group_id,
                "epoch": self.epoch,
                "members": sorted(self.members),
                "note": "simulated_rekey_after_join",
            }

    def leave(self, drone_id):
        with self.lock:
            self.members.discard(drone_id)
            self.epoch += 1

            return {
                "status": "accepted",
                "event": "leave",
                "drone_id": drone_id,
                "group_id": self.group_id,
                "epoch": self.epoch,
                "members": sorted(self.members),
                "note": "simulated_rekey_after_leave",
            }

    def revoke(self, drone_id):
        with self.lock:
            self.members.discard(drone_id)
            self.revoked.add(drone_id)
            self.epoch += 1

            return {
                "status": "accepted",
                "event": "revoke",
                "target": drone_id,
                "group_id": self.group_id,
                "epoch": self.epoch,
                "members": sorted(self.members),
                "revoked": sorted(self.revoked),
                "note": "simulated_rekey_after_revocation",
            }

    def status(self):
        with self.lock:
            return {
                "status": "ok",
                "group_id": self.group_id,
                "epoch": self.epoch,
                "members": sorted(self.members),
                "revoked": sorted(self.revoked),
            }


# ============================================================
# Handler TCP do servidor
# ============================================================

class AuthTCPHandler(socketserver.StreamRequestHandler):
    group_state = None

    def handle(self):
        peer = self.client_address
        raw = self.rfile.readline().decode("utf-8").strip()

        if not raw:
            return

        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            response = {"status": "error", "reason": "invalid_json"}
            self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))
            return

        event = request.get("event")
        drone_id = request.get("drone_id")
        target = request.get("target")

        log(f"received request from {peer}: {request}")

        if event == "register":
            response = self.group_state.register(drone_id)
        elif event == "join":
            response = self.group_state.join(drone_id)
        elif event == "leave":
            response = self.group_state.leave(drone_id)
        elif event == "revoke":
            response = self.group_state.revoke(target)
        elif event == "status":
            response = self.group_state.status()
        else:
            response = {
                "status": "error",
                "reason": "unknown_event",
                "received": request,
            }

        log(f"response: {response}")
        self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))


# ============================================================
# Cliente
# ============================================================

def parse_host_port(auth_server):
    if ":" not in auth_server:
        return auth_server, 9000

    host, port = auth_server.rsplit(":", 1)
    return host, int(port)


def send_request(host, port, payload, timeout=5):
    start = time.time()

    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))

        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk

    elapsed_ms = (time.time() - start) * 1000

    if data:
        response = json.loads(data.decode("utf-8").strip())
    else:
        response = {"status": "error", "reason": "empty_response"}

    return response, elapsed_ms


# ============================================================
# Modos de execução
# ============================================================

def run_auth_server(args):
    host = args.listen or "0.0.0.0"
    port = int(args.port or 9000)

    AuthTCPHandler.group_state = GroupState(args.group_id)

    server = socketserver.ThreadingTCPServer((host, port), AuthTCPHandler)
    server.daemon_threads = True

    log(f"auth server started on {host}:{port}, group_id={args.group_id}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("auth server interrupted")
    finally:
        server.server_close()
        log("auth server stopped")


def run_member(args):
    host, port = parse_host_port(args.auth_server)

    payload = {
        "event": "register",
        "drone_id": args.drone_id,
        "group_id": args.group_id,
        "timestamp": now(),
    }

    try:
        response, elapsed_ms = send_request(host, port, payload)
        status = response.get("status", "unknown")
        epoch = response.get("epoch")
        log(
            f"member={args.drone_id} register_response={response} "
            f"auth_time_ms={elapsed_ms:.3f}"
        )
        emit_event(
            "register",
            role="member",
            drone_id=args.drone_id,
            group_id=args.group_id,
            epoch=epoch,
            elapsed_ms=elapsed_ms,
            status=status,
        )
    except Exception as exc:
        log(f"member={args.drone_id} register_failed error={exc}")
        emit_event(
            "register",
            role="member",
            drone_id=args.drone_id,
            group_id=args.group_id,
            epoch=None,
            elapsed_ms=None,
            status="error",
            extra=str(exc),
        )

    start_t = time.time()
    while True:
        if args.duration and (time.time() - start_t) >= args.duration:
            log(f"member={args.drone_id} duration reached, exiting")
            return

        time.sleep(args.heartbeat_interval)

        status_payload = {
            "event": "status",
            "drone_id": args.drone_id,
            "group_id": args.group_id,
            "timestamp": now(),
        }

        try:
            response, elapsed_ms = send_request(host, port, status_payload)
            log(
                f"member={args.drone_id} heartbeat "
                f"epoch={response.get('epoch')} "
                f"members={response.get('members')} "
                f"revoked={response.get('revoked')} "
                f"rtt_ms={elapsed_ms:.3f}"
            )
            emit_event(
                "heartbeat",
                role="member",
                drone_id=args.drone_id,
                group_id=args.group_id,
                epoch=response.get("epoch"),
                elapsed_ms=elapsed_ms,
                status=response.get("status", "unknown"),
            )
        except Exception as exc:
            log(f"member={args.drone_id} heartbeat_failed error={exc}")
            emit_event(
                "heartbeat",
                role="member",
                drone_id=args.drone_id,
                group_id=args.group_id,
                epoch=None,
                elapsed_ms=None,
                status="error",
                extra=str(exc),
            )


def run_join(args):
    host, port = parse_host_port(args.auth_server)

    payload = {
        "event": "join",
        "drone_id": args.drone_id,
        "group_id": args.group_id,
        "timestamp": now(),
    }

    try:
        response, elapsed_ms = send_request(host, port, payload)
        log(
            f"joiner={args.drone_id} join_response={response} "
            f"join_time_ms={elapsed_ms:.3f}"
        )
        emit_event(
            "join",
            role="joiner",
            drone_id=args.drone_id,
            group_id=args.group_id,
            epoch=response.get("epoch"),
            elapsed_ms=elapsed_ms,
            status=response.get("status", "unknown"),
        )
    except Exception as exc:
        log(f"joiner={args.drone_id} join_failed error={exc}")
        emit_event(
            "join",
            role="joiner",
            drone_id=args.drone_id,
            group_id=args.group_id,
            epoch=None,
            elapsed_ms=None,
            status="error",
            extra=str(exc),
        )

    start_t = time.time()
    while True:
        if args.duration and (time.time() - start_t) >= args.duration:
            return
        time.sleep(5)


def run_leave(args):
    host, port = parse_host_port(args.auth_server)

    payload = {
        "event": "leave",
        "drone_id": args.drone_id,
        "group_id": args.group_id,
        "timestamp": now(),
    }

    try:
        response, elapsed_ms = send_request(host, port, payload)
        log(
            f"member={args.drone_id} leave_response={response} "
            f"leave_time_ms={elapsed_ms:.3f}"
        )
        emit_event(
            "leave",
            role="member",
            drone_id=args.drone_id,
            group_id=args.group_id,
            epoch=response.get("epoch"),
            elapsed_ms=elapsed_ms,
            status=response.get("status", "unknown"),
        )
    except Exception as exc:
        log(f"member={args.drone_id} leave_failed error={exc}")
        emit_event(
            "leave",
            role="member",
            drone_id=args.drone_id,
            group_id=args.group_id,
            epoch=None,
            elapsed_ms=None,
            status="error",
            extra=str(exc),
        )


def run_revoke(args):
    auth_server = args.auth_server or "127.0.0.1:9000"
    host, port = parse_host_port(auth_server)

    payload = {
        "event": "revoke",
        "target": args.target,
        "group_id": args.group_id,
        "timestamp": now(),
    }

    try:
        response, elapsed_ms = send_request(host, port, payload)
        log(
            f"target={args.target} revoke_response={response} "
            f"revocation_time_ms={elapsed_ms:.3f}"
        )
        emit_event(
            "revoke",
            role="auth-server",
            drone_id=args.target,
            group_id=args.group_id,
            epoch=response.get("epoch"),
            elapsed_ms=elapsed_ms,
            status=response.get("status", "unknown"),
        )
    except Exception as exc:
        log(f"target={args.target} revoke_failed error={exc}")
        emit_event(
            "revoke",
            role="auth-server",
            drone_id=args.target,
            group_id=args.group_id,
            epoch=None,
            elapsed_ms=None,
            status="error",
            extra=str(exc),
        )


# ============================================================
# Entry point
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Simulated group authentication agent")

    parser.add_argument("--role", required=True)
    parser.add_argument("--scenario", default=os.environ.get("SCENARIO", "default"))
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", default="9000")
    parser.add_argument("--drone-id")
    parser.add_argument("--group-id", default="mission-alpha")
    parser.add_argument("--auth-server", default="10.0.0.100:9000")
    parser.add_argument("--event")
    parser.add_argument("--target")
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="0 = run forever; >0 = seconds before client loops exit",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=5.0,
        help="seconds between status heartbeats (member mode)",
    )

    args = parser.parse_args()

    # Garante que SCENARIO usado nos CSVs respeite --scenario se passado.
    global SCENARIO
    SCENARIO = args.scenario or SCENARIO

    log(f"started with args={args} csv={CSV_PATH} scenario={SCENARIO}")

    if args.role == "auth-server" and args.event == "revoke":
        run_revoke(args)
    elif args.role == "auth-server":
        run_auth_server(args)
    elif args.event == "join" or args.role == "joiner":
        run_join(args)
    elif args.event == "leave":
        run_leave(args)
    elif args.role == "member":
        run_member(args)
    else:
        log(f"unsupported mode: role={args.role}, event={args.event}")


if __name__ == "__main__":
    main()