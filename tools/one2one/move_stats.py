# -*- coding: utf-8 -*-
"""Replay One2One 121 on MOEX candles and score moves from D (not PnL)."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

FIB_AB_MIN = 0.25
FIB_AB_MAX = 2.00
FIB_CD_MIN = 0.10
FIB_CD_MAX = 0.74
TP1_RATIO = 0.236
TP3_RATIO = -0.272

MOEX_PAGE = 500


def fetch_moex_candles(
    sec: str,
    interval: int,
    start_date: str,
    end_date: str,
    board: str = "TQBR",
    market: str = "shares",
) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        qs = urllib.parse.urlencode(
            {
                "interval": interval,
                "from": start_date,
                "till": end_date,
                "iss.meta": "off",
                "iss.only": "candles",
                "candles.columns": "begin,open,high,low,close,volume",
                "candles.start": start,
            }
        )
        if market == "index":
            url = (
                "https://iss.moex.com/iss/engines/stock/markets/index/"
                f"securities/{sec}/candles.json?{qs}"
            )
        else:
            url = (
                "https://iss.moex.com/iss/engines/stock/markets/shares/"
                f"boards/{board}/securities/{sec}/candles.json?{qs}"
            )
        payload = None
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                break
            except (OSError, TimeoutError) as exc:
                last_err = exc
                time.sleep(1.5 * (attempt + 1))
        if payload is None:
            raise last_err or RuntimeError("ISS fetch failed")
        data = payload.get("candles", {}).get("data") or []
        cols = payload.get("candles", {}).get("columns") or [
            "begin",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
        for item in data:
            row = dict(zip(cols, item))
            rows.append(
                {
                    "begin": row["begin"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume") or 0),
                }
            )
        if len(data) < MOEX_PAGE:
            break
        start += MOEX_PAGE
        time.sleep(0.12)
    rows.sort(key=lambda r: r["begin"])
    return rows


def resample_ohlc(rows: list[dict], minutes: int) -> list[dict]:
    if minutes <= 1:
        return rows
    buckets: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        dt = datetime.strptime(row["begin"][:19], "%Y-%m-%d %H:%M:%S")
        floored = dt.replace(
            minute=(dt.minute // minutes) * minutes, second=0, microsecond=0
        )
        key = floored.strftime("%Y-%m-%d %H:%M:%S")
        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = {
                "begin": key,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            order.append(key)
        else:
            bucket["high"] = max(bucket["high"], row["high"])
            bucket["low"] = min(bucket["low"], row["low"])
            bucket["close"] = row["close"]
            bucket["volume"] += row["volume"]
    return [buckets[k] for k in order]


def ratio_in_range(value: float, min_v: float, max_v: float, tol: float) -> bool:
    return value >= (min_v - tol) and value <= (max_v + tol)


def get_direction(p_x, p_a, p_b, p_c, p_d):
    bullish = p_a > p_x and p_b < p_a and p_c > p_b and p_d < p_c
    bearish = p_a < p_x and p_b > p_a and p_c < p_b and p_d > p_c
    if bullish:
        return "bull"
    if bearish:
        return "bear"
    return None


def check_one2one(
    p_x,
    p_a,
    p_b,
    p_c,
    p_d,
    ratio_tol_pct=5,
    sym_tol_pct=18,
    cd_max=None,
    ab_min=None,
    ab_max=None,
    cd_min=None,
):
    tol = ratio_tol_pct / 100.0
    xa = abs(p_a - p_x)
    ab = abs(p_b - p_a)
    xc = abs(p_c - p_x)
    cd = abs(p_d - p_c)
    if min(xa, ab, xc, cd) <= 0:
        return None
    ab_ratio = ab / xa
    cd_ratio = cd / xc
    symmetry = abs(ab - cd) / ab
    direction = get_direction(p_x, p_a, p_b, p_c, p_d)
    ab_lo = FIB_AB_MIN if ab_min is None else ab_min
    ab_hi = FIB_AB_MAX if ab_max is None else ab_max
    cd_lo = FIB_CD_MIN if cd_min is None else cd_min
    cd_hi = FIB_CD_MAX if cd_max is None else cd_max
    if not ratio_in_range(ab_ratio, ab_lo, ab_hi, tol):
        return None
    if not ratio_in_range(cd_ratio, cd_lo, cd_hi, tol):
        return None
    if symmetry > (sym_tol_pct / 100.0):
        return None
    if direction is None:
        return None
    return {
        "direction": direction,
        "ab_ratio": ab_ratio,
        "cd_ratio": cd_ratio,
        "symmetry": symmetry,
    }


def calc_levels(p_x, p_c, tp1_ratio=None, stop_ratio=None, p_d=None):
    xc = p_x - p_c
    tp1_r = TP1_RATIO if tp1_ratio is None else tp1_ratio
    stop_r = 1.0 if stop_ratio is None else stop_ratio
    if p_d is None:
        tp1 = p_c + xc * tp1_r
    else:
        tp1 = p_d + (p_c - p_d) * tp1_r
    return {
        "prz50": p_c + xc * 0.5,
        "prz618": p_c + xc * 0.618,
        "stop": p_c + xc * stop_r,
        "tp1": tp1,
        "tp2": p_c,
        "tp3": p_c + xc * TP3_RATIO,
    }


def scan_patterns(
    zz_levels,
    ratio_tol_pct,
    sym_tol_pct,
    history_depth=1,
    cd_max=None,
    ab_min=None,
    ab_max=None,
    cd_min=None,
):
    found = []
    count = len(zz_levels)
    if count < 5:
        return found
    for end_idx in range(count - 1, 3, -1):
        p_x = zz_levels[end_idx - 4]["val"]
        p_a = zz_levels[end_idx - 3]["val"]
        p_b = zz_levels[end_idx - 2]["val"]
        p_c = zz_levels[end_idx - 1]["val"]
        p_d = zz_levels[end_idx]["val"]
        info = check_one2one(
            p_x,
            p_a,
            p_b,
            p_c,
            p_d,
            ratio_tol_pct,
            sym_tol_pct,
            cd_max,
            ab_min=ab_min,
            ab_max=ab_max,
            cd_min=cd_min,
        )
        if info:
            found.append(
                {
                    "info": info,
                    "end_idx": end_idx,
                    "points": {
                        "X": zz_levels[end_idx - 4],
                        "A": zz_levels[end_idx - 3],
                        "B": zz_levels[end_idx - 2],
                        "C": zz_levels[end_idx - 1],
                        "D": zz_levels[end_idx],
                    },
                    "values": {
                        "pX": p_x,
                        "pA": p_a,
                        "pB": p_b,
                        "pC": p_c,
                        "pD": p_d,
                    },
                }
            )
            if len(found) >= history_depth:
                break
    return found


class ZigZagEngine:
    """Bar-by-bar port of one2oneLib.createZZEngine (1-based bars)."""

    def __init__(self, price_step: float):
        self.step = float(price_step) or 1.0
        self.reset()

    def reset(self):
        self.CC = [0.0]
        self.CH = [0.0]
        self.CL = [0.0]
        self.HighMapBuffer = [0.0]
        self.LowMapBuffer = [0.0]
        self.Peak: dict[int, float | None] = {}
        self.ZZLevels: list[dict] = []
        self.lastindex = -1
        self.lastlow = 0.0
        self.lasthigh = 0.0

    def _ensure(self, index: int):
        while len(self.CC) <= index:
            self.CC.append(0.0)
            self.CH.append(0.0)
            self.CL.append(0.0)
            self.HighMapBuffer.append(0.0)
            self.LowMapBuffer.append(0.0)

    def _register_peak(self, index, val, peak_count):
        peak_count += 1
        self.Peak[index] = val
        size = len(self.ZZLevels) + 1
        if peak_count <= 0 and self.ZZLevels:
            self.ZZLevels[len(self.ZZLevels) + peak_count - 1] = {
                "val": val,
                "index": index,
            }
        else:
            if size - 1 < len(self.ZZLevels):
                self.ZZLevels[size - 1] = {"val": val, "index": index}
            else:
                self.ZZLevels.append({"val": val, "index": index})
        return peak_count

    def _replace_last_peak(self, index, val, peak_count):
        self.Peak[index] = val
        size = len(self.ZZLevels)
        if peak_count <= 0 and self.ZZLevels:
            self.ZZLevels[len(self.ZZLevels) + peak_count - 1] = {
                "val": val,
                "index": index,
            }
        elif size > 0:
            self.ZZLevels[size - 1] = {"val": val, "index": index}

    def _get_peak(self, index: int) -> int:
        counter = 0
        for i in range(index, 0, -1):
            if self.Peak.get(i) is not None:
                counter += 1
                if counter == 3:
                    return i
        return -1

    def _slice_min(self, arr, lo, hi):
        return min(arr[lo : hi + 1])

    def _slice_max(self, arr, lo, hi):
        return max(arr[lo : hi + 1])

    def update(
        self,
        index: int,
        depth: int,
        deviation: int,
        backstep: int,
        size: int,
        candle: dict,
    ):
        search_both, search_peak, search_lawn = 0, 1, -1
        self._ensure(index)

        if index == 1:
            self.reset()
            self._ensure(index)
            self.CC[index] = candle["close"]
            self.CH[index] = candle["high"]
            self.CL[index] = candle["low"]
            self.Peak[index] = None
            return self.ZZLevels, False

        self.CC[index] = self.CC[index - 1]
        self.CH[index] = self.CH[index - 1]
        self.CL[index] = self.CL[index - 1]

        if index < depth:
            self.HighMapBuffer[index] = self.HighMapBuffer[index - 1]
            self.LowMapBuffer[index] = self.LowMapBuffer[index - 1]
            self.Peak[index] = None
            return self.ZZLevels, False

        self.CC[index] = candle["close"]
        self.CH[index] = candle["high"]
        self.CL[index] = candle["low"]

        if index < size:
            self.HighMapBuffer[index] = self.HighMapBuffer[index - 1]
            self.LowMapBuffer[index] = self.LowMapBuffer[index - 1]
            self.Peak[index] = None
            return self.ZZLevels, False

        size_of_zz = len(self.ZZLevels)
        search_mode = search_both

        if index == self.lastindex and size_of_zz:
            last_zz = self.ZZLevels[-1]["val"]
            last_zz_i = self.ZZLevels[-1]["index"]
            if self.LowMapBuffer[last_zz_i] != 0:
                search_mode = search_peak
            elif self.HighMapBuffer[last_zz_i] != 0:
                search_mode = search_lawn
            if search_mode == search_peak and self.CL[index] < last_zz:
                self.Peak[last_zz_i] = None
                self.LowMapBuffer[last_zz_i] = 0
                self.LowMapBuffer[index] = self.CL[index]
                self._replace_last_peak(index, self.CL[index], 0)
            elif search_mode == search_lawn and self.CH[index] > last_zz:
                self.Peak[last_zz_i] = None
                self.HighMapBuffer[last_zz_i] = 0
                self.HighMapBuffer[index] = self.CH[index]
                self._replace_last_peak(index, self.CH[index], 0)
        else:
            self.lastindex = index
            self.HighMapBuffer[index] = 0
            self.LowMapBuffer[index] = 0
            self.Peak[index] = None

            start = depth
            last_peak, last_peak_i = 0.0, 0
            peak_i = self._get_peak(index)
            if peak_i == -1:
                last_peak_i, last_peak = 0, 0.0
            else:
                last_peak_i, last_peak = peak_i, self.Peak[peak_i]
                start = peak_i

            search_mode = search_both
            if self.LowMapBuffer[start] != 0:
                search_mode = search_peak
            elif self.HighMapBuffer[start] != 0:
                search_mode = search_lawn

            for i in range(start, index + 1):
                self.Peak[i] = None
                self.LowMapBuffer[i] = 0
                self.HighMapBuffer[i] = 0

            self.lastlow, self.lasthigh = -1.0, -1.0

            for i in range(start, index):
                rng = max(1, i - depth + 1)
                val: float | None = self._slice_min(self.CL, rng, i)
                if val != self.lastlow:
                    self.lastlow = val
                    if (self.CL[i] - val) > (self.step * deviation):
                        val = None
                    else:
                        k = i - 1
                        while k >= i - backstep + 1:
                            if k < 1:
                                break
                            if self.HighMapBuffer[k] != 0:
                                break
                            if self.LowMapBuffer[k] != 0 and self.LowMapBuffer[k] > val:
                                self.LowMapBuffer[k] = 0
                            k -= 1
                else:
                    val = None
                self.LowMapBuffer[i] = val if (val is not None and self.CL[i] == val) else 0

                val = self._slice_max(self.CH, rng, i)
                if val != self.lasthigh:
                    self.lasthigh = val
                    if (val - self.CH[i]) > (self.step * deviation):
                        val = None
                    else:
                        k = i - 1
                        while k >= i - backstep + 1:
                            if k < 1:
                                break
                            if self.LowMapBuffer[k] != 0:
                                break
                            if self.HighMapBuffer[k] != 0 and self.HighMapBuffer[k] < val:
                                self.HighMapBuffer[k] = 0
                            k -= 1
                else:
                    val = None
                self.HighMapBuffer[i] = val if (val is not None and self.CH[i] == val) else 0

            peak_count = -3 if start != depth else 0
            if start != depth:
                search_mode = search_both

            for i in range(start, index):
                if search_mode == search_both:
                    if self.HighMapBuffer[i] != 0:
                        last_peak_i = i
                        last_peak = self.CH[i]
                        search_mode = search_lawn
                        self.LowMapBuffer[i] = 0
                        peak_count = self._register_peak(i, last_peak, peak_count)
                    elif self.LowMapBuffer[i] != 0:
                        last_peak_i = i
                        last_peak = self.CL[i]
                        search_mode = search_peak
                        peak_count = self._register_peak(i, last_peak, peak_count)
                elif search_mode == search_peak:
                    if self.LowMapBuffer[i] != 0 and self.LowMapBuffer[i] < last_peak:
                        self.Peak[last_peak_i] = None
                        last_peak = self.LowMapBuffer[i]
                        last_peak_i = i
                        self._replace_last_peak(i, last_peak, peak_count)
                        self.HighMapBuffer[i] = 0
                    if self.HighMapBuffer[i] != 0 and self.LowMapBuffer[i] == 0:
                        last_peak = self.HighMapBuffer[i]
                        last_peak_i = i
                        search_mode = search_lawn
                        peak_count = self._register_peak(i, last_peak, peak_count)
                elif search_mode == search_lawn:
                    if self.HighMapBuffer[i] != 0 and self.HighMapBuffer[i] > last_peak:
                        self.Peak[last_peak_i] = None
                        last_peak = self.HighMapBuffer[i]
                        last_peak_i = i
                        self._replace_last_peak(i, last_peak, peak_count)
                        self.LowMapBuffer[i] = 0
                    if self.LowMapBuffer[i] != 0 and self.HighMapBuffer[i] == 0:
                        last_peak = self.LowMapBuffer[i]
                        last_peak_i = i
                        search_mode = search_peak
                        peak_count = self._register_peak(i, last_peak, peak_count)

        return self.ZZLevels, True


def evaluate_move(candles, signal_i, direction, stop, tp1, tp2, tp3):
    """Walk from the next bar after the signal. Same-bar TP+stop => stop wins."""
    n = len(candles) - 1
    hit_tp1 = hit_tp2 = hit_tp3 = False
    hit_stop = False
    dir_move = False
    mfe = 0.0
    mae = 0.0
    bars = 0
    start_px = candles[signal_i]["close"]

    for i in range(signal_i + 1, n + 1):
        bars += 1
        hi = candles[i]["high"]
        lo = candles[i]["low"]
        if direction == "bull":
            mfe = max(mfe, hi - start_px)
            mae = max(mae, start_px - lo)
            stop_now = lo <= stop
            t1 = hi >= tp1
            t2 = hi >= tp2
            t3 = hi >= tp3
            if hi > start_px:
                dir_move = True
        else:
            mfe = max(mfe, start_px - lo)
            mae = max(mae, hi - start_px)
            stop_now = hi >= stop
            t1 = lo <= tp1
            t2 = lo <= tp2
            t3 = lo <= tp3
            if lo < start_px:
                dir_move = True

        if stop_now and not (t1 or t2 or t3):
            hit_stop = True
            break
        if stop_now and (t1 or t2 or t3):
            hit_stop = True
            break
        if t1:
            hit_tp1 = True
        if t2:
            hit_tp2 = True
        if t3:
            hit_tp3 = True
            break

    outcome = "open"
    if hit_tp3:
        outcome = "tp3"
    elif hit_tp2:
        outcome = "tp2"
    elif hit_tp1:
        outcome = "tp1"
    elif hit_stop:
        outcome = "stop"
    return {
        "outcome": outcome,
        "dir_move": dir_move,
        "hit_tp1": hit_tp1,
        "hit_tp2": hit_tp2,
        "hit_tp3": hit_tp3,
        "hit_stop": hit_stop,
        "mfe": mfe,
        "mae": mae,
        "bars": bars,
    }


def replay(
    candles: list[dict],
    price_step: float,
    depth: int,
    deviation: int,
    backstep: int,
    ratio_tol: float,
    sym_tol: float,
):
    n = len(candles) - 1
    engine = ZigZagEngine(price_step)
    seen: set[tuple] = set()
    signals = []

    for i in range(1, n + 1):
        zz, ready = engine.update(
            i, depth, deviation, backstep, size=i, candle=candles[i]
        )
        if not ready or len(zz) < 5:
            continue
        patterns = scan_patterns(list(zz), ratio_tol, sym_tol, history_depth=1)
        if not patterns:
            continue
        pat = patterns[0]
        d_pt = pat["points"]["D"]
        key = (pat["info"]["direction"], d_pt["index"])
        if key in seen:
            continue
        if d_pt["index"] > i:
            continue
        seen.add(key)
        lv = calc_levels(pat["values"]["pX"], pat["values"]["pC"], p_d=pat["values"]["pD"])
        ev = evaluate_move(
            candles,
            i,
            pat["info"]["direction"],
            lv["stop"],
            lv["tp1"],
            lv["tp2"],
            lv["tp3"],
        )
        signals.append(
            {
                "signal_i": i,
                "signal_time": candles[i]["begin"],
                "d_time": candles[d_pt["index"]]["begin"],
                "direction": pat["info"]["direction"],
                "ab": pat["info"]["ab_ratio"],
                "cd": pat["info"]["cd_ratio"],
                "sym": pat["info"]["symmetry"],
                "pD": pat["values"]["pD"],
                **lv,
                **ev,
            }
        )
    return signals


def collect_zz_states(candles, price_step, depth, deviation, backstep):
    n = len(candles) - 1
    engine = ZigZagEngine(price_step)
    states = []
    for i in range(1, n + 1):
        zz, ready = engine.update(
            i, depth, deviation, backstep, size=i, candle=candles[i]
        )
        if not ready or len(zz) < 5:
            continue
        states.append(
            (i, [{"val": p["val"], "index": p["index"]} for p in zz[-8:]])
        )
    return states


def signals_from_states(
    states,
    candles,
    ratio_tol,
    sym_tol,
    cd_max=None,
    tp1_ratio=None,
    stop_ratio=None,
    min_rr=0.0,
    ab_min=None,
    ab_max=None,
    cd_min=None,
):
    seen = set()
    signals = []
    for i, zz in states:
        patterns = scan_patterns(
            zz,
            ratio_tol,
            sym_tol,
            1,
            cd_max=cd_max,
            ab_min=ab_min,
            ab_max=ab_max,
            cd_min=cd_min,
        )
        if not patterns:
            continue
        pat = patterns[0]
        d_pt = pat["points"]["D"]
        key = (pat["info"]["direction"], d_pt["index"])
        if key in seen or d_pt["index"] > i:
            continue
        lv = calc_levels(
            pat["values"]["pX"],
            pat["values"]["pC"],
            tp1_ratio,
            stop_ratio,
            p_d=pat["values"]["pD"],
        )
        p_d = pat["values"]["pD"]
        dist_tp1 = abs(lv["tp1"] - p_d)
        dist_stop = abs(lv["stop"] - p_d)
        if dist_tp1 <= 0 or dist_stop / dist_tp1 < min_rr:
            continue
        seen.add(key)
        ev = evaluate_move(
            candles,
            i,
            pat["info"]["direction"],
            lv["stop"],
            lv["tp1"],
            lv["tp2"],
            lv["tp3"],
        )
        signals.append(
            {
                "signal_i": i,
                "direction": pat["info"]["direction"],
                "ab": pat["info"]["ab_ratio"],
                "cd": pat["info"]["cd_ratio"],
                "sym": pat["info"]["symmetry"],
                **ev,
            }
        )
    return signals


def pct(num, den):
    if den <= 0:
        return 0.0
    return 100.0 * num / den


def summarize(signals: list[dict]) -> str:
    n = len(signals)
    if n == 0:
        return "signals=0"
    closed = [s for s in signals if s["outcome"] != "open"]
    nc = len(closed)
    by = Counter(s["outcome"] for s in signals)
    dir_ok = sum(1 for s in signals if s["dir_move"])
    tp1 = sum(1 for s in signals if s["hit_tp1"])
    tp2 = sum(1 for s in signals if s["hit_tp2"])
    tp3 = sum(1 for s in signals if s["hit_tp3"])
    stop_only = sum(1 for s in signals if s["outcome"] == "stop")
    lines = [
        f"signals={n}  closed={nc}  open={by.get('open', 0)}",
        f"move in expected direction: {dir_ok}/{n} = {pct(dir_ok, n):.1f}%",
        f"reached TP1 before stop:    {tp1}/{n} = {pct(tp1, n):.1f}%",
        f"reached TP2 (C) before stop:{tp2}/{n} = {pct(tp2, n):.1f}%",
        f"reached TP3 before stop:    {tp3}/{n} = {pct(tp3, n):.1f}%",
        f"stopped before TP1:         {stop_only}/{n} = {pct(stop_only, n):.1f}%",
        (
            "outcomes: "
            + ", ".join(f"{k}={v}" for k, v in sorted(by.items()))
        ),
    ]
    for side in ("bull", "bear"):
        g = [s for s in signals if s["direction"] == side]
        if not g:
            continue
        d = sum(1 for s in g if s["dir_move"])
        t1 = sum(1 for s in g if s["hit_tp1"])
        t2 = sum(1 for s in g if s["hit_tp2"])
        lines.append(
            f"  {side}: n={len(g)} dir={pct(d, len(g)):.1f}% "
            f"TP1={pct(t1, len(g)):.1f}% TP2={pct(t2, len(g)):.1f}%"
        )
    return "\n".join(lines)


def to_1based(rows: list[dict]) -> list[dict]:
    return [None] + rows  # type: ignore[list-item]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--sec", default="VTBR")
    p.add_argument("--from", dest="date_from", default="2025-09-01")
    p.add_argument("--till", dest="date_till", default="2026-09-11")
    p.add_argument("--tf", type=int, default=5, help="minutes (1,5,10,60)")
    p.add_argument("--depth", type=int, default=12)
    p.add_argument("--deviation", type=int, default=5)
    p.add_argument("--backstep", type=int, default=3)
    p.add_argument("--ratio-tol", type=float, default=0)
    p.add_argument("--sym-tol", type=float, default=999)
    p.add_argument("--step", type=float, default=0.005)
    p.add_argument("--market", default="shares", help="shares or index")
    p.add_argument("--board", default="TQBR")
    return p.parse_args()


def main():
    args = parse_args()
    native = args.tf if args.tf in (1, 10, 60) else 1
    print(
        f"fetch {args.sec} market={args.market} interval={native} "
        f"{args.date_from}..{args.date_till}"
    )
    raw = fetch_moex_candles(
        args.sec,
        native,
        args.date_from,
        args.date_till,
        board=args.board,
        market=args.market,
    )
    print(f"raw candles={len(raw)}")
    rows = resample_ohlc(raw, args.tf) if args.tf not in (1, 10, 60) else raw
    print(f"tf={args.tf}m bars={len(rows)}")
    candles = to_1based(rows)
    signals = replay(
        candles,
        args.step,
        args.depth,
        args.deviation,
        args.backstep,
        args.ratio_tol,
        args.sym_tol,
    )
    print(summarize(signals))
    out = {
        "sec": args.sec,
        "tf": args.tf,
        "from": args.date_from,
        "till": args.date_till,
        "params": {
            "depth": args.depth,
            "deviation": args.deviation,
            "backstep": args.backstep,
            "ratio_tol": args.ratio_tol,
            "sym_tol": args.sym_tol,
        },
        "summary": summarize(signals),
        "signals": signals,
    }
    out_path = str(
        Path(__file__).resolve().parent / f"move_stats_{args.sec}_{args.tf}m.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
