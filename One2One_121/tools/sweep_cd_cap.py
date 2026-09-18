# -*- coding: utf-8 -*-
"""Refine CD cap: that is the binding constraint with stop at X."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import collect_zz_states, signals_from_states, to_1based
from sweep_shoulders_free import filt, load_cache, score, universe

STOP_LIM = 15.0


def main():
    vtbr = universe(to_1based(load_cache("cache_VTBR_10m.json")), 0.005, 12)
    imoex = universe(to_1based(load_cache("cache_IMOEX_10m.json")), 0.01, 12)
    print("raw VTBR", score(vtbr))
    print("raw IMOEX", score(imoex))
    print(
        f"{'CDmax':>6} {'V n':>5} {'Vstop':>6} {'I n':>5} {'Istop':>6}  both<=15"
    )
    rows = []
    for cd_hi in [round(x * 0.02, 2) for x in range(25, 61)]:
        sv = score(filt(vtbr, 0.05, 5.0, 0.05, cd_hi, 999))
        si = score(filt(imoex, 0.05, 5.0, 0.05, cd_hi, 999))
        if not sv or not si:
            continue
        ok = sv["stop_pct"] <= STOP_LIM and si["stop_pct"] <= STOP_LIM
        rows.append((cd_hi, sv, si, ok))
        mark = "  YES" if ok else ""
        print(
            f"{cd_hi:6.2f} {sv['n']:5d} {sv['stop_pct']:5.1f} "
            f"{si['n']:5d} {si['stop_pct']:5.1f}{mark}"
        )

    joint = [r for r in rows if r[3]]
    if joint:
        best = max(joint, key=lambda r: r[1]["n"] + r[2]["n"])
        print(
            "\nbest joint CD max=",
            best[0],
            "VTBR",
            best[1],
            "IMOEX",
            best[2],
        )
    vtbr_ok = [r for r in rows if r[1]["stop_pct"] <= STOP_LIM]
    if vtbr_ok:
        b = max(vtbr_ok, key=lambda r: r[1]["n"])
        print("best VTBR-only CD max=", b[0], "VTBR", b[1], "IMOEX", b[2])


if __name__ == "__main__":
    main()
