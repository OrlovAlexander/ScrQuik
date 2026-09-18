# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import (
    collect_zz_states,
    signals_from_states,
    to_1based,
)
from sweep_shoulders_free import load_cache, score

AB = (0.25, 2.00)
CD = (0.10, 0.74)


def run(candles, step, tp1):
    states = collect_zz_states(candles, step, 12, 5, 3)
    return signals_from_states(
        states,
        candles,
        0,
        999,
        ab_min=AB[0],
        ab_max=AB[1],
        cd_min=CD[0],
        cd_max=CD[1],
        tp1_ratio=tp1,
    )


def main():
    vtbr = to_1based(load_cache("cache_VTBR_10m.json"))
    imoex = to_1based(load_cache("cache_IMOEX_10m.json"))
    print("TP1 of D->C, AB 25-200 CD 20-74, stop=X")
    print("tp1    Vn  Vstop   In  Istop")
    for tp1 in (0.10, 0.15, 0.20, 0.236, 0.30, 0.382):
        sv = score(run(vtbr, 0.005, tp1))
        si = score(run(imoex, 0.01, tp1))
        print(
            f"{tp1:5.3f} {sv['n']:4d} {sv['stop_pct']:5.1f}  "
            f"{si['n']:4d} {si['stop_pct']:5.1f}"
        )


if __name__ == "__main__":
    main()
