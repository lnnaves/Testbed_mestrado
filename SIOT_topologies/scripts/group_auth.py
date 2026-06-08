#!/usr/bin/env python3

import argparse
import json
import socket
import socketserver
import threading
import time
from datetime import datetime


def now():
    return datetime.utcnow().isoformat() + "Z"


def log(msg):
    print(f"[{now()}] [group-auth] {msg}", flush=True)


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

    response, elapsed_ms = send_request(host, port, payload)

    log(
        f"member={args.drone_id} register_response={response} "
        f"auth_time_ms={elapsed_ms:.3f}"
    )

    while True:
        time.sleep(5)
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
        except Exception as exc:
            log(f"member={args.drone_id} heartbeat_failed error={exc}")


def run_join(args):
    host, port = parse_host_port(args.auth_server)

    payload = {
        "event": "join",
        "drone_id": args.drone_id,
        "group_id": args.group_id,
        "timestamp": now(),
    }

    response, elapsed_ms = send_request(host, port, payload)

    log(
        f"joiner={args.drone_id} join_response={response} "
        f"join_time_ms={elapsed_ms:.3f}"
    )

    while True:
        time.sleep(5)


def run_leave(args):
    host, port = parse_host_port(args.auth_server)

    payload = {
        "event": "leave",
        "drone_id": args.drone_id,
        "group_id": args.group_id,
        "timestamp": now(),
    }

    response, elapsed_ms = send_request(host, port, payload)

    log(
        f"member={args.drone_id} leave_response={response} "
        f"leave_time_ms={elapsed_ms:.3f}"
    )


def run_revoke(args):
    # Esse modo é executado normalmente dentro do container da autoridade.
    # Ele conecta no auth-server local já em execução.
    auth_server = args.auth_server or "127.0.0.1:9000"
    host, port = parse_host_port(auth_server)

    payload = {
        "event": "revoke",
        "target": args.target,
        "group_id": args.group_id,
        "timestamp": now(),
    }

    response, elapsed_ms = send_request(host, port, payload)

    log(
        f"target={args.target} revoke_response={response} "
        f"revocation_time_ms={elapsed_ms:.3f}"
    )


def main():
    parser = argparse.ArgumentParser(description="Simulated group authentication agent")

    parser.add_argument("--role", required=True)
    parser.add_argument("--scenario", default="default")
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", default="9000")
    parser.add_argument("--drone-id")
    parser.add_argument("--group-id", default="mission-alpha")
    parser.add_argument("--auth-server", default="10.0.0.100:9000")
    parser.add_argument("--event")
    parser.add_argument("--target")

    args = parser.parse_args()

    log(f"started with args={args}")

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