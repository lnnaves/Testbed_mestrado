#!/usr/bin/env python3

"""
run_campaign.py

Orquestrador da campanha experimental para o paper.

Varre a matriz:
    rekey_scheme in {naive, lkh} x N in {4, 8, 16, 32} x R repetições

Para cada célula, executa o cenário de REVOGAÇÃO (topology_group_revocation.py),
passando o esquema de rekey e o tamanho de grupo N, e consolida os resultados em
dois CSVs prontos para plotar:

    figure1_rekey_cost.csv
        rekey_scheme, group_size, run_id, rekey_msgs, crypto_ops, rekey_ms
        (uma linha por evento de revoke por run)

    figure2_packet_loss.csv
        rekey_scheme, group_size, run_id, t_relative_s, loss_pct
        (janelas de perda alinhadas no tempo em torno do revoke)

IMPORTANTE — de onde vêm os dados:
  - O custo de rekey (rekey_msgs/crypto_ops/rekey_ms) é produzido pelo
    auth-server DENTRO do container, no CSV protocol_latency.csv
    (/tmp/drone-logs/protocol_latency.csv). A perda por janela vem de
    traffic_loss.csv, também dentro do container.
  - Estes arquivos in-container NÃO são automaticamente visíveis para o
    orquestrador. Este script assume que, ao final de cada run, esses CSVs
    foram COPIADOS para o diretório de métricas do run no host, com o padrão:
        <metrics-dir>/<scenario>-run-<N>/protocol_latency.csv
        <metrics-dir>/<scenario>-run-<N>/traffic_loss.csv
    (Veja a função collect_run_artifacts e o bloco de notas no final.)
    Caso esses arquivos não existam, o script ainda consolida o que houver e
    avisa, sem abortar a campanha.

Uso típico (encurtando os waits com --fast para a campanha não levar horas):

    sudo python3 run_campaign.py \
        --schemes naive lkh \
        --sizes 4 8 16 32 \
        --runs 10 \
        --results-dir ./campaign-results \
        --fast
"""

import argparse
import csv
import glob
import os
import subprocess
import sys

# Cenário usado na campanha (o que tem adversário/revogação).
REVOCATION_TOPOLOGY = "topology_group_revocation.py"
# Nome de cenário que o próprio topology_group_revocation.py usa nos CSVs.
REVOCATION_SCENARIO = "group_revocation_adhoc"


def info(msg):
    print(f"[run_campaign] {msg}", flush=True)


# ============================================================
# Execução de uma célula (esquema x N x run)
# ============================================================

def run_cell(scheme, size, runs, args):
    """
    Executa o cenário de revogação para um dado (scheme, N), com `runs`
    repetições, gravando os CSVs por run em um metrics-dir específico da célula.

    Retorna o caminho do metrics-dir da célula.
    """
    cell_dir = os.path.join(
        args.results_dir, "raw", f"{scheme}-N{size}"
    )
    os.makedirs(cell_dir, exist_ok=True)

    cmd = [
        "python3",
        REVOCATION_TOPOLOGY,
        "--no-cli",
        "--runs", str(runs),
        "--rekey-scheme", scheme,
        "--num-drones", str(size),
        "--metrics-dir", cell_dir,
        "--traffic-rate", args.traffic_rate,
        "--ping-count", str(args.ping_count),
        "--ping-timeout", str(args.ping_timeout),
    ]
    if args.fast:
        cmd.append("--fast")

    info(f"running cell scheme={scheme} N={size} runs={runs}")
    info(f"  cmd: {' '.join(cmd)}")

    if args.dry_run:
        info("  [dry-run] skipping execution")
        return cell_dir

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        info(f"  WARNING: cell scheme={scheme} N={size} failed: {exc}")
    except FileNotFoundError:
        info(
            f"  ERROR: could not find {REVOCATION_TOPOLOGY}. "
            f"Run this script from the SIOT_topologies directory."
        )
        sys.exit(1)

    return cell_dir


