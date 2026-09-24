# -*- coding: utf-8 -*-
"""RPM-TF-Up: aggregate higher TF, FIR transform, dual EMA, histogram, divergences."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import floor

from analyzer.bars import Bar
from analyzer.ema import Ema
from analyzer.settings import LayerSettings, UpSettings

HOUR_SLOT = {"H1": 1, "H2": 2, "H3": 3, "H4": 4, "H6": 6, "H8": 8, "H12": 12}
DIV_EXTENDED_PCT = 0.003
DIV_WEAK_RPM_PCT = 0.015
DIV_WEAK_PRICE_PCT = 0.005
DIV_SLOTS = 4
FIR_W = (1.6, 1.6, 1.4, 1.4, 0.5, 0.5, -1.5, -1.5, -1.0, -1.0, -1.0, -1.0)


@dataclass
class AggBar:
    o: float
    h: float
    l: float
    c: float
    t: datetime


@dataclass
class Seg:
    seg_id: int
    start_index: int
    end_index: int
    rpm_max: float
    rpm_max_idx: int
    rpm_min: float
    rpm_min_idx: int
    price_max: float
    price_max_idx: int
    price_min: float
    price_min_idx: int


@dataclass
class DivEntry:
    kind: str
    pivot_span: int
    idx1: int
    idx2: int
    rpm1: float
    rpm2: float
    price1: float
    price2: float


def _is_hour_tf(tf: str) -> bool:
    return tf in HOUR_SLOT


def _is_minute_tf(tf: str) -> bool:
    return tf.startswith("Mn")


def _uses_half(tf: str) -> bool:
    return _is_minute_tf(tf) or _is_hour_tf(tf)


def _mn_mod(tf: str) -> int | None:
    if not tf.startswith("Mn"):
        return None
    return int(tf[2:])


def _clean(dt: datetime, tf: str) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    if _is_hour_tf(tf):
        dt = dt.replace(minute=0)
    return dt


def _hour_slot(hour: int, tf: str) -> int | None:
    n = HOUR_SLOT.get(tf)
    if n is None:
        return None
    if n == 1:
        return hour
    return hour // n


def _is_hour_boundary(dt: datetime, tf: str) -> bool:
    if dt.minute != 0:
        return False
    n = HOUR_SLOT.get(tf)
    if n is None:
        return False
    if n == 1:
        return True
    return dt.hour % n == 0


def _is_new_hourly(tf: str, up_t: datetime, cr_t: datetime) -> bool:
    if tf not in HOUR_SLOT:
        return False
    if (up_t.year, up_t.month, up_t.day) != (cr_t.year, cr_t.month, cr_t.day):
        return True
    return _hour_slot(up_t.hour, tf) != _hour_slot(cr_t.hour, tf)


def _first_bar_ok(tf: str, cr: datetime) -> bool:
    mod = _mn_mod(tf)
    if mod is not None:
        return cr.minute % mod == 0
    if _is_hour_tf(tf):
        return _is_hour_boundary(cr, tf)
    if tf in {"D1", "W1", "M1"}:
        return True
    return False


def _should_add(tf: str, up_t: datetime, cr_t: datetime) -> bool:
    new_hour = up_t.hour != cr_t.hour
    new_day = up_t.day != cr_t.day
    new_month = up_t.month != cr_t.month
    if tf == "M1" and new_month:
        return True
    if tf == "W1" and cr_t.weekday() == 0 and new_day:
        return True
    if tf == "D1" and new_day:
        return True
    if _is_new_hourly(tf, up_t, cr_t):
        return True
    mod = _mn_mod(tf)
    if mod is not None and (new_hour or cr_t.minute % mod == 0):
        return (up_t + timedelta(minutes=1)) < cr_t
    return False


class AggSeries:
    def __init__(self, tf: str) -> None:
        self.tf = tf
        self.bars: list[AggBar] = []

    def clear(self) -> None:
        self.bars.clear()

    def set_price(self, bar: Bar) -> None:
        cr = _clean(bar.dt, self.tf)
        if not self.bars:
            if _first_bar_ok(self.tf, cr):
                self.bars.append(AggBar(bar.o, bar.h, bar.l, bar.c, cr))
            return
        last = self.bars[-1]
        up = _clean(last.t, self.tf)
        if cr < up:
            self.bars.append(AggBar(bar.o, bar.h, bar.l, bar.c, cr))
            return
        if _should_add(self.tf, up, cr):
            self.bars.append(AggBar(bar.o, bar.h, bar.l, bar.c, cr))
            return
        last.h = max(last.h, bar.h)
        last.l = min(last.l, bar.l)
        last.c = bar.c


def _rpm_value(bars: list[AggBar], index: int) -> float:
    if index < 1:
        return 0.0
    row = bars[index - 1]
    return (row.c * 2.0 + row.l + row.h) / 4.0


def rpm_up_transform(n: int, bars: list[AggBar]) -> float:
    acc = 0.0
    for k, w in enumerate(FIR_W):
        acc += _rpm_value(bars, n - k) * w
    return acc / 12.0


def _rel(v1: float, v2: float) -> float | None:
    if v1 == 0:
        return None
    return abs(v2 - v1) / abs(v1)


def _rpm_between(series: dict[int, float], idx1: int, idx2: int) -> tuple[int, int]:
    lo, hi = (idx1, idx2) if idx1 <= idx2 else (idx2, idx1)
    below = above = 0
    for i in range(lo, hi + 1):
        v = series.get(i)
        if v is None:
            continue
        if v < 0:
            below += 1
        elif v > 0:
            above += 1
    return below, above


def _pivot_high(segs: list[Seg], i: int, period: int) -> bool:
    if i < period or i > len(segs) - 1 - period:
        return False
    v = segs[i].rpm_max
    if v <= 0:
        return False
    for j in range(i - period, i + period + 1):
        if j != i and segs[j].rpm_max > 0 and segs[j].rpm_max >= v:
            return False
    return True


def _pivot_low(segs: list[Seg], i: int, period: int) -> bool:
    if i < period or i > len(segs) - 1 - period:
        return False
    v = segs[i].rpm_min
    if v >= 0:
        return False
    for j in range(i - period, i + period + 1):
        if j != i and segs[j].rpm_min < 0 and segs[j].rpm_min <= v:
            return False
    return True


def _kind_high(p1, p2, r1, r2, hidden: bool, weak: bool) -> str | None:
    if p2 < p1 and r2 > r1:
        return "hidden_bear" if hidden else None
    if (_rel(p1, p2) or 1) <= DIV_EXTENDED_PCT and r2 < r1:
        return "extended_bear"
    if p2 > p1 and r2 < r1 and not ((_rel(r1, r2) or 1) <= DIV_WEAK_RPM_PCT):
        return "bear"
    if (
        p2 > p1
        and (_rel(p1, p2) or 0) >= DIV_WEAK_PRICE_PCT
        and (_rel(r1, r2) or 1) <= DIV_WEAK_RPM_PCT
        and (_rel(p1, p2) or 1) > DIV_EXTENDED_PCT
        and weak
    ):
        return "weak_bear"
    return None


def _kind_low(p1, p2, r1, r2, hidden: bool, weak: bool) -> str | None:
    if p2 > p1 and r2 < r1:
        return "hidden_bull" if hidden else None
    if (_rel(p1, p2) or 1) <= DIV_EXTENDED_PCT and r2 > r1:
        return "extended_bull"
    if p2 < p1 and r2 > r1 and not ((_rel(r1, r2) or 1) <= DIV_WEAK_RPM_PCT):
        return "bull"
    if (
        p2 < p1
        and (_rel(p1, p2) or 0) >= DIV_WEAK_PRICE_PCT
        and (_rel(r1, r2) or 1) <= DIV_WEAK_RPM_PCT
        and (_rel(p1, p2) or 1) > DIV_EXTENDED_PCT
        and weak
    ):
        return "weak_bull"
    return None


def _should_draw(kind: str, hidden: bool, weak: bool) -> bool:
    if kind in {"hidden_bear", "hidden_bull"}:
        return hidden
    if kind in {"weak_bear", "weak_bull"}:
        return weak
    return True


def scan_divs(
    segs: list[Seg],
    rpm_series: dict[int, float],
    period: int,
    span_max: int,
    hidden: bool,
    weak: bool,
) -> list[DivEntry]:
    if len(segs) < 2 + period * 2:
        return []
    highs = [i for i in range(period, len(segs) - period) if _pivot_high(segs, i, period)]
    lows = [i for i in range(period, len(segs) - period) if _pivot_low(segs, i, period)]
    cands: list[DivEntry] = []
    span_max = max(1, min(3, span_max))
    for span in range(1, span_max + 1):
        for k in range(span, len(highs)):
            s1, s2 = segs[highs[k - span]], segs[highs[k]]
            below, _ = _rpm_between(rpm_series, s1.rpm_max_idx, s2.rpm_max_idx)
            if below == 0:
                continue
            kind = _kind_high(s1.price_max, s2.price_max, s1.rpm_max, s2.rpm_max, hidden, weak)
            if kind and _should_draw(kind, hidden, weak):
                cands.append(
                    DivEntry(kind, span, s1.rpm_max_idx, s2.rpm_max_idx, s1.rpm_max, s2.rpm_max, s1.price_max, s2.price_max)
                )
        for k in range(span, len(lows)):
            s1, s2 = segs[lows[k - span]], segs[lows[k]]
            _, above = _rpm_between(rpm_series, s1.rpm_min_idx, s2.rpm_min_idx)
            if above == 0:
                continue
            kind = _kind_low(s1.price_min, s2.price_min, s1.rpm_min, s2.rpm_min, hidden, weak)
            if kind and _should_draw(kind, hidden, weak):
                cands.append(
                    DivEntry(kind, span, s1.rpm_min_idx, s2.rpm_min_idx, s1.rpm_min, s2.rpm_min, s1.price_min, s2.price_min)
                )
    cands.sort(key=lambda d: (d.idx2, d.idx1), reverse=True)
    uniq: list[DivEntry] = []
    seen: set[tuple] = set()
    for d in cands:
        key = (d.kind, d.idx1, d.idx2)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
        if len(uniq) >= DIV_SLOTS:
            break
    return uniq


@dataclass
class LayerRuntime:
    settings: LayerSettings
    agg: AggSeries
    ema_fast: Ema | None = None
    ema_slow: Ema | None = None
    cur: Seg | None = None
    confirmed: list[Seg] = field(default_factory=list)
    rpm_at: dict[int, float] = field(default_factory=dict)
    hist_prev: float | None = None

    def reset(self) -> None:
        self.agg.clear()
        self.ema_fast = None
        self.ema_slow = None
        self.cur = None
        self.confirmed = []
        self.hist_prev = None


def _track(layer: LayerRuntime, index: int, seg_id: int, rpm_val: float, hi: float, lo: float, segs_max: int) -> None:
    if layer.cur is None:
        layer.cur = Seg(seg_id, index, index, rpm_val, index, rpm_val, index, hi, index, lo, index)
        return
    if seg_id != layer.cur.seg_id:
        cur = layer.cur
        cur.end_index = index - 1
        layer.confirmed.append(cur)
        if segs_max > 0:
            while len(layer.confirmed) > segs_max:
                layer.confirmed.pop(0)
        layer.cur = Seg(seg_id, index, index, rpm_val, index, rpm_val, index, hi, index, lo, index)
        return
    cur = layer.cur
    cur.end_index = index
    if rpm_val > cur.rpm_max:
        cur.rpm_max, cur.rpm_max_idx = rpm_val, index
    if rpm_val < cur.rpm_min:
        cur.rpm_min, cur.rpm_min_idx = rpm_val, index
    if hi > cur.price_max:
        cur.price_max, cur.price_max_idx = hi, index
    if lo < cur.price_min:
        cur.price_min, cur.price_min_idx = lo, index


def _step_layer(
    layer: LayerRuntime,
    lua_index: int,
    bar: Bar,
    half_start: int,
    size: int,
    div_cfg: UpSettings,
    track_divs: bool = True,
) -> dict:
    st = layer.settings
    empty = {
        "rpm": None,
        "ema": None,
        "hist_up": None,
        "hist_dw": None,
        "agg_n": len(layer.agg.bars),
        "tf": st.tf,
    }
    if not st.enabled():
        return empty
    if _uses_half(st.tf) and lua_index == half_start:
        layer.reset()
        layer.rpm_at.clear()
    if _uses_half(st.tf) and lua_index < half_start:
        return empty
    layer.agg.set_price(bar)
    n = len(layer.agg.bars)
    if n == 1 and layer.ema_fast is None:
        layer.ema_fast = Ema(st.period)
        layer.ema_slow = Ema(st.period_slow)
        return {**empty, "agg_n": n}
    if layer.ema_fast is None or n <= 12:
        return {**empty, "agg_n": n}
    rpm = rpm_up_transform(n, layer.agg.bars)
    layer.rpm_at[lua_index] = rpm
    ema_v = layer.ema_fast.update(rpm)
    slow_v = layer.ema_slow.update(rpm) if layer.ema_slow else 0.0
    hist = (ema_v - slow_v) * 5.0
    hist_up = hist_dw = None
    if layer.hist_prev is not None:
        if hist > layer.hist_prev:
            hist_up = hist
        else:
            hist_dw = hist
    layer.hist_prev = hist
    if track_divs and (st.div_draw == 1 or st.label_draw == 1):
        _track(layer, lua_index, n, rpm, bar.h, bar.l, div_cfg.div_segs_max)
    return {
        "rpm": rpm,
        "ema": ema_v,
        "hist_up": hist_up,
        "hist_dw": hist_dw,
        "agg_n": n,
        "tf": st.tf,
        "hist": hist,
    }


def compute_up(bars: list[Bar], settings: UpSettings, track_divs: bool = True) -> dict:
    size = len(bars)
    half_start = floor(size / 2) + 1
    small = LayerRuntime(settings.small, AggSeries(settings.small.tf))
    middle = LayerRuntime(settings.middle, AggSeries(settings.middle.tf))
    up = LayerRuntime(settings.up, AggSeries(settings.up.tf))
    series = []
    last_s = last_m = last_u = {}
    for i, bar in enumerate(bars):
        lua_i = i + 1
        if lua_i == 1:
            small.reset()
            middle.reset()
            up.reset()
        last_s = _step_layer(small, lua_i, bar, half_start, size, settings, track_divs)
        last_m = _step_layer(middle, lua_i, bar, half_start, size, settings, track_divs)
        last_u = _step_layer(up, lua_i, bar, half_start, size, settings, track_divs)
        series.append({"dt": bar.dt, "small": last_s, "middle": last_m, "up": last_u})

    def _divs(layer: LayerRuntime) -> list[dict]:
        if layer.settings.div_draw != 1:
            return []
        found = scan_divs(
            layer.confirmed,
            layer.rpm_at,
            settings.div_seg_period,
            settings.div_pivot_span_max,
            settings.div_draw_hidden == 1,
            settings.div_draw_weak == 1,
        )
        return [
            {
                "kind": d.kind,
                "span": d.pivot_span,
                "idx1": d.idx1,
                "idx2": d.idx2,
                "rpm1": d.rpm1,
                "rpm2": d.rpm2,
                "price1": d.price1,
                "price2": d.price2,
                "dt1": bars[d.idx1 - 1].dt.isoformat(sep=" ") if 1 <= d.idx1 <= len(bars) else None,
                "dt2": bars[d.idx2 - 1].dt.isoformat(sep=" ") if 1 <= d.idx2 <= len(bars) else None,
            }
            for d in found
        ]

    return {
        "series": series,
        "divs": {
            "small": _divs(small),
            "middle": _divs(middle),
            "up": _divs(up),
        },
        "layers": {
            "small": settings.small.tf,
            "middle": settings.middle.tf,
            "up": settings.up.tf,
        },
    }
