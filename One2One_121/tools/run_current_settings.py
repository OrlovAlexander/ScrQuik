# -*- coding: utf-8 -*-
"""Replay current 121 settings on VTBR / IMOEX M5, M10, H1."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from move_stats import (  # noqa: E402
    fetch_moex_candles,
    replay,
    resample_ohlc,
    summarize,
    to_1based,
)

TOOLS = os.path.dirname(os.path.abspath(__file__))


def load_or_fetch(cache_name, sec, market, tf, date_from, date_till):
    path = os.path.join(TOOLS, cache_name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        print(f"cache {sec} {tf}m bars={len(rows)}", flush=True)
        return rows
    native = tf if tf in (1, 10, 60) else 1
    print(f"fetch {sec} {market} {native}m {date_from}..{date_till}", flush=True)
    raw = fetch_moex_candles(sec, native, date_from, date_till, market=market)
    rows = resample_ohlc(raw, tf) if tf not in (1, 10, 60) else raw
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    print(f"saved {path} bars={len(rows)}", flush=True)
    return rows


def run_one(label, cache_name, sec, market, tf, date_from, date_till, step):
    rows = load_or_fetch(cache_name, sec, market, tf, date_from, date_till)
    candles = to_1based(rows)
    signals = replay(candles, step, 12, 5, 3, 0, 999)
    text = summarize(signals)
    print(f"\n===== {label} bars={len(rows)} =====", flush=True)
    print(text, flush=True)
    out = {
        "sec": sec,
        "market": market,
        "tf": tf,
        "from": date_from,
        "till": date_till,
        "params": {
            "depth": 12,
            "deviation": 5,
            "backstep": 3,
            "ratio_tol": 0,
            "sym_tol": 999,
            "ab": "0.25-2.00",
            "cd": "0.10-0.74",
            "tp1": "0.236 D-C",
            "stop": "X",
            "step": step,
        },
        "summary": text,
        "signals": signals,
    }
    out_path = os.path.join(TOOLS, f"move_stats_{sec}_{tf}m.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote", out_path, flush=True)
    return text


def main():
    jobs = [
        (
            "VTBR M10",
            "cache_VTBR_10m.json",
            "VTBR",
            "shares",
            10,
            "2025-01-01",
            "2026-09-11",
            0.005,
        ),
        (
            "IMOEX M10",
            "cache_IMOEX_10m.json",
            "IMOEX",
            "index",
            10,
            "2025-01-01",
            "2026-09-11",
            0.01,
        ),
        (
            "VTBR H1",
            "cache_VTBR_60m.json",
            "VTBR",
            "shares",
            60,
            "2024-01-01",
            "2026-09-11",
            0.005,
        ),
        (
            "IMOEX H1",
            "cache_IMOEX_60m.json",
            "IMOEX",
            "index",
            60,
            "2024-01-01",
            "2026-09-11",
            0.01,
        ),
        (
            "VTBR M5",
            "cache_VTBR_5m.json",
            "VTBR",
            "shares",
            5,
            "2026-01-01",
            "2026-09-11",
            0.005,
        ),
        (
            "IMOEX M5",
            "cache_IMOEX_5m.json",
            "IMOEX",
            "index",
            5,
            "2026-01-01",
            "2026-09-11",
            0.01,
        ),
    ]
    for job in jobs:
        run_one(*job)


if __name__ == "__main__":
    main()
