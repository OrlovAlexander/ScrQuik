# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import collect_zz_states, signals_from_states, to_1based
from sweep_shoulders import TOOLS, filter_sigs, load_or_fetch, score

PACKS = [
    ("current", 12, 0.618, 0.786, 0.500, 0.618, 18),
    ("AB50-88 CD38-62 s25", 12, 0.500, 0.886, 0.382, 0.618, 25),
    ("AB50-88 CD38-62 s30", 12, 0.500, 0.886, 0.382, 0.618, 30),
    ("AB50-79 CD38-62 s25", 12, 0.500, 0.786, 0.382, 0.618, 25),
    ("AB50-88 CD38-50 s25", 12, 0.500, 0.886, 0.382, 0.500, 25),
    ("AB62-79 CD38-50 s18", 12, 0.618, 0.786, 0.382, 0.500, 18),
    ("AB50-88 CD38-62 s25 D8", 8, 0.500, 0.886, 0.382, 0.618, 25),
    ("AB50-88 CD38-50 s25 D8", 8, 0.500, 0.886, 0.382, 0.500, 25),
]


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
            "VTBR",
            to_1based(
                load_or_fetch(
                    os.path.join(TOOLS, "cache_VTBR_10m.json"),
                    "VTBR",
                    "shares",
                    10,
                    "a",
                    "b",
                )
            ),
            0.005,
        ),
        (
            "IMOEX",
            to_1based(
                load_or_fetch(
                    os.path.join(TOOLS, "cache_IMOEX_10m.json"),
                    "IMOEX",
                    "index",
                    10,
                    "a",
                    "b",
                )
            ),
            0.01,
        ),
    ]
    cache = {}
    print(f"{'pack':<26} {'ins':<6} {'n':>4} {'stop':>6} {'TP1':>6} {'TP2':>6}")
    for name, candles, step in sets:
        for label, depth, a0, a1, c0, c1, sy in PACKS:
            key = (id(candles), depth)
            if key not in cache:
                cache[key] = universe(candles, step, depth)
            sc = score(filter_sigs(cache[key], a0, a1, c0, c1, sy)) or {
                "n": 0,
                "stop_pct": 0,
                "tp1_pct": 0,
                "tp2_pct": 0,
            }
            print(
                f"{label:<26} {name:<6} {sc['n']:4d} {sc['stop_pct']:5.1f} "
                f"{sc['tp1_pct']:5.1f} {sc['tp2_pct']:5.1f}"
            )


if __name__ == "__main__":
    main()
