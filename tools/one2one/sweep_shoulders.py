# -*- coding: utf-8 -*-
"""Sweep AB/XA, CD/XC and symmetry; keep stop-before-TP1 <= 15%."""

from __future__ import annotations

import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import (  # noqa: E402
    collect_zz_states,
    fetch_moex_candles,
    pct,
    signals_from_states,
    to_1based,
)

TOOLS = os.path.dirname(os.path.abspath(__file__))
AB_WINDOWS = (
    (0.382, 0.618),
    (0.382, 0.786),
    (0.382, 0.886),
    (0.382, 1.000),
    (0.500, 0.786),
    (0.500, 0.886),
    (0.500, 1.000),
    (0.618, 0.786),
    (0.618, 0.886),
    (0.618, 1.000),
    (0.786, 1.000),
)
CD_WINDOWS = (
    (0.236, 0.500),
    (0.236, 0.618),
    (0.382, 0.500),
    (0.382, 0.618),
    (0.382, 0.786),
    (0.500, 0.618),
    (0.500, 0.786),
    (0.500, 0.886),
    (0.618, 0.786),
)
SYM_TOLS = (8, 12, 15, 18, 22, 25, 30, 40, 60)
ZZ_CFGS = ((8, 5, 3), (12, 5, 3))


def load_or_fetch(path, sec, market, tf, date_from, date_till, board="TQBR"):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        print(f"cache {sec} {tf}m bars={len(rows)}", flush=True)
        return rows
    native = tf if tf in (1, 10, 60) else 1
    print(f"fetch {sec} {market} {native}m {date_from}..{date_till}", flush=True)
    raw = fetch_moex_candles(
        sec, native, date_from, date_till, board=board, market=market
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    print(f"saved {path} bars={len(raw)}", flush=True)
    return raw


def score(sigs):
    n = len(sigs)
    if n == 0:
        return None
    stop_n = sum(1 for s in sigs if s["outcome"] == "stop")
    tp1_n = sum(1 for s in sigs if s["hit_tp1"])
    tp2_n = sum(1 for s in sigs if s["hit_tp2"])
    return {
        "n": n,
        "stop_pct": round(pct(stop_n, n), 1),
        "tp1_pct": round(pct(tp1_n, n), 1),
        "tp2_pct": round(pct(tp2_n, n), 1),
        "bull": sum(1 for s in sigs if s["direction"] == "bull"),
        "bear": sum(1 for s in sigs if s["direction"] == "bear"),
    }


def in_win(value, lo, hi, tol):
    return (lo - tol) <= value <= (hi + tol)


def filter_sigs(universe, ab_lo, ab_hi, cd_lo, cd_hi, sym_pct, tol=0.05):
    lim = sym_pct / 100.0
    out = []
    for s in universe:
        if not in_win(s["ab"], ab_lo, ab_hi, tol):
            continue
        if not in_win(s["cd"], cd_lo, cd_hi, tol):
            continue
        if s["sym"] > lim:
            continue
        out.append(s)
    return out


def sweep_dataset(name, candles, step):
    print(f"\n===== {name} bars={len(candles) - 1} =====", flush=True)
    ranked = []
    for depth, deviation, backstep in ZZ_CFGS:
        print(f"ZZ Depth={depth} ...", flush=True)
        states = collect_zz_states(candles, step, depth, deviation, backstep)
        universe = signals_from_states(
            states,
            candles,
            ratio_tol=0,
            sym_tol=1000,
            ab_min=0.01,
            ab_max=5.0,
            cd_min=0.01,
            cd_max=5.0,
        )
        print(f"  directional 5-point n={len(universe)}", flush=True)
        base = filter_sigs(universe, 0.618, 0.786, 0.500, 0.618, 18)
        bs = score(base)
        print(f"  baseline AB 61.8-78.6 CD 50-61.8 sym18: {bs}", flush=True)

        for (ab_lo, ab_hi), (cd_lo, cd_hi), sym in itertools.product(
            AB_WINDOWS, CD_WINDOWS, SYM_TOLS
        ):
            sigs = filter_sigs(universe, ab_lo, ab_hi, cd_lo, cd_hi, sym)
            sc = score(sigs)
            if sc is None or sc["n"] < 20:
                continue
            ranked.append(
                {
                    "depth": depth,
                    "ab_min": ab_lo,
                    "ab_max": ab_hi,
                    "cd_min": cd_lo,
                    "cd_max": cd_hi,
                    "sym": sym,
                    **sc,
                }
            )

    ok = [r for r in ranked if r["stop_pct"] <= 15.0]
    ok.sort(key=lambda r: (-r["n"], r["stop_pct"]))
    print("\n=== stop% <= 15, n>=20, max n first ===")
    print(
        f"{'D':>3} {'ABlo':>5} {'ABhi':>5} {'CDlo':>5} {'CDhi':>5} "
        f"{'sym':>3} {'n':>4} {'stop%':>6} {'TP1%':>6} {'TP2%':>6}"
    )
    for r in ok[:25]:
        print(
            f"{r['depth']:3d} {r['ab_min']:5.3f} {r['ab_max']:5.3f} "
            f"{r['cd_min']:5.3f} {r['cd_max']:5.3f} {r['sym']:3d} "
            f"{r['n']:4d} {r['stop_pct']:5.1f} {r['tp1_pct']:5.1f} {r['tp2_pct']:5.1f}"
        )
    if not ok:
        print("(none)")
        ranked.sort(key=lambda r: (r["stop_pct"], -r["n"]))
        print("\n=== lowest stop% ===")
        for r in ranked[:12]:
            print(
                f"D={r['depth']} AB={r['ab_min']:.3f}-{r['ab_max']:.3f} "
                f"CD={r['cd_min']:.3f}-{r['cd_max']:.3f} sym={r['sym']} "
                f"n={r['n']} stop={r['stop_pct']:.1f}% TP1={r['tp1_pct']:.1f}%"
            )
    return {"ok": ok, "all": ranked}


def main():
    vtbr = load_or_fetch(
        os.path.join(TOOLS, "cache_VTBR_10m.json"),
        "VTBR",
        "shares",
        10,
        "2025-01-01",
        "2026-09-11",
    )
    imoex = load_or_fetch(
        os.path.join(TOOLS, "cache_IMOEX_10m.json"),
        "IMOEX",
        "index",
        10,
        "2025-01-01",
        "2026-09-11",
    )
    out = {
        "VTBR_10m": sweep_dataset("VTBR M10", to_1based(vtbr), 0.005),
        "IMOEX_10m": sweep_dataset("IMOEX M10", to_1based(imoex), 0.01),
    }
    path = os.path.join(TOOLS, "sweep_shoulders.json")
    slim = {
        k: {"ok": v["ok"][:40], "n_ok": len(v["ok"]), "n_all": len(v["all"])}
        for k, v in out.items()
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2)
    print("wrote", path)


if __name__ == "__main__":
    main()
