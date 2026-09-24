# -*- coding: utf-8 -*-
"""Find geometry/filters with stop-before-TP1 around 15%."""

from __future__ import annotations

import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import (  # noqa: E402
    collect_zz_states,
    pct,
    signals_from_states,
    to_1based,
)

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache_VTBR_10m.json")
STEP = 0.005


def score(signals):
    n = len(signals)
    if n == 0:
        return None
    stop_n = sum(1 for s in signals if s["outcome"] == "stop")
    tp1_n = sum(1 for s in signals if s["hit_tp1"])
    tp2_n = sum(1 for s in signals if s["hit_tp2"])
    return {
        "n": n,
        "stop_pct": pct(stop_n, n),
        "tp1_pct": pct(tp1_n, n),
        "tp2_pct": pct(tp2_n, n),
    }


def main():
    with open(CACHE, encoding="utf-8") as f:
        candles = to_1based(json.load(f))
    print(f"bars={len(candles) - 1}")

    zz_cfgs = [(8, 5, 3), (12, 5, 3)]
    cd_maxs = (0.52, 0.55, 0.618)
    tp1s = (0.236, 0.382, 0.50)
    stops = (0.786, 0.886, 1.0)
    min_rrs = (0.0, 1.5, 2.0, 3.0)

    rows = []
    for depth, deviation, backstep in zz_cfgs:
        print(f"ZZ Depth={depth} ...", flush=True)
        states = collect_zz_states(candles, STEP, depth, deviation, backstep)
        for cd_max, tp1, stop, min_rr in itertools.product(
            cd_maxs, tp1s, stops, min_rrs
        ):
            sigs = signals_from_states(
                states,
                candles,
                5,
                18,
                cd_max=cd_max,
                tp1_ratio=tp1,
                stop_ratio=stop,
                min_rr=min_rr,
            )
            sc = score(sigs)
            if sc is None or sc["n"] < 25:
                continue
            rows.append(
                {
                    "depth": depth,
                    "cd_max": cd_max,
                    "tp1": tp1,
                    "stop": stop,
                    "min_rr": min_rr,
                    **sc,
                }
            )

    rows.sort(key=lambda r: (abs(r["stop_pct"] - 15.0), -r["n"]))
    near = [r for r in rows if r["stop_pct"] <= 15.0]
    print("\n=== stop% <= 15, n>=25 ===")
    print(
        f"{'D':>3} {'cd':>5} {'tp1':>5} {'st':>5} {'rr':>4} "
        f"{'n':>4} {'stop%':>7} {'TP1%':>7} {'TP2%':>7}"
    )
    for r in near[:20]:
        print(
            f"{r['depth']:3d} {r['cd_max']:5.3f} {r['tp1']:5.3f} {r['stop']:5.3f} "
            f"{r['min_rr']:4.1f} {r['n']:4d} {r['stop_pct']:6.1f} "
            f"{r['tp1_pct']:6.1f} {r['tp2_pct']:6.1f}"
        )
    if not near:
        print("(none)")
        print("\n=== closest to 15% ===")
        for r in rows[:15]:
            print(
                f"D={r['depth']} cd={r['cd_max']:.3f} tp1={r['tp1']:.3f} "
                f"st={r['stop']:.3f} rr={r['min_rr']:.1f} n={r['n']} "
                f"stop={r['stop_pct']:.1f}% TP1={r['tp1_pct']:.1f}%"
            )

    out = os.path.join(os.path.dirname(CACHE), "sweep_15_VTBR_10m.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"near15": near, "all": rows}, f)
    print("wrote", out)


if __name__ == "__main__":
    main()
