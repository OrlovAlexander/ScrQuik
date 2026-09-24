# -*- coding: utf-8 -*-
"""Free search of AB/CD/sym windows: max n with stop-before-TP1 <= 15%."""

from __future__ import annotations

import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import collect_zz_states, signals_from_states, to_1based

TOOLS = os.path.dirname(os.path.abspath(__file__))
STOP_LIM = 15.0


def load_cache(name):
    path = os.path.join(TOOLS, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def universe(candles, step, depth):
    states = collect_zz_states(candles, step, depth, 5, 3)
    return signals_from_states(
        states,
        candles,
        ratio_tol=0,
        sym_tol=1000,
        ab_min=0.01,
        ab_max=10.0,
        cd_min=0.01,
        cd_max=10.0,
    )


def score(sigs):
    n = len(sigs)
    if n == 0:
        return None
    stop_n = sum(1 for s in sigs if s["outcome"] == "stop")
    tp1_n = sum(1 for s in sigs if s["hit_tp1"])
    tp2_n = sum(1 for s in sigs if s["hit_tp2"])
    return {
        "n": n,
        "stop_pct": 100.0 * stop_n / n,
        "tp1_pct": 100.0 * tp1_n / n,
        "tp2_pct": 100.0 * tp2_n / n,
    }


def filt(u, a0, a1, c0, c1, sym):
    lim = sym / 100.0
    out = []
    for s in u:
        if s["ab"] < a0 or s["ab"] > a1:
            continue
        if s["cd"] < c0 or s["cd"] > c1:
            continue
        if s["sym"] > lim:
            continue
        out.append(s)
    return out


def sweep(name, u, depth):
    raw = score(u)
    print(
        f"\n===== {name} Depth={depth} universe n={raw['n']} "
        f"stop={raw['stop_pct']:.1f}% TP1={raw['tp1_pct']:.1f}% =====",
        flush=True,
    )
    ab_mins = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60)
    ab_maxs = (0.70, 0.85, 1.00, 1.20, 1.50, 2.00)
    cd_mins = (0.10, 0.20, 0.30, 0.40, 0.50)
    cd_maxs = (0.45, 0.55, 0.65, 0.80, 1.00, 1.20)
    syms = (25, 40, 60, 80, 120, 999)

    best = None
    ranked = []
    for a0, a1, c0, c1, sy in itertools.product(
        ab_mins, ab_maxs, cd_mins, cd_maxs, syms
    ):
        if a0 >= a1 or c0 >= c1:
            continue
        sc = score(filt(u, a0, a1, c0, c1, sy))
        if sc is None or sc["n"] < 30:
            continue
        if sc["stop_pct"] > STOP_LIM:
            continue
        row = {
            "depth": depth,
            "ab_min": a0,
            "ab_max": a1,
            "cd_min": c0,
            "cd_max": c1,
            "sym": sy,
            **sc,
        }
        ranked.append(row)
        if best is None or sc["n"] > best["n"] or (
            sc["n"] == best["n"] and sc["stop_pct"] < best["stop_pct"]
        ):
            best = row

    ranked.sort(key=lambda r: (-r["n"], r["stop_pct"]))
    print("top by n, stop<=15%:")
    print(
        f"{'AB':>13} {'CD':>13} {'sym':>4} {'n':>5} {'stop':>6} {'TP1':>6} {'TP2':>6}"
    )
    for r in ranked[:12]:
        print(
            f"{r['ab_min']:4.2f}-{r['ab_max']:4.2f}  "
            f"{r['cd_min']:4.2f}-{r['cd_max']:4.2f}  "
            f"{r['sym']:4.0f} {r['n']:5d} {r['stop_pct']:5.1f} "
            f"{r['tp1_pct']:5.1f} {r['tp2_pct']:5.1f}"
        )
    return {"universe": raw, "best": best, "top": ranked[:20]}


def main():
    vtbr = to_1based(load_cache("cache_VTBR_10m.json"))
    imoex = to_1based(load_cache("cache_IMOEX_10m.json"))
    out = {}
    for name, candles, step in (
        ("VTBR M10", vtbr, 0.005),
        ("IMOEX M10", imoex, 0.01),
    ):
        out[name] = {}
        for depth in (8, 12):
            u = universe(candles, step, depth)
            out[name][str(depth)] = sweep(name, u, depth)

    # cross-check: apply VTBR D12 best to IMOEX D12
    vb = out["VTBR M10"]["12"]["best"]
    if vb:
        u_im = universe(imoex, 0.01, 12)
        sc = score(
            filt(u_im, vb["ab_min"], vb["ab_max"], vb["cd_min"], vb["cd_max"], vb["sym"])
        )
        print("\nVTBR D12-best on IMOEX D12:", sc)
        out["cross_vtbr_best_on_imoex"] = sc

    path = os.path.join(TOOLS, "sweep_shoulders_free.json")
    dump = {}
    for k, v in out.items():
        if k.startswith("cross"):
            dump[k] = v
            continue
        dump[k] = {
            d: {"universe": v[d]["universe"], "best": v[d]["best"], "top": v[d]["top"]}
            for d in v
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2)
    print("wrote", path)


if __name__ == "__main__":
    main()