# ============================================================
# Coleta/consolidação de artefatos
# ============================================================

def _find_protocol_csvs(cell_dir):
    """
    Procura protocol_latency.csv produzidos pelos runs dentro de cell_dir.

    Aceita tanto subpastas por run (<scenario>-run-<N>/protocol_latency.csv)
    quanto um protocol_latency.csv direto na pasta, e arquivos copiados com
    sufixo de run.
    """
    patterns = [
        os.path.join(cell_dir, "**", "protocol_latency.csv"),
        os.path.join(cell_dir, "**", "protocol_latency-run-*.csv"),
        os.path.join(cell_dir, "protocol_latency*.csv"),
    ]
    found = []
    for p in patterns:
        found.extend(glob.glob(p, recursive=True))
    return sorted(set(found))


def _find_loss_csvs(cell_dir):
    patterns = [
        os.path.join(cell_dir, "**", "traffic_loss.csv"),
        os.path.join(cell_dir, "**", "traffic_loss-run-*.csv"),
        os.path.join(cell_dir, "traffic_loss*.csv"),
    ]
    found = []
    for p in patterns:
        found.extend(glob.glob(p, recursive=True))
    return sorted(set(found))


def _run_id_from_path(path, fallback):
    """Tenta inferir um run_id do caminho (ex.: ...-run-2/...)."""
    base = path.replace("\\", "/")
    marker = "-run-"
    if marker in base:
        try:
            after = base.split(marker, 1)[1]
            digits = ""
            for ch in after:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            if digits:
                return int(digits)
        except Exception:
            pass
    return fallback


def consolidate_figure1(scheme, size, cell_dir, writer):
    """
    Lê os protocol_latency.csv da célula, filtra eventos de revoke e escreve
    uma linha por evento em figure1_rekey_cost.csv.
    """
    csvs = _find_protocol_csvs(cell_dir)
    if not csvs:
        info(
            f"  [figure1] no protocol_latency.csv found for "
            f"scheme={scheme} N={size} (in {cell_dir})"
        )
        return 0

    n_rows = 0
    for idx, path in enumerate(csvs):
        run_id = _run_id_from_path(path, idx)
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("event") != "revoke":
                        continue
                    rekey_msgs = row.get("rekey_msgs", "")
                    crypto_ops = row.get("crypto_ops", "")
                    rekey_ms = row.get("rekey_ms", "")
                    # group_size do CSV tem prioridade; senão usa o N da célula.
                    group_size = row.get("group_size") or size
                    writer.writerow({
                        "rekey_scheme": row.get("rekey_scheme") or scheme,
                        "group_size": group_size,
                        "run_id": run_id,
                        "rekey_msgs": rekey_msgs,
                        "crypto_ops": crypto_ops,
                        "rekey_ms": rekey_ms,
                    })
                    n_rows += 1
        except Exception as exc:
            info(f"  [figure1] could not read {path}: {exc}")
    return n_rows


