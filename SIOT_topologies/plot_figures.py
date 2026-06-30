#!/usr/bin/env python3

"""
plot_figures.py

Gera as duas figuras do paper a partir dos CSVs agregados produzidos por
run_campaign.py:

    figure1_rekey_cost.csv
        rekey_scheme, group_size, run_id, rekey_msgs, crypto_ops, rekey_ms

    figure2_packet_loss.csv
        rekey_scheme, group_size, run_id, t_relative_s, loss_pct

Saídas (PNG + PDF):
    figure1_rekey_cost.(png|pdf)     -> custo de rekey vs. tamanho do grupo N
                                        (naive O(n) vs. lkh O(log n)),
                                        média ± desvio sobre os runs.
    figure2_packet_loss.(png|pdf)    -> perda de pacotes ao longo do tempo,
                                        com t=0 no instante do revoke, para um
                                        N representativo, naive vs. lkh.

Dependências: apenas matplotlib (pip install matplotlib). Sem pandas/numpy:
a agregação (média/desvio) é feita com a stdlib.

Uso típico:
    python3 plot_figures.py --results-dir ./campaign-results
    python3 plot_figures.py --results-dir ./campaign-results --figure2-size 32
    python3 plot_figures.py --results-dir ./campaign-results --metric rekey_msgs
"""

import argparse
import csv
import math
import os
import sys
from collections import defaultdict

import matplotlib
# Backend não-interativo: funciona em servidor/headless (sem DISPLAY).
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Estilo visual fixo por esquema, para as duas figuras ficarem coerentes.
SCHEME_STYLE = {
    "naive": {"label": "Naïve (O(n))", "marker": "o", "linestyle": "-"},
    "lkh":   {"label": "LKH (O(log n))", "marker": "s", "linestyle": "--"},
}

# Rótulos amigáveis para as métricas da Figura 1.
METRIC_LABELS = {
    "rekey_msgs": "Rekey messages per revocation",
    "crypto_ops": "AES-GCM operations per revocation",
    "rekey_ms":   "Rekey time per revocation (ms)",
}


# ============================================================
# Utilidades de leitura/estatística (sem numpy)
# ============================================================

