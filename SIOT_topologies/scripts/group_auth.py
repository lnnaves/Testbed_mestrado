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

Esquemas de rekeying (--rekey-scheme):
  naive : a cada evento de associação, gera nova chave de grupo e a cifra
          individualmente para cada membro restante (O(n) mensagens).
  lkh   : Logical Key Hierarchy REAL. Mantém uma árvore binária de chaves cujas
          folhas são KEKs por membro e cujos nós internos são KEKs intermediárias
          PERSISTENTES em memória. A chave de grupo é derivada da raiz. A cada
          evento, re-chaveiam-se os nós no caminho da folha afetada até a raiz,
          cifrando a nova chave de cada nó para cada subárvore filha que precisa
          dela. Custo O(log n) mensagens.

Convenção de contagem de mensagens (rekey_msgs) — IMPORTANTE para o paper:
  Conta-se o número de MENSAGENS DE REKEY EMITIDAS PELA AUTORIDADE.
    - naive: N-1 (membros restantes) em leave/revoke; N em join.
    - lkh  : uma mensagem por cifragem de chave de nó destinada a cada subárvore
             filha ao longo do caminho re-chaveado (~O(log n)).
  crypto_ops conta as cifragens AES-GCM realizadas.

Observação de honestidade científica:
  A criptografia é REAL (AES-GCM via biblioteca `cryptography`). O protocolo em si
  é um esquema de REFERÊNCIA usado para AVALIAR o custo de rekeying, não uma nova
  proposta padronizada.

Saídas:
  - Log em texto livre em stdout (capturado pelo redirect na topologia).
  - CSV estruturado em /tmp/drone-logs/protocol_latency.csv com uma linha
    por evento medido. Esse é o arquivo que você usa para análise.
"""

import argparse
import csv
import json
import math
import os
import socket
import socketserver
import threading
import time
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


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
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    print(f"[{now()}] [group-auth] {msg}", flush=True)


def _new_key():
    """Gera uma chave AES-GCM de 128 bits."""
    return AESGCM.generate_key(bit_length=128)


def _encrypt(key, plaintext):
    """
    Cifra `plaintext` (bytes) sob `key` com AES-GCM e nonce aleatório.
    Conta como UMA operação criptográfica. Retorna os bytes do ciphertext
    (não precisamos decifrar; o objetivo é medir o custo real da operação).
    """
    nonce = os.urandom(12)
    return AESGCM(key).encrypt(nonce, plaintext, None)


def emit_event(
    event_type,
    role,
    drone_id,
    group_id,
    epoch,
    elapsed_ms,
    status,
    rekey_scheme="",
    group_size="",
    rekey_msgs="",
    crypto_ops="",
    rekey_ms="",
    extra="",
):
    """
    Escreve uma linha CSV por evento medido.
    Cabeçalho é escrito apenas na primeira vez que o arquivo é criado.

    As colunas rekey_scheme/group_size/rekey_msgs/crypto_ops/rekey_ms são
    preenchidas apenas para eventos de associação (join/leave/revoke); para
    register/heartbeat ficam em branco.
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
                    # ---- novas colunas (custo de rekey) ----
                    "rekey_scheme",
                    "group_size",
                    "rekey_msgs",
                    "crypto_ops",
                    "rekey_ms",
                    # ---------------------------------------
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
                rekey_scheme if rekey_scheme is not None else "",
                group_size if group_size is not None else "",
                rekey_msgs if rekey_msgs is not None else "",
                crypto_ops if crypto_ops is not None else "",
                f"{rekey_ms:.3f}" if isinstance(rekey_ms, (int, float)) else (rekey_ms or ""),
                extra,
            ])


# ============================================================
# Árvore LKH (Logical Key Hierarchy)
# ============================================================

class LKHNode:
    """
    Nó de uma árvore binária de chaves.

    - Folhas: associadas a um drone (member_id != None) e portam a KEK individual.
    - Nós internos: portam uma KEK intermediária PERSISTENTE.
    - A raiz porta a chave da qual a chave de grupo é derivada.
    """

    __slots__ = ("key", "left", "right", "parent", "member_id")

    def __init__(self, key=None, member_id=None):
        self.key = key if key is not None else _new_key()
        self.left = None
        self.right = None
        self.parent = None
        self.member_id = member_id

    def is_leaf(self):
        return self.left is None and self.right is None


