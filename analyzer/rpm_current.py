# -*- coding: utf-8 -*-
"""RPM-TF-Current: 12-bar FIR on typical price + EMA(Period)."""

from __future__ import annotations

from analyzer.bars import Bar, typical
from analyzer.ema import Ema

CURRENT_PERIOD = 90
FIR_W = (1.6, 1.6, 1.4, 1.4, 0.5, 0.5, -1.5, -1.5, -1.0, -1.0, -1.0, -1.0)


def fir_typical(bars: list[Bar], i: int) -> float:
    acc = 0.0
    for k, w in enumerate(FIR_W):
        j = i - k
        acc += (typical(bars[j]) if j >= 0 else 0.0) * w
    return acc / 12.0


def half_history_start(n: int) -> int:
    """0-based first bar of the second half; matches Lua floor(Size/2)+1."""
    if n < 2:
        return 0
    return n // 2


def compute_current(bars: list[Bar], period: int = CURRENT_PERIOD) -> list[dict]:
    ema = Ema(period)
    out: list[dict] = []
    start = half_history_start(len(bars))
    for i, bar in enumerate(bars):
        if i == 0 or i < start:
            out.append({"dt": bar.dt, "rpm": None, "ema": None})
            continue
        rpm = fir_typical(bars, i)
        ema_v = ema.update(rpm)
        out.append({"dt": bar.dt, "rpm": rpm, "ema": ema_v})
    return out
