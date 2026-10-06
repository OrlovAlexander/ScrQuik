# -*- coding: utf-8 -*-
"""Odds overlay evolved into --net / *AnalyzerNet. Do not extend --odds.

Lead TF down to M1 (not pair bundles). Pair bundles are связкаМ1М10 /
связкаМ5М10 / связкаМ10М20, chain window 5. Shared helpers (forming
bars from M1, tf_numeric) are used by net and pack-ahead.

Live кадр (archive): forming bars from the leading TF down to M1 (plus D1).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

from analyzer.bars import BARS_DIR, Bar, load_instrument, list_instruments
from analyzer.combo import PERIOD_MIN
from analyzer.marks import mark_sec_names, watch_marks
from analyzer.neighbors import last_closed_indices
from analyzer.rpm_current import compute_current
from analyzer.rpm_up import compute_up
from analyzer.settings import hist_layer_names, load_up_settings
from analyzer.states import (
    NEAR_EMA,
    NEAR_HIST,
    NEAR_ZERO,
    _ema_state,
    _hist_dir,
    _median_abs,
    _side,
    _slope_only,
    _slope_tag,
    _vs_ema,
)

ODDS_DEAD_END = True  # overlay superseded by --net; keep helpers
ODDS_LEAD_TFS = ("M10", "M30", "H4")
# Pair bundles for pattern search and shares (not the --odds overlay frame).
# Tuple is (senior, junior); name is junior then senior.
BUNDLE_PAIRS = (("M10", "M1"), ("M10", "M5"), ("M20", "M10"))
BUNDLE_NAMES = {
    ("M10", "M1"): "связкаМ1М10",
    ("M10", "M5"): "связкаМ5М10",
    ("M20", "M10"): "связкаМ10М20",
}
# Overlay CSV still keyed by chart TF. Pattern object is BUNDLE_PAIRS.
ODDS_FRAME_TFS = {
    "M10": ("M10", "M1", "D1"),
    "M30": ("M30", "M10", "M1", "D1"),
    "H4": ("H4", "M30", "M10", "M1", "D1"),
}
ODDS_WATCH_TFS = ("M1", "M10", "M30", "H4")
ODDS_MAX_BARS = {"M1": 6000, "M10": 2000, "M30": 2000, "H4": 2000, "D1": 800}
ODDS_DIR = Path(r"C:\QuikFinam\LuaIndicators\analyzer_odds")
DT_FMT = "%d.%m.%Y %H:%M:%S"
SIM_MIN = 0.60
CHAIN_WINDOW = {"M1": 5, "M5": 5, "M10": 5, "M20": 5, "M30": 5, "H4": 5, "D1": 5}
CHAIN_BARS = 5
FLAT_PCT = 0.3
FLAT_FRAC = 0.25
MIN_PACK_TAGS = 5
MIN_SAMPLE = 1
LAPLACE = 1.0
LINE_ALPHA = 0.25
ODDS_PAINT = 400
_WRITE_TRIES = 6
_WRITE_WAIT = 0.12

_NUM_KEYS = ("rpm", "ema", "hist", "d_rpm", "d_ema", "d_hist")
_MAG_KEYS = ("d_rpm", "d_ema", "d_hist")
_PARENT = {"d_rpm": "rpm", "d_ema": "ema", "d_hist": "hist"}
_POS_PAIRS = (
    ("small", "rpm", "small", "ema"),
    ("middle", "rpm", "middle", "ema"),
    ("small", "rpm", "middle", "rpm"),
    ("small", "ema", "middle", "ema"),
    ("small", "rpm", "middle", "ema"),
    ("middle", "rpm", "small", "ema"),
)
_ZERO_RANK = {"below_0": -1.0, "near_0": 0.0, "above_0": 1.0}
_EMA_RANK = {"below_ema": -1.0, "near_ema": 0.0, "above_ema": 1.0}
_DIR_Z = {"rising": 1.0, "flat": 0.0, "falling": -1.0}


def format_odds_dt(dt: datetime) -> str:
    return dt.strftime(DT_FMT)


def sim_field(z_hist: float, z_live: float) -> float:
    return 1.0 - abs(z_hist - z_live) / max(abs(z_hist), abs(z_live), 1.0)


def clip_line(pct: float) -> float:
    return min(100.0, max(0.0, float(pct)))


def median_move_pct(closes: list[float]) -> float:
    xs = []
    for a, b in zip(closes, closes[1:]):
        if a > 0:
            xs.append(abs(b - a) / a * 100.0)
    if not xs:
        return 0.0
    m = float(median(xs))
    return m if m > 0 else 0.0


def flat_threshold(closes: list[float]) -> float:
    """Flat = small vs this TF's typical close-to-close, not a fixed 0.3%."""
    typical = median_move_pct(closes)
    if typical > 0:
        return typical * FLAT_FRAC
    return FLAT_PCT


def classify_outcome(close_now: float, close_next: float, flat_pct: float = FLAT_PCT) -> str:
    if close_now <= 0:
        return "flat"
    move = (close_next - close_now) / close_now * 100.0
    if abs(move) < flat_pct:
        return "flat"
    return "up" if move > 0 else "down"


def forming_d1(d1: list[Bar], fillers: list[Bar]) -> list[Bar]:
    """Closed D1 plus today's unfinished daily bar from M1/M10 (or H4) OHLC."""
    out = list(d1)
    if not fillers:
        return out
    today = fillers[-1].dt.date()
    day = [b for b in fillers if b.dt.date() == today]
    if not day:
        return out
    syn = Bar(
        dt=datetime(today.year, today.month, today.day),
        o=day[0].o,
        h=max(b.h for b in day),
        l=min(b.l for b in day),
        c=day[-1].c,
    )
    if out and out[-1].dt.date() == today:
        out[-1] = syn
        return out
    if out and out[-1].dt.date() > today:
        return out
    out.append(syn)
    return out


