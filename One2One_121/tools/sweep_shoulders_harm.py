# -*- coding: utf-8 -*-
from __future__ import annotations

import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import collect_zz_states, signals_from_states, to_1based
from sweep_shoulders import TOOLS, filter_sigs, load_or_fetch, score

AB_WINS = ((0.500, 0.786), (0.500, 0.886), (0.618, 0.786), (0.618, 0.886))
CD_WINS = ((0.382, 0.618), (0.500, 0.618), (0.382, 0.500))
SYMS = (15, 18, 22, 25, 30)


def universe(candles, step, depth):
    states = collect_zz_states(candles, step, depth, 5, 3)
    return signals_from_states(
        states,
        candles,
        0,
        1000,
        ab_min=0.01,
        ab_max=5,
        cd_min=0.01,
        cd_max=5,
    )


def main():
    sets = [
        (
            "VTBR M10",
            to_1based(
                load_or_fetch(
                    os.path.join(TOOLS, "cache_VTBR_10m.json"),
                    "VTBR",
                    "shares",
                    10,
                    "2025-01-01",
                    "2026-09-11",
                )
            ),
            0.005,
        ),
        (
            "IMOEX M10",
            to_1based(
                load_or_fetch(
                    os.path.join(TOOLS, "cache_IMOEX_10m.json"),
                    "IMOEX",
                    "index",
                    10,
                    "2025-01-01",
                    "2026-09-11",
                )
            ),
            0.01,
        ),
    ]
    hdr = "  D  AB            CD           sym    n  stop   TP1   TP2"
    for name, candles, step in sets:
        print(f"\n==== {name} harmonic-ish ====")
        print(hdr)
        for depth in (8, 12):
            u = universe(candles, step, depth)
            rows = []
            for (a0, a1), (c0, c1), sy in itertools.product(AB_WINS, CD_WINS, SYMS):
                sc = score(filter_sigs(u, a0, a1, c0, c1, sy))
                if not sc:
                    continue
                rows.append((depth, a0, a1, c0, c1, sy, sc))
            ok = [r for r in rows if r[6]["stop_pct"] <= 15]
            ok.sort(key=lambda r: -r[6]["n"])
            if ok:
                show = ok[:10]
            else:
                print(f"  Depth={depth}: none <=15%; closest:")
                show = sorted(rows, key=lambda r: (r[6]["stop_pct"], -r[6]["n"]))[:6]
            for d, a0, a1, c0, c1, sy, sc in show:
                print(
                    f"{d:3d} {a0:4.3f}-{a1:4.3f}  {c0:4.3f}-{c1:4.3f}  "
                    f"{sy:3d} {sc['n']:4d} {sc['stop_pct']:5.1f} "
                    f"{sc['tp1_pct']:5.1f} {sc['tp2_pct']:5.1f}"
                )


if __name__ == "__main__":
    main()
