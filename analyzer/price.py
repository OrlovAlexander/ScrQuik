# -*- coding: utf-8 -*-
"""Classify price movement on one chart TF."""

from __future__ import annotations

from analyzer.bars import Bar

LOOKBACK = {"M1": 12, "M10": 8, "M30": 6, "H4": 4}
MOVES = ("flat", "up", "down", "start_up", "start_down")


def _mean_range(bars: list[Bar], start: int, end: int) -> float:
    acc = 0.0
    n = 0
    for i in range(start, end + 1):
        acc += bars[i].h - bars[i].l
        n += 1
    return (acc / n) if n else 0.0


def _raw_move(bars: list[Bar], i: int, lookback: int) -> str:
    if i < lookback:
        return "unknown"
    start = i - lookback
    net = bars[i].c - bars[start].c
    hi = max(b.h for b in bars[start : i + 1])
    lo = min(b.l for b in bars[start : i + 1])
    rng = hi - lo
    mean_rng = _mean_range(bars, start, i) or 1e-9
    if rng < 1.6 * mean_rng and abs(net) < 0.75 * mean_rng:
        return "flat"
    if net > 0.9 * mean_rng:
        return "up"
    if net < -0.9 * mean_rng:
        return "down"
    if rng < 2.2 * mean_rng:
        return "flat"
    return "up" if net >= 0 else "down"


def classify_moves(bars: list[Bar], tf: str) -> list[str]:
    lookback = LOOKBACK.get(tf, 8)
    raw = [_raw_move(bars, i, lookback) for i in range(len(bars))]
    out: list[str] = []
    prev = "unknown"
    for label in raw:
        if label == "up" and prev in {"flat", "down"}:
            out.append("start_up")
        elif label == "down" and prev in {"flat", "up"}:
            out.append("start_down")
        else:
            out.append(label)
        if label != "unknown":
            prev = label
    return out