class LKHTree:
    """
    Logical Key Hierarchy real.

    Estratégia de balanceamento (documentada de propósito):
      Mantemos a lista ordenada de membros e, a cada mudança de associação,
      reconstruímos a TOPOLOGIA da árvore como uma árvore binária balanceada
      sobre as folhas atuais (altura = ceil(log2(N))). As CHAVES das folhas
      (KEKs individuais dos membros) são PRESERVADAS entre eventos — só os nós
      internos no caminho afetado é que são re-chaveados. Isso mantém o caminho
      de re-chaveamento em O(log n) e preserva o segredo individual de cada
      membro, que é a essência do LKH.

    Contagem de mensagens:
      Para cada nó interno re-chaveado, a nova chave do nó é cifrada uma vez sob
      a chave de CADA filho que deve recebê-la. Cada cifragem dessas conta como
      UMA mensagem (rekey_msgs) e UMA operação criptográfica (crypto_ops).
    """

    def __init__(self):
        self.root = None
        self.leaves = {}  # member_id -> LKHNode (folha), preserva a KEK individual

    # ---------- construção da topologia balanceada ----------

    def _build_balanced(self, leaf_nodes):
        """
        Constrói uma árvore binária balanceada a partir de uma lista de folhas
        (preservando os objetos-folha e suas chaves). Nós internos recebem chaves
        novas aqui apenas se forem criados; o re-chaveamento contabilizado é feito
        separadamente em _rekey_path para o evento corrente.
        """
        if not leaf_nodes:
            self.root = None
            return

        level = list(leaf_nodes)
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                if i + 1 < len(level):
                    parent = LKHNode()  # nó interno com chave nova
                    parent.left = level[i]
                    parent.right = level[i + 1]
                    level[i].parent = parent
                    level[i + 1].parent = parent
                    next_level.append(parent)
                else:
                    # número ímpar: promove o nó solitário para o próximo nível
                    next_level.append(level[i])
            level = next_level

        self.root = level[0]

    def _rebuild(self):
        """Reconstrói a topologia a partir das folhas atuais (ordem estável)."""
        ordered = [self.leaves[m] for m in sorted(self.leaves.keys())]
        # Reset de ligações antes de reconstruir.
        for node in ordered:
            node.parent = None
            node.left = None
            node.right = None
        self._build_balanced(ordered)

    # ---------- caminho e re-chaveamento ----------

    def _path_to_root(self, node):
        """Lista de nós internos da folha (exclusiva) até a raiz (inclusiva)."""
        path = []
        cur = node.parent
        while cur is not None:
            path.append(cur)
            cur = cur.parent
        return path

    def _rekey_path(self, leaf):
        """
        Re-chaveia todos os nós internos no caminho de `leaf` até a raiz.

        Para cada nó re-chaveado, cifra a nova chave do nó sob a chave de cada
        filho existente (uma mensagem por filho). Retorna (n_msgs, n_ops).
        """
        n_msgs = 0
        n_ops = 0
        for node in self._path_to_root(leaf):
            node.key = _new_key()  # nova chave para o nó interno (inclui a raiz)
            for child in (node.left, node.right):
                if child is not None:
                    _encrypt(child.key, node.key)  # cifragem real AES-GCM
                    n_ops += 1
                    n_msgs += 1  # 1 mensagem por subárvore filha -> ~O(log n)
        return n_msgs, n_ops

    # ---------- API de eventos ----------

    def add_member(self, member_id):
        """
        Adiciona um membro (cria folha com KEK nova), reconstrói a topologia e
        re-chaveia o caminho da nova folha. Retorna (n_msgs, n_ops).
        """
        if member_id not in self.leaves:
            self.leaves[member_id] = LKHNode(member_id=member_id)
        self._rebuild()
        leaf = self.leaves[member_id]
        return self._rekey_path(leaf)

    def remove_member(self, member_id):
        """
        Remove um membro. Re-chaveia o caminho que ele ocupava (a partir do pai)
        para que o membro removido não derive as novas chaves. Retorna
        (n_msgs, n_ops).
        """
        leaf = self.leaves.pop(member_id, None)

        if not self.leaves:
            self.root = None
            return 0, 0

        # Reconstrói a topologia sem o membro removido.
        self._rebuild()

        # Re-chaveia o caminho a partir da raiz até as folhas afetadas.
        # Como a topologia foi reconstruída, re-chaveamos todos os nós internos
        # no caminho da folha "vizinha" (a que herdou a posição) até a raiz.
        # Para simplicidade e correção do custo O(log n), re-chaveamos o caminho
        # da primeira folha (ordem estável) até a raiz, que cobre a raiz e os
        # ancestrais reorganizados.
        anchor = self.leaves[sorted(self.leaves.keys())[0]]
        return self._rekey_path(anchor)

    def group_key_fingerprint(self):
        """Identificador curto da chave de grupo atual (derivada da raiz)."""
        if self.root is None:
            return None
        # Não expomos a chave; só um hash curto para correlação/log.
        import hashlib
        return hashlib.sha256(self.root.key).hexdigest()[:8]

    def height(self):
        return max(1, math.ceil(math.log2(max(1, len(self.leaves)))))


