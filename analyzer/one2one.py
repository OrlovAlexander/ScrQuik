# -*- coding: utf-8 -*-
"""One2One_121 on a barsSaver M30 series (settings from One2One_121.ini)."""

from __future__ import annotations

import sys
from pathlib import Path

from analyzer.bars import Bar
from analyzer.settings import One2OneSettings, load_one2one_settings

_TOOLS = Path(__file__).resolve().parents[1] / "tools" / "one2one"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from move_stats import (  # noqa: E402
    ZigZagEngine,
    calc_levels,
    scan_patterns,
    to_1based,
)


def _to_candles(bars: list[Bar]) -> list[dict]:
    rows = [
        {
            "begin": b.dt.isoformat(sep=" "),
            "open": b.o,
            "high": b.h,
            "low": b.l,
            "close": b.c,
        }
        for b in bars
    ]
    return to_1based(rows)


def infer_step(bars: list[Bar]) -> float:
    diffs = []
    prev = None
    for b in bars[-400:]:
        if prev is not None:
            d = abs(b.c - prev)
            if d > 0:
                diffs.append(d)
        prev = b.c
    if not diffs:
        return 0.01
    return min(diffs)


def current_pattern(
    bars: list[Bar],
    price_step: float | None = None,
    settings: One2OneSettings | None = None,
) -> dict | None:
    if len(bars) < 20:
        return None
    st = settings or load_one2one_settings()
    step = price_step if price_step is not None else infer_step(bars)
    candles = _to_candles(bars)
    engine = ZigZagEngine(step)
    zz: list = []
    ready = False
    last_i = len(bars)
    for i in range(1, last_i + 1):
        zz, ready = engine.update(
            i, st.depth, st.deviation, st.backstep, size=i, candle=candles[i]
        )
    if not ready or len(zz) < 5:
        return None
    patterns = scan_patterns(list(zz), st.ratio_tol, st.sym_tol, history_depth=1)
    if not patterns:
        return None
    pat = patterns[0]
    lv = calc_levels(pat["values"]["pX"], pat["values"]["pC"], p_d=pat["values"]["pD"])
    pts = pat["points"]
    return {
        "direction": pat["info"]["direction"],
        "ab": pat["info"]["ab_ratio"],
        "cd": pat["info"]["cd_ratio"],
        "sym": pat["info"]["symmetry"],
        "X": {"i": pts["X"]["index"], "price": pat["values"]["pX"], "dt": candles[pts["X"]["index"]]["begin"]},
        "A": {"i": pts["A"]["index"], "price": pat["values"]["pA"], "dt": candles[pts["A"]["index"]]["begin"]},
        "B": {"i": pts["B"]["index"], "price": pat["values"]["pB"], "dt": candles[pts["B"]["index"]]["begin"]},
        "C": {"i": pts["C"]["index"], "price": pat["values"]["pC"], "dt": candles[pts["C"]["index"]]["begin"]},
        "D": {"i": pts["D"]["index"], "price": pat["values"]["pD"], "dt": candles[pts["D"]["index"]]["begin"]},
        "stop": lv["stop"],
        "tp1": lv["tp1"],
        "tp2": lv["tp2"],
        "tp3": lv["tp3"],
        "price_step": step,
        "depth": st.depth,
        "deviation": st.deviation,
        "backstep": st.backstep,
    }


def pattern_events(
    bars: list[Bar],
    price_step: float | None = None,
    settings: One2OneSettings | None = None,
) -> list[dict | None]:
    """Tag the bar where a 121 D is first confirmed. Later bars stay None until D changes."""
    n = len(bars)
    out: list[dict | None] = [None] * n
    if n < 20:
        return out
    st = settings or load_one2one_settings()
    step = price_step if price_step is not None else infer_step(bars)
    candles = _to_candles(bars)
    engine = ZigZagEngine(step)
    seen: set[int] = set()
    for i in range(1, n + 1):
        zz, ready = engine.update(
            i, st.depth, st.deviation, st.backstep, size=i, candle=candles[i]
        )
        if not ready or len(zz) < 5:
            continue
        patterns = scan_patterns(list(zz), st.ratio_tol, st.sym_tol, history_depth=1)
        if not patterns:
            continue
        pat = patterns[0]
        d_i = pat["points"]["D"]["index"]
        if d_i in seen:
            continue
        seen.add(d_i)
        out[i - 1] = {
            "direction": pat["info"]["direction"],
            "ab": pat["info"]["ab_ratio"],
            "cd": pat["info"]["cd_ratio"],
            "d_index": d_i,
        }
    return out
