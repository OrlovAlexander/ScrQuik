# -*- coding: utf-8 -*-
"""Senior TF bars from M1: closed slots frozen at close, forming OHLC at each minute.

CSV of M10/M30/H4/D1 is only an OHLC check at slot close, not the working series.
RPM current/up for a forming bar uses cached EMA/FIR state after the last close.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from analyzer.bars import Bar
from analyzer.combo import PERIOD_MIN
from analyzer.ema import Ema
from analyzer.odds import (
    _cur_nums,
    _layer_nums,
    _scale_map,
    aggregate_m1,
    slot_open,
)
from analyzer.rpm_current import CURRENT_PERIOD, fir_typical, half_history_start
from analyzer.rpm_up import AggBar, AggSeries, LayerRuntime, _step_layer
from analyzer.settings import hist_layer_names, load_up_settings


def _chunk_bar(chunk: list[Bar], slot: datetime) -> Bar:
    return Bar(
        dt=slot,
        o=chunk[0].o,
        h=max(b.h for b in chunk),
        l=min(b.l for b in chunk),
        c=chunk[-1].c,
    )


def slot_complete(last_dt: datetime, slot: datetime, period_min: int) -> bool:
    """True if last_dt is the last minute of the slot (or past it)."""
    return last_dt + timedelta(minutes=1) >= slot + timedelta(minutes=period_min)


def closed_bars_from_m1(m1: list[Bar], period_min: int) -> list[Bar]:
    """Complete slots only. Incomplete last slot is omitted."""
    if period_min <= 1:
        return list(m1)
    out: list[Bar] = []
    cur_slot: datetime | None = None
    chunk: list[Bar] = []
    for bar in m1:
        slot = slot_open(bar.dt, period_min)
        if cur_slot is not None and slot != cur_slot:
            out.append(_chunk_bar(chunk, cur_slot))
            chunk = [bar]
            cur_slot = slot
        elif cur_slot is None:
            cur_slot = slot
            chunk = [bar]
        else:
            chunk.append(bar)
    if cur_slot is not None and chunk and slot_complete(chunk[-1].dt, cur_slot, period_min):
        out.append(_chunk_bar(chunk, cur_slot))
    return out


def forming_bar(m1: list[Bar], tf: str, clock: datetime) -> Bar | None:
    period = PERIOD_MIN.get(tf)
    if not period or not m1:
        return None
    slot = slot_open(clock, period)
    end = min(slot + timedelta(minutes=period), clock + timedelta(minutes=1))
    return aggregate_m1(m1, slot, end)


def verify_closed_csv(
    closed: list[Bar],
    csv: list[Bar],
    period_min: int,
    *,
    tol: float = 1e-4,
) -> dict[str, int]:
    """OHLC check of M1-built closed slots against senior CSV. Not a working series."""
    by_slot = {slot_open(bar.dt, period_min): bar for bar in csv}
    mismatch = 0
    missing = 0
    checked = 0
    for bar in closed:
        other = by_slot.get(bar.dt)
        if other is None:
            missing += 1
            continue
        checked += 1
        if (
            abs(bar.o - other.o) > tol
            or abs(bar.h - other.h) > tol
            or abs(bar.l - other.l) > tol
            or abs(bar.c - other.c) > tol
        ):
            mismatch += 1
    return {"checked": checked, "mismatch": mismatch, "missing": missing}


def _snap_layer(layer: LayerRuntime) -> dict:
    return {
        "bars": [AggBar(b.o, b.h, b.l, b.c, b.t) for b in layer.agg.bars],
        "ema_fast": layer.ema_fast,
        "ema_slow": layer.ema_slow,
        "ema_fast_prev": layer.ema_fast.prev if layer.ema_fast else None,
        "ema_slow_prev": layer.ema_slow.prev if layer.ema_slow else None,
        "hist_prev": layer.hist_prev,
        "rpm_at": dict(layer.rpm_at),
        "cur": layer.cur,
        "confirmed": list(layer.confirmed),
    }


def _restore_layer(layer: LayerRuntime, snap: dict) -> None:
    layer.agg.bars = snap["bars"]
    layer.ema_fast = snap["ema_fast"]
    layer.ema_slow = snap["ema_slow"]
    if layer.ema_fast is not None:
        layer.ema_fast.prev = snap["ema_fast_prev"]
    if layer.ema_slow is not None:
        layer.ema_slow.prev = snap["ema_slow_prev"]
    layer.hist_prev = snap["hist_prev"]
    layer.rpm_at = snap["rpm_at"]
    layer.cur = snap["cur"]
    layer.confirmed = snap["confirmed"]


def _current_at_last(bars: list[Bar], ema: Ema) -> dict:
    i = len(bars) - 1
    bar = bars[i]
    start = half_history_start(len(bars))
    if i == 0 or i < start:
        return {"dt": bar.dt, "rpm": None, "ema": None}
    rpm = fir_typical(bars, i)
    return {"dt": bar.dt, "rpm": rpm, "ema": ema.update(rpm)}


class TfStepper:
    """Incremental RPM on closed TF bars; peek forming last bar without committing."""

    def __init__(self, tf: str) -> None:
        self.tf = tf
        self.up_set = load_up_settings(tf)
        hist_names = hist_layer_names(self.up_set)
        self.hist_name = hist_names[0] if hist_names else "up"
        self.closed_bars: list[Bar] = []
        self.closed_packs: list[dict] = []
        self.cur_ema = Ema(CURRENT_PERIOD)
        self.small = LayerRuntime(self.up_set.small, AggSeries(self.up_set.small.tf))
        self.middle = LayerRuntime(self.up_set.middle, AggSeries(self.up_set.middle.tf))
        self.up = LayerRuntime(self.up_set.up, AggSeries(self.up_set.up.tf))
        self.prev_cur: dict | None = None
        self.prev_small: dict | None = None
        self.prev_middle: dict | None = None
        self.prev_hist: dict | None = None

    def peek(self, bar: Bar) -> dict:
        return self._pack_bar(bar, commit=False)

    def commit(self, bar: Bar) -> dict:
        pack = self._pack_bar(bar, commit=True)
        self.closed_bars.append(bar)
        self.closed_packs.append(pack)
        return pack

    def _pack_bar(self, bar: Bar, *, commit: bool) -> dict:
        n = len(self.closed_bars) + 1
        lua_i = n
        if commit:
            cur = _current_at_last(self.closed_bars + [bar], self.cur_ema)
            last_s, last_m, last_u = self._up_step(bar, n, lua_i, commit=True)
        else:
            ema = Ema(CURRENT_PERIOD)
            ema.prev = self.cur_ema.prev
            cur = _current_at_last(self.closed_bars + [bar], ema)
            last_s, last_m, last_u = self._up_step(bar, n, lua_i, commit=False)
        hist = {"small": last_s, "middle": last_m, "up": last_u}.get(self.hist_name) or last_u
        c_nums = _cur_nums(cur, self.prev_cur)
        s_nums = _layer_nums(last_s, self.prev_small)
        m_nums = _layer_nums(last_m, self.prev_middle)
        h_nums = _layer_nums(hist, self.prev_hist)
        if commit:
            if c_nums.get("rpm") is not None:
                self.prev_cur = cur
            if s_nums.get("rpm") is not None:
                self.prev_small = last_s
            if m_nums.get("rpm") is not None:
                self.prev_middle = last_m
            if h_nums.get("hist") is not None:
                self.prev_hist = hist
        return {
            "dt": bar.dt,
            "o": bar.o,
            "h": bar.h,
            "l": bar.l,
            "c": bar.c,
            "current": c_nums,
            "small": s_nums,
            "middle": m_nums,
            "hist": h_nums,
            "hist_raw": hist,
        }

    def _up_step(
        self, bar: Bar, n: int, lua_i: int, *, commit: bool
    ) -> tuple[dict, dict, dict]:
        half = n // 2 + 1
        snaps = None if commit else (
            _snap_layer(self.small),
            _snap_layer(self.middle),
            _snap_layer(self.up),
        )
        if lua_i == 1 and commit:
            self.small.reset()
            self.middle.reset()
            self.up.reset()
        try:
            last_s = _step_layer(self.small, lua_i, bar, half, n, self.up_set, False)
            last_m = _step_layer(self.middle, lua_i, bar, half, n, self.up_set, False)
            last_u = _step_layer(self.up, lua_i, bar, half, n, self.up_set, False)
            return last_s, last_m, last_u
        finally:
            if snaps is not None:
                _restore_layer(self.small, snaps[0])
                _restore_layer(self.middle, snaps[1])
                _restore_layer(self.up, snaps[2])


def _scales_from_packs(packs: list[dict]) -> dict[str, float]:
    rows = [p for p in packs if p]
    scales: dict[str, float] = {}
    scales.update(_scale_map([p["current"] for p in rows], "current"))
    scales.update(_scale_map([p["small"] for p in rows], "small"))
    scales.update(_scale_map([p["middle"] for p in rows], "middle"))
    scales.update(_scale_map([p["hist"] for p in rows], "hist"))
    return scales


def replay_tf_book(
    m1: list[Bar],
    tf: str,
    csv: list[Bar] | None = None,
) -> dict | None:
    """Packs of `tf` at every M1: forming OHLC to t, neighbors = frozen closed slots."""
    period = PERIOD_MIN.get(tf)
    if not period or not m1:
        return None
    if tf == "M1":
        from analyzer.odds import tf_numeric

        return tf_numeric(m1, "M1")
    stepper = TfStepper(tf)
    n = len(m1)
    m1_slot: list[int | None] = [None] * n
    m1_packs: list[dict | None] = [None] * n
    m1_bars: list[Bar | None] = [None] * n
    cur_slot: datetime | None = None
    chunk: list[Bar] = []
    pending: list[int] = []

    def flush_closed() -> None:
        if cur_slot is None or not chunk:
            return
        stepper.commit(_chunk_bar(chunk, cur_slot))

    for i, bar in enumerate(m1):
        slot = slot_open(bar.dt, period)
        if cur_slot is not None and slot != cur_slot:
            flush_closed()
            chunk = [bar]
            pending = [i]
            cur_slot = slot
        elif cur_slot is None:
            cur_slot = slot
            chunk = [bar]
            pending = [i]
        else:
            chunk.append(bar)
            pending.append(i)
        forming = _chunk_bar(chunk, cur_slot)
        pack = stepper.peek(forming)
        m1_slot[i] = len(stepper.closed_bars)
        m1_packs[i] = pack
        m1_bars[i] = forming

    if cur_slot is not None and chunk and slot_complete(chunk[-1].dt, cur_slot, period):
        flush_closed()

    scale_src = stepper.closed_packs or [p for p in m1_packs if p]
    scales = _scales_from_packs(scale_src)
    csv_check = verify_closed_csv(stepper.closed_bars, csv or [], period) if csv else None
    return {
        "tf": tf,
        "bars": stepper.closed_bars,
        "packs": stepper.closed_packs,
        "scales": scales,
        "hist_name": stepper.hist_name,
        "m1_slot": m1_slot,
        "m1_packs": m1_packs,
        "m1_bars": m1_bars,
        "csv_check": csv_check,
        "from_m1": True,
    }