def _to_float(value):
    """Converte para float com tolerância; retorna None se não der."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(value, default=None):
    f = _to_float(value)
    if f is None:
        return default
    return int(round(f))


def _mean_std(values):
    """
    Retorna (média, desvio_padrão_amostral) de uma lista de floats.
    Para n<=1, o desvio é 0.0. Lista vazia retorna (None, None).
    """
    vals = [v for v in values if v is not None]
    n = len(vals)
    if n == 0:
        return None, None
    mean = sum(vals) / n
    if n == 1:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)  # amostral (n-1)
    return mean, math.sqrt(var)


def _read_rows(path):
    """Lê um CSV como lista de dicts; lista vazia se o arquivo não existir."""
    if not os.path.isfile(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


# ============================================================
# Figura 1 — custo de rekey vs. N
# ============================================================

def plot_figure1(fig1_csv, out_base, metric="rekey_msgs", logx=True, logy=False):
    """
    Plota a métrica escolhida (rekey_msgs por padrão) em função de group_size,
    uma linha por esquema, com barras de erro = desvio padrão sobre os runs.

    Retorna True se gerou a figura, False se não havia dados.
    """
    rows = _read_rows(fig1_csv)
    if not rows:
        print(f"[plot] figure1: nenhum dado em {fig1_csv}", file=sys.stderr)
        return False

    if metric not in METRIC_LABELS:
        print(
            f"[plot] figure1: métrica '{metric}' inválida; "
            f"use uma de {list(METRIC_LABELS)}",
            file=sys.stderr,
        )
        return False

    # Agrega: {scheme: {group_size: [valores]}}
    data = defaultdict(lambda: defaultdict(list))
    for row in rows:
        scheme = (row.get("rekey_scheme") or "").strip().lower()
        if scheme not in SCHEME_STYLE:
            # Ignora esquemas desconhecidos, mas avisa uma vez.
            continue
        size = _to_int(row.get("group_size"))
        val = _to_float(row.get(metric))
        if size is None or val is None:
            continue
        data[scheme][size].append(val)

    if not data:
        print(
            f"[plot] figure1: dados presentes, mas sem valores válidos para "
            f"métrica '{metric}'",
            file=sys.stderr,
        )
        return False

    fig, ax = plt.subplots(figsize=(6.4, 4.2))

    # Ordena os esquemas para legenda estável (naive antes de lkh).
    for scheme in sorted(data.keys(), key=lambda s: 0 if s == "naive" else 1):
        sizes = sorted(data[scheme].keys())
        means, stds = [], []
        for size in sizes:
            m, sd = _mean_std(data[scheme][size])
            means.append(m)
            stds.append(sd if sd is not None else 0.0)

        style = SCHEME_STYLE[scheme]
        ax.errorbar(
            sizes, means, yerr=stds,
            label=style["label"],
            marker=style["marker"],
            linestyle=style["linestyle"],
            capsize=4, linewidth=1.8, markersize=6,
        )

    ax.set_xlabel("Group size N (number of drones)")
    ax.set_ylabel(METRIC_LABELS[metric])
    ax.set_title("Rekeying cost on revocation: naïve vs. LKH")

    if logx:
        ax.set_xscale("log", base=2)
        # Mostra os N reais (4, 8, 16, 32...) como ticks legíveis.
        all_sizes = sorted({s for sch in data.values() for s in sch.keys()})
        ax.set_xticks(all_sizes)
        ax.set_xticklabels([str(s) for s in all_sizes])
    if logy:
        ax.set_yscale("log")

    ax.grid(True, which="both", linestyle=":", linewidth=0.6, alpha=0.7)
    ax.legend(frameon=True)
    fig.tight_layout()

    _savefig(fig, out_base)
    plt.close(fig)
    print(f"[plot] figure1 OK -> {out_base}.png / {out_base}.pdf (metric={metric})")
    return True


# ============================================================
# Figura 2 — perda de pacotes vs. tempo (t=0 no revoke)
# ============================================================

def _bin_key(t, bin_width):
    """Bucketiza o tempo relativo em janelas de largura bin_width (segundos)."""
    if bin_width <= 0:
        return t
    # Centro do bin, para o eixo ficar simétrico em torno de 0.
    return round(t / bin_width) * bin_width


def plot_figure2(fig2_csv, out_base, target_size=None,
                 t_min=None, t_max=None, bin_width=1.0):
    """
    Plota loss_pct em função de t_relative_s (t=0 = revoke), uma linha por
    esquema, para um único group_size (target_size). Como cada run tem suas
    próprias janelas, os pontos são agregados por bin de tempo (média ± desvio).

    Se target_size for None, escolhe o MAIOR N disponível (mais ilustrativo).
    Retorna True se gerou a figura, False caso contrário.
    """
    rows = _read_rows(fig2_csv)
    if not rows:
        print(f"[plot] figure2: nenhum dado em {fig2_csv}", file=sys.stderr)
        return False

    # Descobre os N disponíveis.
    sizes_present = sorted({
        _to_int(r.get("group_size"))
        for r in rows
        if _to_int(r.get("group_size")) is not None
    })
    if not sizes_present:
        print("[plot] figure2: nenhum group_size válido", file=sys.stderr)
        return False

    if target_size is None:
        target_size = sizes_present[-1]  # maior N
    elif target_size not in sizes_present:
        print(
            f"[plot] figure2: N={target_size} não está nos dados "
            f"(disponíveis: {sizes_present}); usando N={sizes_present[-1]}",
            file=sys.stderr,
        )
        target_size = sizes_present[-1]

    # Agrega: {scheme: {bin_t: [loss_pct...]}}
    data = defaultdict(lambda: defaultdict(list))
    for row in rows:
        scheme = (row.get("rekey_scheme") or "").strip().lower()
        if scheme not in SCHEME_STYLE:
            continue
        size = _to_int(row.get("group_size"))
        if size != target_size:
            continue
        t = _to_float(row.get("t_relative_s"))
        loss = _to_float(row.get("loss_pct"))
        if t is None or loss is None:
            continue
        if t_min is not None and t < t_min:
            continue
        if t_max is not None and t > t_max:
            continue
        data[scheme][_bin_key(t, bin_width)].append(loss)

    if not data:
        print(
            f"[plot] figure2: sem pontos válidos para N={target_size} "
            f"(verifique t-min/t-max e se o revoke foi detectado)",
            file=sys.stderr,
        )
        return False

    fig, ax = plt.subplots(figsize=(7.0, 4.2))

    for scheme in sorted(data.keys(), key=lambda s: 0 if s == "naive" else 1):
        bins = sorted(data[scheme].keys())
        ts, means, stds = [], [], []
        for b in bins:
            m, sd = _mean_std(data[scheme][b])
            ts.append(b)
            means.append(m)
            stds.append(sd if sd is not None else 0.0)

        style = SCHEME_STYLE[scheme]
        ax.plot(
            ts, means,
            label=style["label"],
            marker=style["marker"],
            linestyle=style["linestyle"],
            linewidth=1.8, markersize=5,
        )
        # Banda de ± desvio padrão (sombreada).
        lower = [m - s for m, s in zip(means, stds)]
        upper = [m + s for m, s in zip(means, stds)]
        ax.fill_between(ts, lower, upper, alpha=0.15)

    # Linha vertical no instante do revoke (t=0).
    ax.axvline(0.0, color="red", linestyle="-.", linewidth=1.2, alpha=0.8)
    ax.annotate(
        "revocation (t=0)",
        xy=(0.0, ax.get_ylim()[1]),
        xytext=(4, -12), textcoords="offset points",
        color="red", fontsize=9, ha="left", va="top",
    )

    ax.set_xlabel("Time relative to revocation (s)")
    ax.set_ylabel("Packet loss (%)")
    ax.set_title(
        f"Legitimate-traffic disruption around revocation (N={target_size})"
    )
    ax.set_ylim(bottom=0)
    ax.grid(True, linestyle=":", linewidth=0.6, alpha=0.7)
    ax.legend(frameon=True)
    fig.tight_layout()

    _savefig(fig, out_base)
    plt.close(fig)
    print(f"[plot] figure2 OK -> {out_base}.png / {out_base}.pdf (N={target_size})")
    return True


# ============================================================
# Saída de arquivos
# ============================================================

def _savefig(fig, out_base):
    """Salva PNG (300 dpi) e PDF (vetorial) com o mesmo nome-base."""
    fig.savefig(out_base + ".png", dpi=300, bbox_inches="tight")
    fig.savefig(out_base + ".pdf", bbox_inches="tight")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Plot Figure 1 (rekey cost vs N) and Figure 2 (packet loss "
                    "around revocation) from run_campaign.py CSVs."
    )
    parser.add_argument(
        "--results-dir", default="./campaign-results",
        help="Directory containing figure1_rekey_cost.csv and "
             "figure2_packet_loss.csv (default: ./campaign-results)"
    )
    parser.add_argument(
        "--fig1-csv", default=None,
        help="Override path to figure1_rekey_cost.csv"
    )
    parser.add_argument(
        "--fig2-csv", default=None,
        help="Override path to figure2_packet_loss.csv"
    )
    parser.add_argument(
        "--out-dir", default=None,
        help="Where to write the figures (default: same as --results-dir)"
    )
    parser.add_argument(
        "--metric", default="rekey_msgs",
        choices=list(METRIC_LABELS.keys()),
        help="Figure 1 metric to plot (default: rekey_msgs). "
             "Also try crypto_ops or rekey_ms."
    )
    parser.add_argument(
        "--fig1-logy", action="store_true",
        help="Use a logarithmic Y axis on Figure 1 (useful for rekey_msgs, "
             "where naive O(n) dwarfs lkh O(log n))."
    )
    parser.add_argument(
        "--figure2-size", type=int, default=None,
        help="Group size N to show in Figure 2 (default: largest available)."
    )
    parser.add_argument(
        "--t-min", type=float, default=None,
        help="Lower bound (s) for Figure 2 time axis (e.g. -10)."
    )
    parser.add_argument(
        "--t-max", type=float, default=None,
        help="Upper bound (s) for Figure 2 time axis (e.g. 30)."
    )
    parser.add_argument(
        "--bin-width", type=float, default=1.0,
        help="Time bin width (s) used to average Figure 2 across runs "
             "(default: 1.0; match your --loss-window)."
    )
    parser.add_argument(
        "--only", choices=["1", "2"], default=None,
        help="Plot only Figure 1 or only Figure 2 (default: both)."
    )

    args = parser.parse_args()

    results_dir = args.results_dir
    out_dir = args.out_dir or results_dir
    os.makedirs(out_dir, exist_ok=True)

    fig1_csv = args.fig1_csv or os.path.join(results_dir, "figure1_rekey_cost.csv")
    fig2_csv = args.fig2_csv or os.path.join(results_dir, "figure2_packet_loss.csv")

    ok_any = False

    if args.only in (None, "1"):
        out1 = os.path.join(out_dir, "figure1_rekey_cost")
        ok1 = plot_figure1(
            fig1_csv, out1,
            metric=args.metric,
            logx=True,
            logy=args.fig1_logy,
        )
        ok_any = ok_any or ok1

    if args.only in (None, "2"):
        out2 = os.path.join(out_dir, "figure2_packet_loss")
        ok2 = plot_figure2(
            fig2_csv, out2,
            target_size=args.figure2_size,
            t_min=args.t_min,
            t_max=args.t_max,
            bin_width=args.bin_width,
        )
        ok_any = ok_any or ok2

    if not ok_any:
        print(
            "[plot] Nenhuma figura foi gerada. Rode a campanha primeiro "
            "(run_campaign.py) e confira se os CSVs existem em --results-dir.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
