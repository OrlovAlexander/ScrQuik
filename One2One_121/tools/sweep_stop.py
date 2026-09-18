# -*- coding: utf-8 -*-
"""Grid-search One2One params to get stop-before-TP1 below 50%."""

from __future__ import annotations

import itertools
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import (  # noqa: E402
    collect_zz_states,
    fetch_moex_candles,
    pct,
    resample_ohlc,
    signals_from_states,
    to_1based,
)

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_VTBR_10m.json")
SEC = "VTBR"
TF = 10
DATE_FROM = "2025-01-01"
DATE_TILL = "2026-09-11"
STEP = 0.005

ZZ_GRID = [
    (8, 5, 3),
    (10, 5, 3),
    (12, 3, 3),
    (12, 5, 3),
    (12, 8, 3),
    (16, 5, 3),
    (20, 5, 3),
    (24, 5, 3),
    (12, 5, 2),
    (12, 5, 5),
]

RATIO_GRID = (3, 5, 8)
SYM_GRID = (10, 15, 18, 22)
CD_MAX_GRID = (0.618, 0.70, 0.786)


def load_candles():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            rows = json.load(f)
        print(f"cache {CACHE} bars={len(rows)}")
        return to_1based(rows)
    print(f"fetch {SEC} {TF}m {DATE_FROM}..{DATE_TILL}")
    raw = fetch_moex_candles(SEC, TF, DATE_FROM, DATE_TILL)
    rows = resample_ohlc(raw, TF) if TF not in (1, 10, 60) else raw
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    print(f"saved {CACHE} bars={len(rows)}")
    return to_1based(rows)


def score(signals):
    n = len(signals)
    if n == 0:
        return {
            "n": 0,
            "stop_pct": 100.0,
            "tp1_pct": 0.0,
            "tp2_pct": 0.0,
            "dir_pct": 0.0,
        }
    stop_n = sum(1 for s in signals if s["outcome"] == "stop")
    tp1_n = sum(1 for s in signals if s["hit_tp1"])
    tp2_n = sum(1 for s in signals if s["hit_tp2"])
    dir_n = sum(1 for s in signals if s["dir_move"])
    return {
        "n": n,
        "stop_pct": pct(stop_n, n),
        "tp1_pct": pct(tp1_n, n),
        "tp2_pct": pct(tp2_n, n),
        "dir_pct": pct(dir_n, n),
    }


def zz_worker(item):
    depth, deviation, backstep, candles = item
    states = collect_zz_states(candles, STEP, depth, deviation, backstep)
    rows = []
    for ratio_tol, sym_tol, cd_max in itertools.product(
        RATIO_GRID, SYM_GRID, CD_MAX_GRID
    ):
        sigs = signals_from_states(states, candles, ratio_tol, sym_tol, cd_max)
        sc = score(sigs)
        rows.append(
            {
                "depth": depth,
                "deviation": deviation,
                "backstep": backstep,
                "ratio_tol": ratio_tol,
                "sym_tol": sym_tol,
                "cd_max": cd_max,
                **sc,
            }
        )
    return rows


def main():
    candles = load_candles()
    jobs = [(*zz, candles) for zz in ZZ_GRID]
    all_rows = []
    print(f"ZZ configs={len(jobs)} filter combos/config={len(RATIO_GRID)*len(SYM_GRID)*len(CD_MAX_GRID)}")
    with ProcessPoolExecutor(max_workers=min(4, len(jobs))) as pool:
        futs = [pool.submit(zz_worker, job) for job in jobs]
        for fut in as_completed(futs):
            rows = fut.result()
            all_rows.extend(rows)
            zz = rows[0]
            print(
                f"done Depth={zz['depth']} Dev={zz['deviation']} BS={zz['backstep']}",
                flush=True,
            )

    viable = [r for r in all_rows if r["n"] >= 40]
    viable.sort(key=lambda r: (r["stop_pct"], -r["tp1_pct"], -r["n"]))
    print("\n=== stop-before-TP1, n>=40 ===")
    print(
        f"{'D':>3} {'Dv':>3} {'Bs':>3} {'rt':>3} {'sy':>3} {'cd':>5} "
        f"{'n':>4} {'stop%':>7} {'TP1%':>7} {'TP2%':>7}"
    )
    shown = 0
    for r in viable:
        mark = " *" if r["stop_pct"] < 50 else ""
        print(
            f"{r['depth']:3d} {r['deviation']:3d} {r['backstep']:3d} "
            f"{r['ratio_tol']:3.0f} {r['sym_tol']:3.0f} {r['cd_max']:5.3f} "
            f"{r['n']:4d} {r['stop_pct']:6.1f} {r['tp1_pct']:6.1f} {r['tp2_pct']:6.1f}{mark}"
        )
        shown += 1
        if shown >= 25:
            break

    below = [r for r in viable if r["stop_pct"] < 50]
    print(f"\nbelow 50% stop: {len(below)} of {len(viable)} (n>=40)")
    out_path = os.path.join(os.path.dirname(CACHE), "sweep_stop_VTBR_10m.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"rows": all_rows}, f)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