def consolidate_figure2(scheme, size, cell_dir, writer):
    """
    Lê os traffic_loss.csv da célula e escreve janelas de perda alinhadas no
    tempo (t_relative_s relativo ao início da série de janelas do run) em
    figure2_packet_loss.csv.
    """
    csvs = _find_loss_csvs(cell_dir)
    if not csvs:
        info(
            f"  [figure2] no traffic_loss.csv found for "
            f"scheme={scheme} N={size} (in {cell_dir})"
        )
        return 0

    n_rows = 0
    for idx, path in enumerate(csvs):
        run_id = _run_id_from_path(path, idx)
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            # Usa window_start para criar um tempo relativo ao primeiro janela.
            starts = []
            for row in rows:
                try:
                    starts.append(float(row.get("window_start")))
                except Exception:
                    starts.append(None)
            base = None
            for s in starts:
                if s is not None:
                    base = s
                    break
            for row, s in zip(rows, starts):
                if s is not None and base is not None:
                    t_rel = s - base
                else:
                    t_rel = ""
                writer.writerow({
                    "rekey_scheme": scheme,
                    "group_size": size,
                    "run_id": run_id,
                    "t_relative_s": f"{t_rel:.3f}" if t_rel != "" else "",
                    "loss_pct": row.get("loss_pct", ""),
                })
                n_rows += 1
        except Exception as exc:
            info(f"  [figure2] could not read {path}: {exc}")
    return n_rows


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run the naive-vs-LKH x N x R rekeying campaign over the "
                    "revocation scenario and consolidate ready-to-plot CSVs."
    )
    parser.add_argument(
        "--schemes", nargs="+", default=["naive", "lkh"],
        choices=["naive", "lkh"],
        help="Rekey schemes to sweep (default: naive lkh)"
    )
    parser.add_argument(
        "--sizes", nargs="+", type=int, default=[4, 8, 16, 32],
        help="Group sizes N to sweep (default: 4 8 16 32)"
    )
    parser.add_argument(
        "--runs", type=int, default=10,
        help="Repetitions per cell (default: 10)"
    )
    parser.add_argument(
        "--results-dir", default="./campaign-results",
        help="Directory for raw per-cell outputs and aggregated CSVs"
    )
    parser.add_argument(
        "--traffic-rate", default="10pps",
        help="Traffic generation rate passed to the scenario (default: 10pps)"
    )
    parser.add_argument(
        "--ping-count", type=int, default=5,
        help="Ping packets per RTT measurement (default: 5)"
    )
    parser.add_argument(
        "--ping-timeout", type=int, default=1,
        help="Ping timeout per packet in seconds (default: 1)"
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Shorten the long wait() durations in the scenario to speed up "
             "large campaigns (passes --fast through to the topology)."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the commands and consolidation plan without running the "
             "scenarios (useful to validate the matrix)."
    )

    args = parser.parse_args()

    os.makedirs(args.results_dir, exist_ok=True)

    fig1_path = os.path.join(args.results_dir, "figure1_rekey_cost.csv")
    fig2_path = os.path.join(args.results_dir, "figure2_packet_loss.csv")

    info(
        f"campaign: schemes={args.schemes} sizes={args.sizes} "
        f"runs={args.runs} fast={args.fast} dry_run={args.dry_run}"
    )

    # Abre os dois CSVs agregados e escreve cabeçalhos uma vez.
    with open(fig1_path, "w", newline="") as f1, \
         open(fig2_path, "w", newline="") as f2:

        w1 = csv.DictWriter(f1, fieldnames=[
            "rekey_scheme", "group_size", "run_id",
            "rekey_msgs", "crypto_ops", "rekey_ms",
        ])
        w1.writeheader()

        w2 = csv.DictWriter(f2, fieldnames=[
            "rekey_scheme", "group_size", "run_id",
            "t_relative_s", "loss_pct",
        ])
        w2.writeheader()

        total_fig1 = 0
        total_fig2 = 0

        for scheme in args.schemes:
            for size in args.sizes:
                cell_dir = run_cell(scheme, size, args.runs, args)
                if args.dry_run:
                    continue
                total_fig1 += consolidate_figure1(scheme, size, cell_dir, w1)
                total_fig2 += consolidate_figure2(scheme, size, cell_dir, w2)

    info(f"wrote {fig1_path} ({total_fig1} rows)")
    info(f"wrote {fig2_path} ({total_fig2} rows)")

    if total_fig1 == 0 and not args.dry_run:
        info(
            "NOTE: figure1 has 0 rows. Make sure the in-container "
            "protocol_latency.csv is copied into each run's metrics dir "
            "(see the docstring at the top of this file)."
        )
    info("campaign done.")


if __name__ == "__main__":
    main()
