#!/usr/bin/env python3

import argparse
import os
import time
from datetime import datetime


def now():
    return datetime.utcnow().isoformat() + "Z"


def read_first_line(path, default="0"):
    try:
        with open(path, "r") as f:
            return f.readline().strip()
    except Exception:
        return default


def read_int(path):
    try:
        return int(read_first_line(path, "0"))
    except Exception:
        return 0


def read_proc_stat():
    """
    Retorna total e idle ticks da CPU.
    """
    line = read_first_line("/proc/stat", "")

    if not line.startswith("cpu "):
        return 0, 0

    parts = line.split()
    values = [int(x) for x in parts[1:]]

    idle = values[3] + values[4]
    total = sum(values)

    return total, idle


def cpu_usage_percent(prev_total, prev_idle, curr_total, curr_idle):
    total_delta = curr_total - prev_total
    idle_delta = curr_idle - prev_idle

    if total_delta <= 0:
        return 0.0

    usage = 100.0 * (1.0 - (idle_delta / total_delta))
    return max(0.0, min(100.0, usage))


def read_memory_info():
    """
    Lê /proc/meminfo.
    Retorna MemTotal, MemAvailable e uso aproximado.
    """
    data = {}

    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                key, value = line.split(":", 1)
                value_kb = int(value.strip().split()[0])
                data[key] = value_kb
    except Exception:
        pass

    total = data.get("MemTotal", 0)
    available = data.get("MemAvailable", 0)
    used = total - available if total >= available else 0

    return total, available, used


def read_network_stats():
    """
    Lê estatísticas em /sys/class/net.
    Retorna uma lista com métricas por interface.
    """
    results = []

    base = "/sys/class/net"

    if not os.path.isdir(base):
        return results

    for iface in sorted(os.listdir(base)):
        if iface == "lo":
            continue

        stats_dir = os.path.join(base, iface, "statistics")

        rx_bytes = read_int(os.path.join(stats_dir, "rx_bytes"))
        tx_bytes = read_int(os.path.join(stats_dir, "tx_bytes"))
        rx_packets = read_int(os.path.join(stats_dir, "rx_packets"))
        tx_packets = read_int(os.path.join(stats_dir, "tx_packets"))
        rx_errors = read_int(os.path.join(stats_dir, "rx_errors"))
        tx_errors = read_int(os.path.join(stats_dir, "tx_errors"))

        results.append({
            "iface": iface,
            "rx_bytes": rx_bytes,
            "tx_bytes": tx_bytes,
            "rx_packets": rx_packets,
            "tx_packets": tx_packets,
            "rx_errors": rx_errors,
            "tx_errors": tx_errors,
        })

    return results


def print_header():
    print(
        "timestamp,"
        "scenario,"
        "node,"
        "cpu_percent,"
        "mem_total_kb,"
        "mem_available_kb,"
        "mem_used_kb,"
        "iface,"
        "rx_bytes,"
        "tx_bytes,"
        "rx_packets,"
        "tx_packets,"
        "rx_errors,"
        "tx_errors",
        flush=True
    )


def main():
    parser = argparse.ArgumentParser(description="Simple metrics collector")

    parser.add_argument("--scenario", default="default")
    parser.add_argument("--node", default="unknown")
    parser.add_argument("--interval", type=float, default=1.0)

    args = parser.parse_args()

    print_header()

    prev_total, prev_idle = read_proc_stat()
    time.sleep(args.interval)

    while True:
        curr_total, curr_idle = read_proc_stat()
        cpu = cpu_usage_percent(prev_total, prev_idle, curr_total, curr_idle)

        prev_total, prev_idle = curr_total, curr_idle

        mem_total, mem_available, mem_used = read_memory_info()
        net_stats = read_network_stats()

        if not net_stats:
            print(
                f"{now()},"
                f"{args.scenario},"
                f"{args.node},"
                f"{cpu:.3f},"
                f"{mem_total},"
                f"{mem_available},"
                f"{mem_used},"
                f"NA,0,0,0,0,0,0",
                flush=True
            )
        else:
            for stat in net_stats:
                print(
                    f"{now()},"
                    f"{args.scenario},"
                    f"{args.node},"
                    f"{cpu:.3f},"
                    f"{mem_total},"
                    f"{mem_available},"
                    f"{mem_used},"
                    f"{stat['iface']},"
                    f"{stat['rx_bytes']},"
                    f"{stat['tx_bytes']},"
                    f"{stat['rx_packets']},"
                    f"{stat['tx_packets']},"
                    f"{stat['rx_errors']},"
                    f"{stat['tx_errors']}",
                    flush=True
                )

        time.sleep(args.interval)


if __name__ == "__main__":
    main()