def slot_open(dt: datetime, period_min: int) -> datetime:
    """Open of the TF slot that contains dt (midnight-aligned, as barsSaver H4)."""
    if period_min >= 1440:
        return datetime(dt.year, dt.month, dt.day)
    minutes = dt.hour * 60 + dt.minute
    floored = (minutes // period_min) * period_min
    return datetime(dt.year, dt.month, dt.day, floored // 60, floored % 60)


def aggregate_m1(m1: list[Bar], start: datetime, end: datetime) -> Bar | None:
    chunk = [b for b in m1 if start <= b.dt < end]
    if not chunk:
        return None
    return Bar(
        dt=start,
        o=chunk[0].o,
        h=max(b.h for b in chunk),
        l=min(b.l for b in chunk),
        c=chunk[-1].c,
    )


def append_forming(bars: list[Bar], tf: str, m1: list[Bar], clock: datetime) -> list[Bar]:
    """Append today's unfinished bar of tf, built from M1 inside the current slot."""
    out = list(bars)
    period = PERIOD_MIN.get(tf)
    if not period or not m1 or tf == "M1":
        return out
    slot = slot_open(clock, period)
    end = slot + timedelta(minutes=period)
    syn = aggregate_m1(m1, slot, min(end, clock + timedelta(minutes=1)))
    if syn is None:
        return out
    if out and out[-1].dt == slot:
        out[-1] = syn
        return out
    if out and out[-1].dt > slot:
        return out
    out.append(syn)
    return out


def series_clock(raw: dict[str, list[Bar]]) -> datetime | None:
    m1 = raw.get("M1") or []
    if m1:
        return m1[-1].dt
    times = [bars[-1].dt for bars in raw.values() if bars]
    return max(times) if times else None


def at_or_before_indices(event_times: list[datetime], src_times: list[datetime]) -> list[int | None]:
    """Last src bar with dt <= event; may be the last (forming) bar."""
    j = -1
    n = len(src_times)
    out: list[int | None] = []
    for t in event_times:
        while j + 1 < n and src_times[j + 1] <= t:
            j += 1
        out.append(j if j >= 0 else None)
    return out


def _delta(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None:
        return None
    return cur - prev


def _layer_nums(chunk: dict, prev: dict | None) -> dict[str, float | None]:
    prev = prev or {}
    rpm = chunk.get("rpm")
    ema = chunk.get("ema")
    hist = chunk.get("hist")
    return {
        "rpm": rpm,
        "ema": ema,
        "hist": hist,
        "d_rpm": _delta(rpm, prev.get("rpm")),
        "d_ema": _delta(ema, prev.get("ema")),
        "d_hist": _delta(hist, prev.get("hist")),
    }


def _cur_nums(row: dict, prev: dict | None) -> dict[str, float | None]:
    prev = prev or {}
    rpm = row.get("rpm")
    ema = row.get("ema")
    return {
        "rpm": rpm,
        "ema": ema,
        "hist": None,
        "d_rpm": _delta(rpm, prev.get("rpm")),
        "d_ema": _delta(ema, prev.get("ema")),
        "d_hist": None,
    }


def _scale_map(rows: list[dict], prefix: str) -> dict[str, float]:
    scales: dict[str, float] = {}
    for key in ("rpm", "ema", "hist"):
        scales[f"{prefix}.{key}"] = _median_abs([r.get(key) for r in rows])
    return scales


def tf_numeric(bars: list[Bar], tf: str) -> dict:
    current = compute_current(bars)
    up_set = load_up_settings(tf)
    up = compute_up(bars, up_set, track_divs=False)
    hist_names = hist_layer_names(up_set)
    hist_name = hist_names[0] if hist_names else "up"
    series = up["series"]
    cur_rows: list[dict] = []
    small_rows: list[dict] = []
    middle_rows: list[dict] = []
    hist_rows: list[dict] = []
    packs: list[dict] = []
    prev_cur: dict | None = None
    prev_small: dict | None = None
    prev_middle: dict | None = None
    prev_hist: dict | None = None
    for i, bar in enumerate(bars):
        cur = current[i] if i < len(current) else {}
        up_row = series[i] if i < len(series) else {}
        small = up_row.get("small") or {}
        middle = up_row.get("middle") or {}
        hist = up_row.get(hist_name) or {}
        c_nums = _cur_nums(cur, prev_cur)
        s_nums = _layer_nums(small, prev_small)
        m_nums = _layer_nums(middle, prev_middle)
        h_nums = _layer_nums(hist, prev_hist)
        cur_rows.append(c_nums)
        small_rows.append(s_nums)
        middle_rows.append(m_nums)
        hist_rows.append(h_nums)
        packs.append(
            {
                "dt": bar.dt,
                "c": bar.c,
                "current": c_nums,
                "small": s_nums,
                "middle": m_nums,
                "hist": h_nums,
                "hist_raw": hist,
            }
        )
        if c_nums.get("rpm") is not None:
            prev_cur = cur
        if s_nums.get("rpm") is not None:
            prev_small = small
        if m_nums.get("rpm") is not None:
            prev_middle = middle
        if h_nums.get("hist") is not None:
            prev_hist = hist
    scales = {}
    scales.update(_scale_map(cur_rows, "current"))
    scales.update(_scale_map(small_rows, "small"))
    scales.update(_scale_map(middle_rows, "middle"))
    scales.update(_scale_map(hist_rows, "hist"))
    return {
        "tf": tf,
        "bars": bars,
        "packs": packs,
        "scales": scales,
        "hist_name": hist_name,
    }


def _z_one(
    nums: dict,
    scales: dict,
    prefix: str,
    keys: tuple[str, ...] = _NUM_KEYS,
    *,
    scale_prefix: str | None = None,
) -> dict[str, float]:
    parent_prefix = scale_prefix if scale_prefix is not None else prefix
    out: dict[str, float] = {}
    for key in keys:
        val = nums.get(key)
        if val is None:
            continue
        parent = _PARENT.get(key, key)
        scale = scales.get(f"{parent_prefix}.{parent}") or 1.0
        out[f"{prefix}.{key}"] = val / scale
    return out


def pack_z(pack: dict, scales: dict, tf: str) -> dict[str, float]:
    z: dict[str, float] = {}
    z.update(_z_one(pack.get("current") or {}, scales, f"{tf}.current", scale_prefix="current"))
    z.update(_z_one(pack.get("small") or {}, scales, f"{tf}.small", scale_prefix="small"))
    z.update(_z_one(pack.get("middle") or {}, scales, f"{tf}.middle", scale_prefix="middle"))
    z.update(_z_one(pack.get("hist") or {}, scales, f"{tf}.hist", scale_prefix="hist"))
    return z


def pack_mag_z(pack: dict, scales: dict, tf: str) -> dict[str, float]:
    """z of pack deltas (magnitude and sign), not absolute RPM levels."""
    z: dict[str, float] = {}
    z.update(_z_one(pack.get("current") or {}, scales, f"{tf}.current", _MAG_KEYS, scale_prefix="current"))
    z.update(_z_one(pack.get("small") or {}, scales, f"{tf}.small", _MAG_KEYS, scale_prefix="small"))
    z.update(_z_one(pack.get("middle") or {}, scales, f"{tf}.middle", _MAG_KEYS, scale_prefix="middle"))
    z.update(_z_one(pack.get("hist") or {}, scales, f"{tf}.hist", _MAG_KEYS, scale_prefix="hist"))
    return z


def _gap_z(a: float | None, b: float, scale: float, name: str, out: dict[str, float]) -> None:
    if a is None:
        return
    out[name] = (a - b) / max(scale, 1e-12)


def pack_pos_z(pack: dict, scales: dict, tf: str) -> dict[str, float]:
    """z-gaps of line distances (mean characteristic, not the hard order gate)."""
    out: dict[str, float] = {}
    cur = pack.get("current") or {}
    rpm_scale = scales.get("current.rpm") or 1.0
    ema_scale = scales.get("current.ema") or 1.0
    trio_scale = max(rpm_scale, ema_scale, 1e-12)
    _gap_z(cur.get("rpm"), 0.0, rpm_scale, f"{tf}.current.rpm_vs_0", out)
    _gap_z(cur.get("ema"), 0.0, ema_scale, f"{tf}.current.ema_vs_0", out)
    if cur.get("rpm") is not None and cur.get("ema") is not None:
        out[f"{tf}.current.rpm_vs_ema"] = (cur["rpm"] - cur["ema"]) / trio_scale
    for a_layer, a_key, b_layer, b_key in _POS_PAIRS:
        a = (pack.get(a_layer) or {}).get(a_key)
        b = (pack.get(b_layer) or {}).get(b_key)
        if a is None or b is None:
            continue
        sa = scales.get(f"{a_layer}.{a_key}") or 1.0
        sb = scales.get(f"{b_layer}.{b_key}") or 1.0
        scale = max(sa, sb, 1e-12)
        name = f"{tf}.{a_layer}.{a_key}_vs_{b_layer}.{b_key}"
        out[name] = (a - b) / scale
    return out


def pack_order_z(pack: dict, scales: dict, tf: str) -> dict[str, float]:
    """Who-is-above for RPM current trio: rpm / zero / EMA (hard pos gate)."""
    out: dict[str, float] = {}
    cur = pack.get("current") or {}
    rpm_scale = scales.get("current.rpm") or 1.0
    ema_scale = scales.get("current.ema") or 1.0
    vs0 = _side(cur.get("rpm"), rpm_scale, NEAR_ZERO)
    if vs0 in _ZERO_RANK:
        out[f"{tf}.current.rpm_side"] = _ZERO_RANK[vs0]
    ema_vs0 = _side(cur.get("ema"), ema_scale, NEAR_ZERO)
    if ema_vs0 in _ZERO_RANK:
        out[f"{tf}.current.ema_side"] = _ZERO_RANK[ema_vs0]
    vs_ema = _vs_ema(cur.get("rpm"), cur.get("ema"), rpm_scale)
    if vs_ema in _EMA_RANK:
        out[f"{tf}.current.rpm_side_ema"] = _EMA_RANK[vs_ema]
    return out


def pack_layer_order(pack: dict, scales: dict, tf: str) -> dict[str, float]:
    """Who-is-above for small/middle RPM and EMAs (mean, not min)."""
    out: dict[str, float] = {}
    for a_layer, a_key, b_layer, b_key in _POS_PAIRS:
        a = (pack.get(a_layer) or {}).get(a_key)
        b = (pack.get(b_layer) or {}).get(b_key)
        if a is None or b is None:
            continue
        sa = scales.get(f"{a_layer}.{a_key}") or 1.0
        sb = scales.get(f"{b_layer}.{b_key}") or 1.0
        scale = max(sa, sb, 1e-12)
        near = NEAR_EMA * scale
        if abs(a - b) < near:
            rank = 0.0
        else:
            rank = 1.0 if a > b else -1.0
        out[f"{tf}.{a_layer}.{a_key}_side_{b_layer}.{b_key}"] = rank
    return out


def _cross_z(prev_side: str, cur_side: str, ranks: dict[str, float]) -> float | None:
    prev_rank = ranks.get(prev_side)
    cur_rank = ranks.get(cur_side)
    if prev_rank is None or cur_rank is None:
        return None
    delta = cur_rank - prev_rank
    if delta == 0:
        return 0.0
    return 1.0 if delta > 0 else -1.0


def _put_z(dst: dict[str, float], key: str, value: float | None) -> None:
    if value is not None:
        dst[key] = value


def pack_events(pack: dict, prev: dict | None, scales: dict, tf: str) -> dict[str, dict[str, float]]:
    """Crossings and line direction/flat after retag on the live scale."""
    prev = prev or {}
    current: dict[str, float] = {}
    other: dict[str, float] = {}
    cur = pack.get("current") or {}
    prev_cur = prev.get("current") or {}
    rpm_scale = scales.get("current.rpm") or 1.0
    ema_scale = scales.get("current.ema") or 1.0
    _put_z(
        current,
        f"{tf}.current.rpm_x_0",
        _cross_z(
            _side(prev_cur.get("rpm"), rpm_scale, NEAR_ZERO),
            _side(cur.get("rpm"), rpm_scale, NEAR_ZERO),
            _ZERO_RANK,
        ),
    )
    _put_z(
        current,
        f"{tf}.current.rpm_x_ema",
        _cross_z(
            _vs_ema(prev_cur.get("rpm"), prev_cur.get("ema"), rpm_scale),
            _vs_ema(cur.get("rpm"), cur.get("ema"), rpm_scale),
            _EMA_RANK,
        ),
    )
    _put_z(
        other,
        f"{tf}.current.rpm_dir",
        _DIR_Z.get(_slope_only(cur.get("rpm"), prev_cur.get("rpm"), rpm_scale)),
    )
    _put_z(
        other,
        f"{tf}.current.ema_x_0",
        _cross_z(
            _side(prev_cur.get("ema"), ema_scale, NEAR_ZERO),
            _side(cur.get("ema"), ema_scale, NEAR_ZERO),
            _ZERO_RANK,
        ),
    )
    _put_z(
        other,
        f"{tf}.current.ema_dir",
        _DIR_Z.get(_slope_only(cur.get("ema"), prev_cur.get("ema"), ema_scale)),
    )
    for layer in ("small", "middle"):
        nums = pack.get(layer) or {}
        prev_nums = prev.get(layer) or {}
        layer_rpm = scales.get(f"{layer}.rpm") or 1.0
        layer_ema = scales.get(f"{layer}.ema") or 1.0
        _put_z(
            other,
            f"{tf}.{layer}.rpm_x_0",
            _cross_z(
                _side(prev_nums.get("rpm"), layer_rpm, NEAR_ZERO),
                _side(nums.get("rpm"), layer_rpm, NEAR_ZERO),
                _ZERO_RANK,
            ),
        )
        _put_z(
            other,
            f"{tf}.{layer}.ema_x_0",
            _cross_z(
                _side(prev_nums.get("ema"), layer_ema, NEAR_ZERO),
                _side(nums.get("ema"), layer_ema, NEAR_ZERO),
                _ZERO_RANK,
            ),
        )
        _put_z(
            other,
            f"{tf}.{layer}.rpm_dir",
            _DIR_Z.get(_slope_only(nums.get("rpm"), prev_nums.get("rpm"), layer_rpm)),
        )
        _put_z(
            other,
            f"{tf}.{layer}.ema_dir",
            _DIR_Z.get(_slope_only(nums.get("ema"), prev_nums.get("ema"), layer_ema)),
        )
    hist = pack.get("hist") or {}
    prev_hist = prev.get("hist") or {}
    hist_scale = scales.get("hist.hist") or 1.0
    _put_z(
        other,
        f"{tf}.hist.x_0",
        _cross_z(
            _side(prev_hist.get("hist"), hist_scale, NEAR_HIST),
            _side(hist.get("hist"), hist_scale, NEAR_HIST),
            _ZERO_RANK,
        ),
    )
    return {"current": current, "other": other}


def _retag_layer(nums: dict, prev: dict | None, rpm_scale: float, ema_scale: float) -> dict:
    rpm = nums.get("rpm")
    ema = nums.get("ema")
    prev_rpm = (prev or {}).get("rpm")
    prev_ema = (prev or {}).get("ema")
    vs0 = _side(rpm, rpm_scale, NEAR_ZERO)
    vs_ema = _vs_ema(rpm, ema, rpm_scale)
    slope = _slope_tag(rpm, prev_rpm, ema, rpm_scale)
    ema_vs0, ema_slope = _ema_state(ema, prev_ema, ema_scale)
    tags = [vs0, vs_ema, slope, ema_vs0, ema_slope]
    return {"tags": tags, "rpm": rpm, "ema": ema}


def pack_key(pack: dict, scales: dict, prev: dict | None = None) -> tuple:
    """Discrete pack after retag on live scales (not Hamming on stored labels)."""
    prev = prev or {}
    key: list[str] = []
    for name in ("current", "small", "middle"):
        tagged = _retag_layer(
            pack.get(name) or {},
            prev.get(name),
            scales.get(f"{name}.rpm") or 1.0,
            scales.get(f"{name}.ema") or 1.0,
        )
        key.extend(tagged["tags"])
    hist = pack.get("hist") or {}
    key.append(_side(hist.get("hist"), scales.get("hist.hist") or 1.0, NEAR_HIST))
    raw = pack.get("hist_raw") or {}
    key.append(_hist_dir(raw) if raw else "na")
    return tuple(key)


def pack_tag_count(pack: dict, scales: dict, prev: dict | None = None) -> int:
    """Retag with live scales; count non-na discrete fields (pack if ≥5)."""
    return sum(1 for t in pack_key(pack, scales, prev) if t not in {None, "na"})


def feat_sim(z_hist: dict[str, float], z_live: dict[str, float]) -> float:
    keys = [k for k in z_live if k in z_hist]
    if not keys:
        return 0.0
    return sum(sim_field(z_hist[k], z_live[k]) for k in keys) / len(keys)


def feat_sim_min(z_hist: dict[str, float], z_live: dict[str, float]) -> float:
    keys = [k for k in z_live if k in z_hist]
    if not keys:
        return 0.0
    return min(sim_field(z_hist[k], z_live[k]) for k in keys)


def _reject_min(z_hist: dict[str, float], z_live: dict[str, float], sim_min: float) -> bool:
    """True if min field sim is below sim_min (or there is nothing to compare)."""
    n = 0
    for key, live in z_live.items():
        hist = z_hist.get(key)
        if hist is None:
            continue
        n += 1
        if sim_field(hist, live) < sim_min:
            return True
    return n == 0


def frame_sim(z_hist: dict[str, float], z_live: dict[str, float]) -> float:
    return feat_sim(z_hist, z_live)


def _key_delta(prev: tuple, cur: tuple) -> tuple:
    n = min(len(prev), len(cur))
    if n == 0:
        return ()
    return tuple((prev[i], cur[i]) for i in range(n))


def _tuple_sim(left: tuple, right: tuple) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(1.0 for a, b in zip(left, right) if a == b) / len(left)


def _group_min(hist_frames: list[dict], live_frames: list[dict], key: str) -> float | None:
    vals: list[float] = []
    for hist, live in zip(hist_frames, live_frames):
        left = hist.get(key) or {}
        right = live.get(key) or {}
        if left and right:
            vals.append(feat_sim_min(left, right))
    if not vals:
        return None
    return min(vals)


def _group_mean(hist_frames: list[dict], live_frames: list[dict], key: str) -> float | None:
    vals: list[float] = []
    for hist, live in zip(hist_frames, live_frames):
        left = hist.get(key) or {}
        right = live.get(key) or {}
        if left and right:
            vals.append(feat_sim(left, right))
    if not vals:
        return None
    return sum(vals) / len(vals)


def chain_characteristics_sim(
    hist_frames: list[dict],
    live_frames: list[dict],
) -> dict[str, float]:
    """Trio order / current-cross min; layers, geom, dir/other, mag, pack-delta mean."""
    if not live_frames or len(hist_frames) != len(live_frames):
        return {}
    pos_vals: list[float] = []
    mag_vals: list[float] = []
    layer_vals: list[float] = []
    geom_vals: list[float] = []
    for hist, live in zip(hist_frames, live_frames):
        pos_vals.append(feat_sim_min(hist.get("pos") or {}, live.get("pos") or {}))
        hist_mag = hist.get("mag") or {}
        live_mag = live.get("mag") or {}
        if hist_mag and live_mag:
            mag_vals.append(feat_sim(hist_mag, live_mag))
        hist_layers = hist.get("layers") or {}
        live_layers = live.get("layers") or {}
        if hist_layers and live_layers:
            layer_vals.append(feat_sim(hist_layers, live_layers))
        hist_geom = hist.get("geom") or {}
        live_geom = live.get("geom") or {}
        if hist_geom and live_geom:
            geom_vals.append(feat_sim(hist_geom, live_geom))
    pack_vals: list[float] = []
    for i in range(1, len(live_frames)):
        hist_delta = _key_delta(hist_frames[i - 1].get("key") or (), hist_frames[i].get("key") or ())
        live_delta = _key_delta(live_frames[i - 1].get("key") or (), live_frames[i].get("key") or ())
        pack_vals.append(_tuple_sim(hist_delta, live_delta))
    out = {
        "pos": min(pos_vals) if pos_vals else 0.0,
        "mag": sum(mag_vals) / len(mag_vals) if mag_vals else 0.0,
        "pack": sum(pack_vals) / len(pack_vals) if pack_vals else 0.0,
    }
    if layer_vals:
        out["layers"] = sum(layer_vals) / len(layer_vals)
    if geom_vals:
        out["geom"] = sum(geom_vals) / len(geom_vals)
    current = _group_min(hist_frames, live_frames, "current")
    other = _group_mean(hist_frames, live_frames, "other")
    if current is not None:
        out["current"] = current
    if other is not None:
        out["other"] = other
    return out


def chain_sim(
    hist_frames: list[dict],
    live_frames: list[dict],
    sim_min: float = SIM_MIN,
) -> float:
    """Pattern match: trio order + current crossings first; dir/layers/geom/mag/pack after."""
    chars = chain_characteristics_sim(hist_frames, live_frames)
    if not chars:
        return 0.0
    if chars["pos"] < sim_min:
        return 0.0
    current = chars.get("current")
    if current is not None and current < sim_min:
        return 0.0
    if any(value < sim_min for value in chars.values()):
        return 0.0
    return sum(chars.values()) / len(chars)


def strip_tf_keys(feat: dict[str, float], tf: str) -> dict[str, float]:
    prefix = tf + "."
    return {(k[len(prefix):] if k.startswith(prefix) else k): v for k, v in feat.items()}


def pack_feat(pack: dict, prev: dict | None, scales: dict, tf: str) -> dict:
    """Last-bar pack features for analog search (no chain)."""
    events = pack_events(pack, prev, scales, tf)
    return {
        "pos": strip_tf_keys(pack_order_z(pack, scales, tf), tf),
        "layers": strip_tf_keys(pack_layer_order(pack, scales, tf), tf),
        "geom": strip_tf_keys(pack_pos_z(pack, scales, tf), tf),
        "mag": strip_tf_keys(pack_mag_z(pack, scales, tf), tf),
        "current": strip_tf_keys(events["current"], tf),
        "other": strip_tf_keys(events["other"], tf),
        "dt": pack["dt"],
        "c": pack["c"],
    }


def pack_sim(hist: dict, live: dict, sim_min: float = SIM_MIN) -> float:
    """Similar forming pack: trio order + crossings min; layers/geom/dir/mag mean. No pack-delta."""
    if feat_sim_min(hist.get("pos") or {}, live.get("pos") or {}) < sim_min:
        return 0.0
    live_cur = live.get("current") or {}
    if live_cur and _reject_min(hist.get("current") or {}, live_cur, sim_min):
        return 0.0
    soft: list[float] = []
    for key in ("layers", "geom", "mag", "other"):
        left = hist.get(key) or {}
        right = live.get(key) or {}
        if left and right:
            value = feat_sim(left, right)
            if value < sim_min:
                return 0.0
            soft.append(value)
    pos = feat_sim_min(hist.get("pos") or {}, live.get("pos") or {})
    vals = [pos]
    if live_cur:
        vals.append(feat_sim_min(hist.get("current") or {}, live_cur))
    vals.extend(soft)
    return sum(vals) / len(vals)


def sample_shares(outcomes: list[str]) -> dict[str, float]:
    n = len(outcomes)
    if n == 0:
        return {"n": 0, "up": 0.0, "down": 0.0, "flat": 0.0}
    up = sum(1 for o in outcomes if o == "up")
    down = sum(1 for o in outcomes if o == "down")
    flat = sum(1 for o in outcomes if o == "flat")
    return {
        "n": n,
        "up": 100.0 * up / n,
        "down": 100.0 * down / n,
        "flat": 100.0 * flat / n,
    }


def paint_shares(outcomes: list[str]) -> dict[str, float]:
    """Laplace (add-1) so one analog cannot paint 0% or 100%."""
    n = len(outcomes)
    up = sum(1 for o in outcomes if o == "up")
    down = sum(1 for o in outcomes if o == "down")
    flat = sum(1 for o in outcomes if o == "flat")
    denom = n + 3.0 * LAPLACE
    return {
        "n": n,
        "up": 100.0 * (up + LAPLACE) / denom,
        "down": 100.0 * (down + LAPLACE) / denom,
        "flat": 100.0 * (flat + LAPLACE) / denom,
    }


def blend_lines(prev: dict | None, raw: dict) -> dict[str, float]:
    """EMA of painted shares; a single bar cannot jump 0↔100."""
    if prev is None:
        return {"up": raw["up"], "down": raw["down"], "flat": raw["flat"]}
    a = LINE_ALPHA
    keep = 1.0 - a
    return {
        "up": a * raw["up"] + keep * prev["up"],
        "down": a * raw["down"] + keep * prev["down"],
        "flat": a * raw["flat"] + keep * prev["flat"],
    }


def _align_index(
    lead_dt: datetime,
    lead_tf: str,
    src_times: list[datetime],
    src_tf: str,
    *,
    forming: bool,
    clock: datetime,
) -> int | None:
    if src_tf == "D1" or forming:
        event = clock if forming else lead_dt + timedelta(minutes=PERIOD_MIN[lead_tf])
        return at_or_before_indices([event], src_times)[0]
    event = lead_dt + timedelta(minutes=PERIOD_MIN[lead_tf])
    return last_closed_indices([event], src_times, PERIOD_MIN.get(src_tf))[0]


def _frame_is_forming(pack_dt: datetime, lead_tf: str, clock: datetime) -> bool:
    close = pack_dt + timedelta(minutes=PERIOD_MIN[lead_tf])
    return close > clock


def _frame_at(
    lead_i: int,
    lead_tf: str,
    books: dict[str, dict],
    live_scales: dict[str, dict],
    clock: datetime,
) -> dict | None:
    lead = books[lead_tf]
    pack = lead["packs"][lead_i]
    if pack_tag_count(pack, live_scales[lead_tf], lead["packs"][lead_i - 1] if lead_i else None) < MIN_PACK_TAGS:
        return None
    pos = pack_order_z(pack, live_scales[lead_tf], lead_tf)
    geom = pack_pos_z(pack, live_scales[lead_tf], lead_tf)
    layers = pack_layer_order(pack, live_scales[lead_tf], lead_tf)
    mag = pack_mag_z(pack, live_scales[lead_tf], lead_tf)
    lead_prev = lead["packs"][lead_i - 1] if lead_i else None
    events = pack_events(pack, lead_prev, live_scales[lead_tf], lead_tf)
    current = dict(events["current"])
    other = dict(events["other"])
    parts = {lead_tf: pack}
    lead_key = pack_key(pack, live_scales[lead_tf], lead_prev)
    forming = lead_i == len(lead["packs"]) - 1 and _frame_is_forming(pack["dt"], lead_tf, clock)
    for tf in ODDS_FRAME_TFS[lead_tf]:
        if tf == lead_tf:
            continue
        book = books.get(tf)
        if not book:
            continue
        times = [p["dt"] for p in book["packs"]]
        idx = _align_index(pack["dt"], lead_tf, times, tf, forming=forming, clock=clock)
        if idx is None:
            continue
        extra = book["packs"][idx]
        prev = book["packs"][idx - 1] if idx else None
        if pack_tag_count(extra, live_scales[tf], prev) < MIN_PACK_TAGS:
            continue
        pos.update(pack_order_z(extra, live_scales[tf], tf))
        geom.update(pack_pos_z(extra, live_scales[tf], tf))
        layers.update(pack_layer_order(extra, live_scales[tf], tf))
        mag.update(pack_mag_z(extra, live_scales[tf], tf))
        extra_events = pack_events(extra, prev, live_scales[tf], tf)
        current.update(extra_events["current"])
        other.update(extra_events["other"])
        parts[tf] = extra
    return {
        "i": lead_i,
        "dt": pack["dt"],
        "c": pack["c"],
        "pos": pos,
        "geom": geom,
        "layers": layers,
        "mag": mag,
        "current": current,
        "other": other,
        "parts": parts,
        "key": lead_key,
        "forming": forming,
    }


def _build_books(
    raw: dict[str, list[Bar]],
    lead_tf: str,
    *,
    extra_tfs: tuple[str, ...] = (),
) -> dict[str, dict]:
    clock = series_clock(raw) or datetime.min
    m1 = raw.get("M1") or []
    fillers = m1 or raw.get("M10") or raw.get("M30") or raw.get("H4") or []
    d1 = forming_d1(raw.get("D1") or [], fillers)
    books: dict[str, dict] = {}
    want = list(ODDS_FRAME_TFS[lead_tf])
    for tf in extra_tfs:
        if tf not in want:
            want.append(tf)
    for tf in want:
        if tf in books:
            continue
        if tf == "D1":
            bars = d1
        elif tf == "M1":
            bars = list(m1)
        else:
            bars = append_forming(raw.get(tf) or [], tf, m1, clock)
        if not bars:
            continue
        books[tf] = tf_numeric(bars, tf)
    return books


def odds_rows(
    raw: dict[str, list[Bar]],
    lead_tf: str,
    *,
    sim_min: float = SIM_MIN,
    chain_bars: int | None = None,
    books: dict[str, dict] | None = None,
    clock: datetime | None = None,
) -> list[dict]:
    if lead_tf not in ODDS_LEAD_TFS:
        raise ValueError(f"odds lead TF must be M10, M30 or H4, got {lead_tf}")
    books = books if books is not None else _build_books(raw, lead_tf)
    if lead_tf not in books:
        return []
    clock = clock or series_clock(raw) or books[lead_tf]["packs"][-1]["dt"]
    live_scales = {tf: book["scales"] for tf, book in books.items()}
    lead_packs = books[lead_tf]["packs"]
    frames: list[dict | None] = []
    for i in range(len(lead_packs)):
        frames.append(_frame_at(i, lead_tf, books, live_scales, clock))
    closes = [p["c"] for p in lead_packs]
    flat_pct = flat_threshold(closes)
    rows: list[dict] = []
    need = chain_bars if chain_bars is not None else CHAIN_WINDOW.get(lead_tf, CHAIN_BARS)
    start_i = max(need - 1, len(frames) - ODDS_PAINT)
    valid: list[int] = [i for i, fr in enumerate(frames) if fr is not None]
    chains: dict[int, list[dict]] = {}
    for i in valid:
        if i + 1 < need:
            continue
        chunk = []
        ok = True
        for k in range(i - need + 1, i + 1):
            if frames[k] is None:
                ok = False
                break
            chunk.append(
                {
                    "pos": frames[k]["pos"],
                    "layers": frames[k].get("layers") or {},
                    "geom": frames[k].get("geom") or {},
                    "mag": frames[k]["mag"],
                    "current": frames[k]["current"],
                    "other": frames[k]["other"],
                    "key": frames[k]["key"],
                }
            )
        if ok:
            chains[i] = chunk
    prev_line: dict[str, float] | None = None
    for i in range(start_i, len(lead_packs)):
        chain = chains.get(i)
        frame = frames[i]
        forming = bool(frame and frame.get("forming"))
        if not forming and i == len(lead_packs) - 1:
            forming = _frame_is_forming(lead_packs[i]["dt"], lead_tf, clock)
        if chain is None or frame is None:
            if prev_line is None:
                continue
            rows.append(
                _share_row(
                    lead_packs[i]["dt"],
                    {"n": 0, "up": prev_line["up"], "down": prev_line["down"], "flat": prev_line["flat"]},
                    forming=forming,
                )
            )
            continue
        hits: list[str] = []
        live_pos = frame["pos"]
        live_cur = frame["current"]
        for j in chains:
            if j >= i:
                break
            if j + 1 >= len(closes):
                continue
            past = frames[j]
            if past is None:
                continue
            if _reject_min(past["pos"], live_pos, sim_min):
                continue
            if live_cur and past.get("current") and _reject_min(past["current"], live_cur, sim_min):
                continue
            if chain_sim(chains[j], chain, sim_min) >= sim_min:
                hits.append(classify_outcome(closes[j], closes[j + 1], flat_pct))
        raw = paint_shares(hits)
        line = blend_lines(prev_line, raw)
        prev_line = line
        rows.append(
            _share_row(
                lead_packs[i]["dt"],
                {"n": raw["n"], "up": line["up"], "down": line["down"], "flat": line["flat"]},
                forming=forming,
            )
        )
    last = lead_packs[-1]
    if _frame_is_forming(last["dt"], lead_tf, clock):
        if not rows or rows[-1]["dt"] != last["dt"]:
            raw = paint_shares([])
            line = blend_lines(prev_line, raw)
            rows.append(
                _share_row(
                    last["dt"],
                    {"n": 0, "up": line["up"], "down": line["down"], "flat": line["flat"]},
                    forming=True,
                )
            )
    return rows


def _share_row(dt: datetime, share: dict, *, forming: bool) -> dict:
    return {
        "dt": dt,
        "up": clip_line(share["up"]),
        "down": clip_line(share["down"]),
        "flat": clip_line(share["flat"]),
        "n": share["n"],
        "p_up": share["up"],
        "p_down": share["down"],
        "p_flat": share["flat"],
        "forming": 1 if forming else 0,
    }


def write_odds_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        fh.write("datetime;up;down;flat;n\n")
        for row in rows:
            stamp = format_odds_dt(row["dt"]) if isinstance(row["dt"], datetime) else str(row["dt"])
            fh.write(
                f"{stamp};{row['up']:.2f};{row['down']:.2f};{row['flat']:.2f};{row['n']}\n"
            )
    last_err: OSError | None = None
    for attempt in range(_WRITE_TRIES):
        try:
            tmp.replace(path)
            return
        except OSError as exc:
            last_err = exc
            time.sleep(_WRITE_WAIT * (attempt + 1))
    if last_err is not None:
        raise last_err
    tmp.replace(path)


def odds_path(sec: str, class_code: str, tf: str, dest_dir: Path | None = None) -> Path:
    return (dest_dir or ODDS_DIR) / f"{sec}_{class_code}_{tf}.csv"


def export_odds(
    sec: str,
    class_code: str = "TQBR",
    dest_dir: Path | None = None,
    data_dir: Path | None = None,
    tfs: tuple[str, ...] | None = None,
) -> dict:
    dest = Path(dest_dir or ODDS_DIR)
    chosen = tuple(tf for tf in (tfs or ODDS_LEAD_TFS) if tf in ODDS_LEAD_TFS)
    if not chosen:
        chosen = ODDS_LEAD_TFS
    data_root = data_dir or BARS_DIR
    need: list[str] = ["M1"]
    for tf in chosen:
        for name in ODDS_FRAME_TFS[tf]:
            if name not in need:
                need.append(name)
    raw = load_instrument(
        sec,
        class_code,
        data_root,
        tfs=tuple(need),
        max_bars=ODDS_MAX_BARS,
        skip_missing=True,
    )
    names = mark_sec_names(sec, class_code, data_root)
    files: dict[str, str] = {}
    counts: dict[str, dict] = {}
    shared = _build_books(raw, chosen[0], extra_tfs=chosen[1:]) if chosen else {}
    clock = series_clock(raw)
    for tf in chosen:
        rows = odds_rows(raw, tf, books=shared, clock=clock)
        written = None
        for name in names:
            path = odds_path(name, class_code, tf, dest)
            write_odds_csv(path, rows)
            written = path
        files[tf] = str(written) if written else ""
        last = rows[-1] if rows else None
        counts[tf] = {
            "bars": len(rows),
            "n": last["n"] if last else 0,
            "up": last["p_up"] if last else 0.0,
            "down": last["p_down"] if last else 0.0,
            "flat": last["p_flat"] if last else 0.0,
            "forming": last["forming"] if last else 0,
        }
    return {
        "sec": sec,
        "class_code": class_code,
        "dir": str(dest),
        "files": files,
        "counts": counts,
    }


def export_all_odds(
    class_code: str | None = None,
    dest_dir: Path | None = None,
    data_dir: Path | None = None,
    tfs: tuple[str, ...] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[dict]:
    emit = log or (lambda msg: print(msg, flush=True))
    items = list_instruments(
        data_dir or BARS_DIR,
        class_code=class_code,
        tfs=("M1", "M10", "M30", "H4"),
    )
    emit(f"odds all  n={len(items)}  class={class_code or '*'}")
    reports: list[dict] = []
    for sec, cls in items:
        try:
            report = export_odds(sec, cls, dest_dir=dest_dir, data_dir=data_dir, tfs=tfs)
            reports.append(report)
            emit(format_odds(report, compact=True))
        except Exception as exc:
            reports.append({"sec": sec, "class_code": cls, "error": str(exc)})
            emit(f"{sec} {cls}  error: {exc}")
    return reports


def format_odds(report: dict, compact: bool = False) -> str:
    counts = report.get("counts") or {}
    if compact:
        bits = [
            f"{tf} rows={pack['bars']} n={pack['n']} up={pack['up']:.0f} dn={pack['down']:.0f} fl={pack['flat']:.0f}"
            f"{' form' if pack.get('forming') else ''}"
            for tf, pack in counts.items()
        ]
        when = report.get("exported_at") or ""
        prefix = f"{when}  " if when else ""
        body = "  ".join(bits)
        line = f"{prefix}{report['sec']} {report['class_code']}"
        return f"{line}  {body}" if body else line
    lines = [f"{report['sec']} {report['class_code']}  odds -> {report['dir']}"]
    for tf, pack in counts.items():
        lines.append(
            f"  {tf}: rows={pack['bars']} sample={pack['n']} "
            f"up={pack['up']:.1f}% down={pack['down']:.1f}% flat={pack['flat']:.1f}%"
        )
        path = (report.get("files") or {}).get(tf)
        if path:
            lines.append(f"       {path}")
    return "\n".join(lines)


def watch_odds(
    sec: str | None = None,
    class_code: str | None = None,
    dest_dir: Path | None = None,
    data_dir: Path | None = None,
    tfs: tuple[str, ...] | None = None,
    poll: float = 11.0,
    exporter: Callable[..., dict] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    stop: Callable[[], bool] | None = None,
    log: Callable[[str], None] | None = None,
) -> int:
    """Recalc on M1 ticks (forming кадр) and when M10/M30/H4 close."""
    return watch_marks(
        sec,
        class_code,
        dest_dir=dest_dir or ODDS_DIR,
        data_dir=data_dir,
        tfs=tfs or ODDS_WATCH_TFS,
        poll=poll,
        exporter=exporter or export_odds,
        sleeper=sleeper,
        stop=stop,
        log=log,
        formatter=format_odds,
        label="odds",
        export_tfs=lambda _dirty: ODDS_LEAD_TFS,
    )
