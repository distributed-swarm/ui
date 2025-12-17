#!/usr/bin/env python3
"""
Plot benchmark artifacts from stats_timeseries.jsonl.

Usage:
  python bench/plot_run.py bench/runs/<run-folder>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import matplotlib.pyplot as plt


def read_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def dig_int(d: Dict[str, Any], keys) -> Optional[int]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, int):
            return v
    return None


def dig_float(d: Dict[str, Any], keys) -> Optional[float]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="Path to a single run folder under bench/runs/")
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    stats_path = run_dir / "stats_timeseries.jsonl"
    if not stats_path.exists():
        raise SystemExit(f"Missing: {stats_path}")

    rows = read_jsonl(stats_path)

    ts = []
    completed = []
    failed = []
    queue_len = []
    latency_p95 = []
    latency_p99 = []

    for r in rows:
        t = r.get("t")
        st = r.get("stats", {})
        if not isinstance(st, dict) or not isinstance(t, (int, float)):
            continue

        ts.append(float(t))

        # Try common fields
        completed.append(dig_int(st, ["completed_total", "tasks_completed", "ctrl_tasks_completed"]) or 0)
        failed.append(dig_int(st, ["failed_total", "tasks_failed", "ctrl_tasks_failed"]) or 0)
        queue_len.append(dig_int(st, ["queue_len", "pending", "backlog"]) or 0)

        # Optional latency percentiles if present
        latency_p95.append(dig_float(st, ["latency_p95_ms", "p95_ms", "p95_latency_ms"]) or float("nan"))
        latency_p99.append(dig_float(st, ["latency_p99_ms", "p99_ms", "p99_latency_ms"]) or float("nan"))

    if not ts:
        raise SystemExit("No usable stats rows found.")

    t0 = ts[0]
    t_rel = [x - t0 for x in ts]

    # Plot completed over time
    plt.figure()
    plt.plot(t_rel, completed)
    plt.xlabel("seconds")
    plt.ylabel("completed_total (best-effort)")
    plt.title(run_dir.name)
    plt.tight_layout()
    plt.show()

    # Plot queue length over time
    plt.figure()
    plt.plot(t_rel, queue_len)
    plt.xlabel("seconds")
    plt.ylabel("queue_len (best-effort)")
    plt.title(f"{run_dir.name} — queue")
    plt.tight_layout()
    plt.show()

    # Plot p95/p99 if present
    if any(x == x for x in latency_p95) or any(x == x for x in latency_p99):
        plt.figure()
        plt.plot(t_rel, latency_p95, label="p95")
        plt.plot(t_rel, latency_p99, label="p99")
        plt.xlabel("seconds")
        plt.ylabel("latency (ms) (if exposed by /stats)")
        plt.title(f"{run_dir.name} — latency percentiles")
        plt.legend()
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
