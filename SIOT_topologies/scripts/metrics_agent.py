#!/usr/bin/env python3

import argparse
import os
import time
from datetime import datetime


def now():
    return datetime.utcnow().isoformat() + "Z"


def read_proc_stat():
    """
    Retorna total e idle ticks da CPU.
    """
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline().strip()
        
        if not line.startswith("cpu "):
            return 0, 0

        parts = line.split()
        values = [int(x) for x in parts[1:]]

        idle = values[3] + values[4]
        total = sum(values)

        return total, idle
    except Exception:
        return 0, 0


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


def read_network_stats_from_proc():
    """
    Lê estatísticas de rede de /proc/net/dev.
    Funciona melhor dentro de containers.
    
    Formato de /proc/net/dev:
    Inter-|   Receive                                                |  Transmit
     face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
        lo: 1234     5678    0    0    0     0          0         0     1234     5678    0    0    0     0       0          0
      eth0: 9876     1234    0    0    0     0          0         0     5432      432    0    0    0     0       0          0
    """
    results = []

    try:
        with open("/proc/net/dev", "r") as f:
            lines = f.readlines()
        
        # Skip first 2 header lines
        for line in lines[2:]:
            if ":" not in line:
                continue
            
            iface, data = line.split(":", 1)
            iface = iface.strip()
            
            if iface == "lo":
                continue
            
            parts = data.split()
            
            if len(parts) < 16:
                continue
            
            try:
                rx_bytes = int(parts[0])
                rx_packets = int(parts[1])
                rx_errors = int(parts[2])
                rx_dropped = int(parts[3])
                
                # Transmit starts at index 8
                tx_bytes = int(parts[8])
                tx_packets = int(parts[9])
                tx_errors = int(parts[10])
                tx_dropped = int(parts[11])
                
                results.append({
                    "iface": iface,
                    "rx_bytes": rx_bytes,
                    "tx_bytes": tx_bytes,
                    "rx_packets": rx_packets,
                    "tx_packets": tx_packets,
                    "rx_errors": rx_errors,
                    "tx_errors": tx_errors,
                    "rx_dropped": rx_dropped,
                    "tx_dropped": tx_dropped,
                })
            except (ValueError, IndexError):
                continue
    
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error reading /proc/net/dev: {e}", flush=True)
    
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
        "tx_errors,"
        "rx_dropped,"
        "tx_dropped",
        flush=True
    )


def main():
    parser = argparse.ArgumentParser(description="Metrics collector for Containernet containers")

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
        net_stats = read_network_stats_from_proc()

        if not net_stats:
            # Se nenhuma interface foi encontrada, imprime uma linha genérica
            print(
                f"{now()},"
                f"{args.scenario},"
                f"{args.node},"
                f"{cpu:.3f},"
                f"{mem_total},"
                f"{mem_available},"
                f"{mem_used},"
                f"NA,0,0,0,0,0,0,0,0",
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
                    f"{stat['tx_errors']},"
                    f"{stat['rx_dropped']},"
                    f"{stat['tx_dropped']}",
                    flush=True
                )

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