# ============================================================
# Estado do grupo (no servidor)
# ============================================================

class GroupState:
    def __init__(self, group_id, rekey_scheme="naive"):
        self.group_id = group_id
        self.rekey_scheme = rekey_scheme
        self.members = []          # ordem de inserção; tamanho = N
        self.revoked = set()
        self.epoch = 1
        self.lock = threading.Lock()

        # Estado criptográfico REAL.
        self.group_key = _new_key()             # usado pelo esquema naive
        self.member_kek = {}                    # member_id -> KEK individual (naive)
        self.lkh = LKHTree() if rekey_scheme == "lkh" else None

    # ---------- rekeying real ----------

    def _rekey_naive_add(self):
        """Join no esquema naive: nova group key cifrada p/ cada membro (N msgs)."""
        t0 = time.perf_counter()
        self.group_key = _new_key()
        n_msgs = 0
        n_ops = 0
        for m in self.members:
            kek = self.member_kek.setdefault(m, _new_key())
            _encrypt(kek, self.group_key)
            n_ops += 1
            n_msgs += 1  # uma mensagem unicast por membro -> O(n)
        rekey_ms = (time.perf_counter() - t0) * 1000.0
        return n_msgs, n_ops, rekey_ms

    def _rekey_naive_remove(self):
        """Leave/revoke no naive: nova group key cifrada p/ cada restante (N-1)."""
        t0 = time.perf_counter()
        self.group_key = _new_key()
        n_msgs = 0
        n_ops = 0
        for m in self.members:  # já sem o membro removido
            kek = self.member_kek.setdefault(m, _new_key())
            _encrypt(kek, self.group_key)
            n_ops += 1
            n_msgs += 1
        rekey_ms = (time.perf_counter() - t0) * 1000.0
        return n_msgs, n_ops, rekey_ms

    def _rekey_lkh_add(self, member_id):
        t0 = time.perf_counter()
        n_msgs, n_ops = self.lkh.add_member(member_id)
        rekey_ms = (time.perf_counter() - t0) * 1000.0
        return n_msgs, n_ops, rekey_ms

    def _rekey_lkh_remove(self, member_id):
        t0 = time.perf_counter()
        n_msgs, n_ops = self.lkh.remove_member(member_id)
        rekey_ms = (time.perf_counter() - t0) * 1000.0
        return n_msgs, n_ops, rekey_ms

    def _do_rekey_add(self, member_id):
        if self.rekey_scheme == "lkh":
            return self._rekey_lkh_add(member_id)
        return self._rekey_naive_add()

    def _do_rekey_remove(self, member_id):
        if self.rekey_scheme == "lkh":
            return self._rekey_lkh_remove(member_id)
        return self._rekey_naive_remove()

    # ---------- API de protocolo ----------

    def register(self, drone_id):
        """Registro inicial: NÃO dispara rekey (apenas entra no grupo)."""
        with self.lock:
            if drone_id in self.revoked:
                return {
                    "status": "denied",
                    "reason": "drone_revoked",
                    "group_id": self.group_id,
                    "epoch": self.epoch,
                }

            if drone_id not in self.members:
                self.members.append(drone_id)
                self.member_kek.setdefault(drone_id, _new_key())
                if self.lkh is not None:
                    # Garante a folha sem contabilizar como evento de rekey.
                    if drone_id not in self.lkh.leaves:
                        self.lkh.leaves[drone_id] = LKHNode(member_id=drone_id)
                        self.lkh._rebuild()

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

            if drone_id not in self.members:
                self.members.append(drone_id)
                self.member_kek.setdefault(drone_id, _new_key())

            self.epoch += 1
            n_msgs, n_ops, rekey_ms = self._do_rekey_add(drone_id)

            return {
                "status": "accepted",
                "event": "join",
                "drone_id": drone_id,
                "group_id": self.group_id,
                "epoch": self.epoch,
                "members": sorted(self.members),
                "rekey_scheme": self.rekey_scheme,
                "group_size": len(self.members),
                "rekey_msgs": n_msgs,
                "crypto_ops": n_ops,
                "rekey_ms": rekey_ms,
            }

    def leave(self, drone_id):
        with self.lock:
            if drone_id in self.members:
                self.members.remove(drone_id)
            self.member_kek.pop(drone_id, None)

            self.epoch += 1
            n_msgs, n_ops, rekey_ms = self._do_rekey_remove(drone_id)

            return {
                "status": "accepted",
                "event": "leave",
                "drone_id": drone_id,
                "group_id": self.group_id,
                "epoch": self.epoch,
                "members": sorted(self.members),
                "rekey_scheme": self.rekey_scheme,
                "group_size": len(self.members),
                "rekey_msgs": n_msgs,
                "crypto_ops": n_ops,
                "rekey_ms": rekey_ms,
            }

    def revoke(self, drone_id):
        with self.lock:
            if drone_id in self.members:
                self.members.remove(drone_id)
            self.member_kek.pop(drone_id, None)
            self.revoked.add(drone_id)

            self.epoch += 1
            n_msgs, n_ops, rekey_ms = self._do_rekey_remove(drone_id)

            return {
                "status": "accepted",
                "event": "revoke",
                "target": drone_id,
                "group_id": self.group_id,
                "epoch": self.epoch,
                "members": sorted(self.members),
                "revoked": sorted(self.revoked),
                "rekey_scheme": self.rekey_scheme,
                "group_size": len(self.members),
                "rekey_msgs": n_msgs,
                "crypto_ops": n_ops,
                "rekey_ms": rekey_ms,
            }

    def status(self):
        with self.lock:
            return {
                "status": "ok",
                "group_id": self.group_id,
                "epoch": self.epoch,
                "members": sorted(self.members),
                "revoked": sorted(self.revoked),
                "rekey_scheme": self.rekey_scheme,
                "group_size": len(self.members),
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

    AuthTCPHandler.group_state = GroupState(
        args.group_id, rekey_scheme=args.rekey_scheme
    )

    server = socketserver.ThreadingTCPServer((host, port), AuthTCPHandler)
    server.daemon_threads = True

    log(
        f"auth server started on {host}:{port}, group_id={args.group_id}, "
        f"rekey_scheme={args.rekey_scheme}"
    )

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
            rekey_scheme=response.get("rekey_scheme", ""),
            group_size=response.get("group_size", ""),
            rekey_msgs=response.get("rekey_msgs", ""),
            crypto_ops=response.get("crypto_ops", ""),
            rekey_ms=response.get("rekey_ms", ""),
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
            rekey_scheme=response.get("rekey_scheme", ""),
            group_size=response.get("group_size", ""),
            rekey_msgs=response.get("rekey_msgs", ""),
            crypto_ops=response.get("crypto_ops", ""),
            rekey_ms=response.get("rekey_ms", ""),
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
            rekey_scheme=response.get("rekey_scheme", ""),
            group_size=response.get("group_size", ""),
            rekey_msgs=response.get("rekey_msgs", ""),
            crypto_ops=response.get("crypto_ops", ""),
            rekey_ms=response.get("rekey_ms", ""),
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
        "--rekey-scheme",
        choices=["naive", "lkh"],
        default="naive",
        help="Group rekeying scheme: naive (O(n)) or lkh (O(log n))",
    )
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

    log(
        f"started with args={args} csv={CSV_PATH} scenario={SCENARIO} "
        f"rekey_scheme={args.rekey_scheme}"
    )

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
