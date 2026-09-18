# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import to_1based
from sweep_shoulders_free import filt, load_cache, score, universe

vtbr = universe(to_1based(load_cache("cache_VTBR_10m.json")), 0.005, 12)
imoex = universe(to_1based(load_cache("cache_IMOEX_10m.json")), 0.01, 12)
packs = [
    (0.25, 2.00, 0.10, 0.74, 999),
]
print("AB            CD           sym  Vn   Vstop  In   Istop")
for p in packs:
    sv = score(filt(vtbr, *p))
    si = score(filt(imoex, *p))
    print(
        f"{p[0]:.2f}-{p[1]:.2f}  {p[2]:.2f}-{p[3]:.2f}  {p[4]:4d}  "
        f"{sv['n']:4d} {sv['stop_pct']:5.1f}  {si['n']:4d} {si['stop_pct']:5.1f}"
    )
