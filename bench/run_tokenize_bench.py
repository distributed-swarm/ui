#!/usr/bin/env python3
"""
Run a repeatable tokenize benchmark against the Neuro-Fabric controller and save artifacts.

Artifacts per run:
  runs/<timestamp>-tokenize-<mode>-<rate>/config.json
  runs/<...>/agents_start.json
  runs/<...>/agents_end.json
  runs/<...>/stats_timeseries.jsonl
  runs/<...>/submit_log.jsonl

Modes:
  --mode fixed-rate  : submit at --rate tasks/sec for --duration seconds
  --mode flood       : keep submitting as fast as possible with --max_inflight cap

Usage examples:
  python bench/run_tokenize_bench.py --mode fixed-rate --rate 2000 --duration 300
  python bench/run_tokenize_bench.py --mode flood --duration 120 --max_inflight 20000
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests


# --------------------------
# Config / helpers
# --------------------------

@dataclass
class RunConfig:
    controller_url: str
    duration_s: int
    mode: str
    rate_tps: Optional[int]
    max_inflight: int
    sample_interval_s: float
    op: str
    payload_bytes: int
    seed: int


def utc_stamp() -> str:
    # filesystem-friendly
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def mkdirp(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def jdump(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True))


def jsonl_append(path: Path, obj: Any) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, sort_keys=False) + "\n")


def rand_text(n: int) -> str:
    # deterministic-ish text generator if seed is set globally
    alphabet = string.ascii_letters + string.digits + "     \n"
    return "".join(random.choice(alphabet) for _ in range(n))


# --------------------------
# API calls
# --------------------------

def get_json(session: requests.Session, url: str, timeout_s: float = 5.0) -> Any:
    r = session.get(url, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def submit_job(session: requests.Session, base: str, op: str, text: str, timeout_s: float = 10.0) -> Dict[str, Any]:
    """
    Adjust this if your /api/job contract differs.

    Tries a couple common payload shapes. If both fail, raises with the response.
    """
    url = f"{base.rstrip('/')}/api/job"

    payloads = [
        # Shape A (common)
        {"op": op, "input": {"text": text}},
        # Shape B (alternate)
        {"task": {"op": op, "input": {"text": text}}},
    ]

    last_err = None
    for payload in payloads:
        try:
            r = session.post(url, json=payload, timeout=timeout_s)
            if 200 <= r.status_code < 300:
                # Might be {job_id:..} or {id:..} or something else; we just log it
                try:
                    return {"ok": True, "status": r.status_code, "resp": r.json()}
                except Exception:
                    return {"ok": True, "status": r.status_code, "resp_text": r.text[:500]}
            else:
                last_err = {"ok": False, "status": r.status_code, "resp_text": r.text[:1000], "payload": payload}
        except Exception as e:
            last_err = {"ok": False, "exc": repr(e), "payload": payload}

    raise RuntimeError(f"Submit failed for all payload shapes. Last error: {last_err}")


# --------------------------
# Bench logic
# --------------------------

def run_bench(cfg: RunConfig) -> Path:
    random.seed(cfg.seed)

    runs_dir = Path(__file__).resolve().parent / "runs"
    mkdirp(runs_dir)

    rate_tag = f"{cfg.rate_tps}tps" if cfg.rate_tps is not None else "na"
    out_dir = runs_dir / f"{utc_stamp()}-tokenize-{cfg.mode}-{rate_tag}"
    mkdirp(out_dir)

    jdump(out_dir / "config.json", asdict(cfg))

    session = requests.Session()

    # Preflight
    agents_url = f"{cfg.controller_url.rstrip('/')}/api/agents"
    stats_url = f"{cfg.controller_url.rstrip('/')}/stats"
    health_url = f"{cfg.controller_url.rstrip('/')}/healthz"

    # Health check (best-effort)
    try:
        r = session.get(health_url, timeout=3.0)
        jsonl_append(out_dir / "submit_log.jsonl", {"t": time.time(), "event": "healthz", "status": r.status_code, "text": r.text[:200]})
    except Exception as e:
        jsonl_append(out_dir / "submit_log.jsonl", {"t": time.time(), "event": "healthz_error", "error": repr(e)})

    agents_start = get_json(session, agents_url, timeout_s=10.0)
    jdump(out_dir / "agents_start.json", agents_start)

    # Stats sampler loop runs in the main thread with time slicing.
    stats_path = out_dir / "stats_timeseries.jsonl"
    submit_log_path = out_dir / "submit_log.jsonl"

    start = time.time()
    end = start + cfg.duration_s

    submitted = 0
    submit_fail = 0

    # For flood mode, track inflight as "submitted - completed_delta".
    # We'll estimate completions by reading /stats if it has completed_total; else we just cap submissions.
    last_completed_total: Optional[int] = None
    baseline_completed_total: Optional[int] = None

    next_sample = start
    next_tick = start

    # Fixed-rate timing control
    interval = 1.0 / cfg.rate_tps if (cfg.mode == "fixed-rate" and cfg.rate_tps and cfg.rate_tps > 0) else 0.0

    while True:
        now = time.time()
        if now >= end:
            break

        # Sample stats periodically
        if now >= next_sample:
            try:
                st = get_json(session, stats_url, timeout_s=5.0)
                jsonl_append(stats_path, {"t": now, "stats": st})

                # Try to discover completed_total
                # We don't know your exact schema; attempt common keys.
                completed_total = None
                for key in ["completed_total", "tasks_completed", "ctrl_tasks_completed"]:
                    if isinstance(st, dict) and key in st and isinstance(st[key], int):
                        completed_total = st[key]
                        break

                if completed_total is not None:
                    if baseline_completed_total is None:
                        baseline_completed_total = completed_total
                    last_completed_total = completed_total

            except Exception as e:
                jsonl_append(stats_path, {"t": now, "error": repr(e)})

            next_sample += cfg.sample_interval_s

        # Submit tasks according to mode
        if cfg.mode == "fixed-rate":
            # Submit exactly one task per interval; catch up if we lag, but don't spiral
            if now >= next_tick:
                text = rand_text(cfg.payload_bytes)
                try:
                    resp = submit_job(session, cfg.controller_url, cfg.op, text)
                    submitted += 1
                    jsonl_append(submit_log_path, {"t": now, "event": "submit_ok", "n": submitted, "resp": resp})
                except Exception as e:
                    submit_fail += 1
                    jsonl_append(submit_log_path, {"t": now, "event": "submit_fail", "n": submitted, "fails": submit_fail, "error": repr(e)})

                next_tick += interval
                # If we fell behind by a lot, jump forward (prevents huge backlog of "catch-up" submits)
                if next_tick < now - 2.0:
                    next_tick = now

        elif cfg.mode == "flood":
            # Estimate inflight if we can; otherwise just use max_inflight as a soft cap via sleep
            inflight = None
            if baseline_completed_total is not None and last_completed_total is not None:
                inflight = submitted - (last_completed_total - baseline_completed_total)

            if inflight is None or inflight < cfg.max_inflight:
                text = rand_text(cfg.payload_bytes)
                try:
                    resp = submit_job(session, cfg.controller_url, cfg.op, text)
                    submitted += 1
                    # Log less verbosely in flood mode
                    if submitted % 1000 == 0:
                        jsonl_append(submit_log_path, {"t": now, "event": "submit_ok", "n": submitted, "inflight": inflight, "resp_hint": resp.get("status")})
                except Exception as e:
                    submit_fail += 1
                    jsonl_append(submit_log_path, {"t": now, "event": "submit_fail", "n": submitted, "fails": submit_fail, "error": repr(e)})
                    time.sleep(0.05)
            else:
                # Backpressure
                time.sleep(0.002)

        else:
            raise ValueError(f"Unknown mode: {cfg.mode}")

    # Final snapshots
    try:
        st_end = get_json(session, stats_url, timeout_s=10.0)
        jsonl_append(stats_path, {"t": time.time(), "event": "final", "stats": st_end})
    except Exception as e:
        jsonl_append(stats_path, {"t": time.time(), "event": "final_error", "error": repr(e)})

    agents_end = get_json(session, agents_url, timeout_s=10.0)
    jdump(out_dir / "agents_end.json", agents_end)

    summary = {
        "submitted": submitted,
        "submit_fail": submit_fail,
        "duration_s": cfg.duration_s,
        "mode": cfg.mode,
        "rate_tps": cfg.rate_tps,
        "max_inflight": cfg.max_inflight,
        "out_dir": str(out_dir),
    }
    jdump(out_dir / "summary.json", summary)

    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller", default=os.environ.get("CONTROLLER_URL", "http://localhost:8080"))
    ap.add_argument("--duration", type=int, default=300)
    ap.add_argument("--mode", choices=["fixed-rate", "flood"], default="fixed-rate")
    ap.add_argument("--rate", type=int, default=2000, help="tasks/sec (fixed-rate mode only)")
    ap.add_argument("--max_inflight", type=int, default=20000, help="flood mode cap (best-effort)")
    ap.add_argument("--sample_interval", type=float, default=1.0)
    ap.add_argument("--op", default="map_tokenize")
    ap.add_argument("--payload_bytes", type=int, default=256)
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()

    cfg = RunConfig(
        controller_url=args.controller,
        duration_s=args.duration,
        mode=args.mode,
        rate_tps=(args.rate if args.mode == "fixed-rate" else None),
        max_inflight=args.max_inflight,
        sample_interval_s=args.sample_interval,
        op=args.op,
        payload_bytes=args.payload_bytes,
        seed=args.seed,
    )

    out = run_bench(cfg)
    print(f"\nDONE. Artifacts written to:\n  {out}\n")


if __name__ == "__main__":
    main()

