# -*- coding: utf-8 -*-
"""Standalone MLP on pair-bundle chains (evolved from --odds).

Input = one pair bundle (связкаД1Н4 / связкаН4М30 / связкаМ30М10):
3 neighboring packs of the senior TF + 3 of the junior. Same weights
for every pair so knowledge mixes across TFs. Not a snapshot of five
TFs. Training samples every M1. Ahead is three readouts (one per
pair: 10 / 30 / 240 M1). No action head (Wa): do not train it, do not
draw it. Live action is the equal mean of the three ahead softmaxes.
Chart ahead lines are that same mean (flat / up / down), not one TF's
head. Senior TFs on history are M1-built: closed slots frozen at close,
forming OHLC to minute t (CSV only verifies close).
Regime = impulse/pullback vs senior RPM on every bar. A minute with
no room for the longest ahead is not a training row. Does not change
combo buy/sell. Do not extend --odds; continue this net instead.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

import numpy as np

from analyzer.bars import BARS_DIR, Bar, KNOWN_TFS, load_instrument, list_instruments
from analyzer.combo import (
    PERIOD_MIN,
    WARMUP,
    buy_body,
    buy_hist,
    sell_body,
    sell_hist,
    setup_signal,
)
from analyzer.marks import mark_sec_names, watch_marks
from analyzer.odds import (
    BUNDLE_PAIRS,
    DT_FMT,
    FLAT_FRAC,
    FLAT_PCT,
    ODDS_MAX_BARS,
    at_or_before_indices,
    clip_line,
    flat_threshold,
    format_odds_dt,
    pack_tag_count,
    slot_open,
    tf_numeric,
)
from analyzer.tf_from_m1 import replay_tf_book
from analyzer.states import (
    EMA_TREND_BARS,
    NEAR_HIST,
    NEAR_ZERO,
    _ema_state,
    _hist_dir,
    _side,
    _slope_only,
    _slope_tag,
    _vs_ema,
)

NET_TFS = ("M1", "M10", "M30", "H4", "D1")
NET_DIR = Path(r"C:\QuikFinam\LuaIndicators\analyzer_net")
NET_CSV_DIR = NET_DIR
WEIGHTS_NAME = "net.npz"
NET_CHART_TFS = ("M1", "M10", "M30", "H4", "D1")
NET_WATCH_TFS = ("M1", "M10", "M30", "H4")
CHAIN_BARS = 3
STRIDE = 1
_WRITE_TRIES = 6
_WRITE_WAIT = 0.12
HIDDEN = (128, 64)
EPOCHS = 36
BATCH = 96
LR = 0.008
MOMENTUM = 0.9
WEIGHT_DECAY = 2e-4
PATIENCE = 8
VAL_FRAC = 0.2
MIN_PACK_TAGS = 5
LAYER_DIV_LOOK = 3
LAYER_DIV_MIN = 2
R_MULT = 2.0
GIVEBACK = 1.0
STOP_BARS = 10
TRADE_HORIZON = 120
ACTION_MIN = 0.45
ACTION_GAP = 0.08
POINT_REGIME_MIN = 0.55
AHEAD_BARS = 10
AHEAD_MIN = 0.45
# horizon in junior bars of the pair; sample grid is always M1
BUNDLE_AHEAD = {
    ("M30", "M10"): {"clock": "M1", "period": 1, "bars": 10},
    ("H4", "M30"): {"clock": "M5", "period": 5, "bars": 6},
    ("D1", "H4"): {"clock": "M30", "period": 30, "bars": 8},
}


def ahead_horizon_m1(pair: tuple[str, str]) -> int:
    """Ahead window in M1 bars from this minute (6 M5 = 30 M1, 8 M30 = 240 M1)."""
    spec = BUNDLE_AHEAD[pair]
    return int(spec["period"]) * int(spec["bars"])


def max_ahead_m1() -> int:
    """Longest ahead window; training needs this many M1 after the row."""
    return max(ahead_horizon_m1(pair) for pair in BUNDLE_PAIRS)


def train_label_stop(n: int, *, overlay: bool) -> int:
    """Exclusive end index. Overlay goes to the last M1; train cuts the right edge."""
    if overlay:
        return n
    return n - max_ahead_m1()


def ahead_head_index(pair: tuple[str, str]) -> int:
    """Which ahead readout: 0=D1H4, 1=H4M30, 2=M30M10."""
    return BUNDLE_PAIRS.index(pair)


def ahead_pair_for_tf(tf: str) -> tuple[str, str]:
    """Chart TF → pair whose junior bar is the next candle of this graph."""
    return {
        "M1": ("M30", "M10"),
        "M10": ("M30", "M10"),
        "M30": ("H4", "M30"),
        "H4": ("D1", "H4"),
        "D1": ("D1", "H4"),
    }[tf]


N_AHEAD_HEADS = len(BUNDLE_PAIRS)
_AHEAD_W = tuple(f"Wh{k}" for k in range(N_AHEAD_HEADS))
_AHEAD_B = tuple(f"bh{k}" for k in range(N_AHEAD_HEADS))
_MLP_PARAMS = ("W1", "b1", "W2", "b2", "Wr", "br") + _AHEAD_W + _AHEAD_B
POINT_TFS = ("M10", "M30")
FUT_TRAIN_REPEAT = 4
REGIME_EMA = 8
REGIME_NAMES = ("flat", "impulse", "pullback")
ACTION_NAMES = ("none", "buy_in", "sell_in", "buy_out", "sell_out")
AHEAD_NAMES = ("ahead_flat", "ahead_up", "ahead_down")
SETUP_NAMES = ("none", "buy", "sell", "buy1", "sell1", "buy2", "sell2")
_NUM_FIELDS = (
    ("current", "rpm"),
    ("current", "ema"),
    ("current", "d_rpm"),
    ("current", "d_ema"),
    ("small", "rpm"),
    ("small", "ema"),
    ("small", "hist"),
    ("small", "d_rpm"),
    ("middle", "rpm"),
    ("middle", "ema"),
    ("middle", "hist"),
    ("hist", "hist"),
    ("hist", "d_hist"),
)
_PARENT = {"d_rpm": "rpm", "d_ema": "ema", "d_hist": "hist"}
_ZERO = {"below_0": -1.0, "near_0": 0.0, "above_0": 1.0}
_EMA = {"below_ema": -1.0, "near_ema": 0.0, "above_ema": 1.0}
_HIST_DIR = {"hist_shrinking": -1.0, "hist_growing": 1.0}
# nums + 8 marks + setups + miss_hist_buy/sell + pack_bias + layer_div_buy/sell + pack_ok
TF_DIM = len(_NUM_FIELDS) + 8 + len(SETUP_NAMES) + 5 + 1
# кадр одной связки = цепочка старшего ТФ (3 пачки) + цепочка младшего (3 пачки)
FRAME_DIM = TF_DIM * CHAIN_BARS * 2
IN_DIM = FRAME_DIM


def weights_path(dest_dir: Path | None = None) -> Path:
    return (dest_dir or NET_DIR) / WEIGHTS_NAME


def _z(pack: dict, layer: str, key: str, scales: dict) -> float:
    val = (pack.get(layer) or {}).get(key)
    if val is None:
        return 0.0
    parent = _PARENT.get(key, key)
    scale = scales.get(f"{layer}.{parent}") or 1.0
    return float(val) / scale


def _slope_dir(slope: str) -> float:
    if slope.startswith("rising"):
        return 1.0
    if slope.startswith("falling"):
        return -1.0
    return 0.0


def _ema_older(packs: list[dict], idx: int, layer: str) -> float | None:
    j = idx - EMA_TREND_BARS
    if j < 0:
        return None
    return (packs[j].get(layer) or {}).get("ema")


def _layer_tags(nums: dict, prev: dict | None, rpm_scale: float, ema_scale: float, older_ema) -> dict:
    prev = prev or {}
    rpm = nums.get("rpm")
    ema = nums.get("ema")
    vs0 = _side(rpm, rpm_scale, NEAR_ZERO)
    vs_ema = _vs_ema(rpm, ema, rpm_scale)
    slope = _slope_tag(rpm, prev.get("rpm"), ema, rpm_scale)
    ema_vs0, ema_slope = _ema_state(ema, prev.get("ema"), ema_scale)
    ema_trend = "na"
    if ema is not None and older_ema is not None:
        ema_trend = _slope_only(ema, older_ema, ema_scale)
    return {
        "vs0": vs0,
        "vs_ema": vs_ema,
        "slope": slope,
        "ema_vs0": ema_vs0,
        "ema_slope": ema_slope,
        "ema_trend": ema_trend,
    }


def pack_bias(cur: dict, small: dict, middle: dict, hist: dict) -> float:
    """Pack direction from tags, not from current.vs0 alone. Mean of votes."""
    hist_sign = _ZERO.get(hist.get("hist_sign"), 0.0)
    hist_dir = _HIST_DIR.get(hist.get("hist_dir"), 0.0)
    votes = (
        _slope_dir(str(cur.get("slope") or "")),
        _ZERO.get(cur.get("ema_vs0"), 0.0),
        _ZERO.get(cur.get("vs0"), 0.0),
        _ZERO.get(small.get("vs0"), 0.0),
        _ZERO.get(middle.get("vs0"), 0.0),
        hist_sign,
        hist_sign * hist_dir,
    )
    return float(sum(votes) / len(votes))


def pack_dir_from_bias(bias: float, ok: bool) -> int:
    if not ok:
        return 0
    if bias > 0.05:
        return 1
    if bias < -0.05:
        return -1
    return 0


def miss_hist_buy(small: dict, middle: dict, hist: dict, current: dict) -> bool:
    """H4 buy body without red growing hist, or leftover after lift."""
    if buy_hist(hist):
        return False
    if buy_body(small, middle, current):
        return True
    return (
        hist.get("hist_sign") == "below_0"
        and hist.get("hist_dir") == "hist_shrinking"
        and current.get("vs0") != "below_0"
    )


def miss_hist_sell(small: dict, middle: dict, hist: dict, current: dict) -> bool:
    """H4 sell body without green growing hist, or leftover after drop."""
    if sell_hist(hist):
        return False
    if sell_body(small, middle, current):
        return True
    return (
        hist.get("hist_sign") == "above_0"
        and hist.get("hist_dir") == "hist_shrinking"
        and current.get("vs0") != "above_0"
    )


def _h4_refuse_long(h4: dict) -> bool:
    hist = h4["hist"]
    cur = h4["current"]
    if buy_hist(hist):
        return False
    leftover = (
        hist.get("hist_sign") == "below_0"
        and hist.get("hist_dir") == "hist_shrinking"
        and cur.get("vs0") != "below_0"
    )
    if leftover:
        return True
    if not buy_body(h4["small"], h4["middle"], cur):
        return False
    shrinking = hist.get("hist_dir") == "hist_shrinking"
    rising = str(cur.get("slope") or "").startswith("rising")
    return shrinking or rising


def _h4_refuse_short(h4: dict) -> bool:
    hist = h4["hist"]
    cur = h4["current"]
    if sell_hist(hist):
        return False
    leftover = (
        hist.get("hist_sign") == "above_0"
        and hist.get("hist_dir") == "hist_shrinking"
        and cur.get("vs0") != "above_0"
    )
    if leftover:
        return True
    if not sell_body(h4["small"], h4["middle"], cur):
        return False
    shrinking = hist.get("hist_dir") == "hist_shrinking"
    falling = str(cur.get("slope") or "").startswith("falling")
    return shrinking or falling


def hist_refuse_side(d1_dir: int, h4: dict | None, m1_dir: int) -> int:
    """+1 long / -1 short: D1 pack already that way, H4 never printed hist.

    Combo buy/sell stay as they are. This is the missing hist, not a setup.
    """
    if h4 is None or d1_dir == 0:
        return 0
    if d1_dir > 0 and m1_dir >= 0 and _h4_refuse_long(h4):
        return 1
    if d1_dir < 0 and m1_dir <= 0 and _h4_refuse_short(h4):
        return -1
    return 0


def _middle_holds_long(middle: dict) -> bool:
    if middle.get("vs0") != "above_0":
        return False
    if middle.get("vs_ema") not in ("above_ema", "near_ema"):
        return False
    slope = str(middle.get("slope") or "")
    trend = middle.get("ema_trend") or ""
    return slope.startswith("rising") or slope.startswith("flat") or trend in ("rising", "flat")


def _middle_holds_short(middle: dict) -> bool:
    if middle.get("vs0") != "below_0":
        return False
    if middle.get("vs_ema") not in ("below_ema", "near_ema"):
        return False
    slope = str(middle.get("slope") or "")
    trend = middle.get("ema_trend") or ""
    return slope.startswith("falling") or slope.startswith("flat") or trend in ("falling", "flat")


def _small_down_in_plus(small: dict) -> bool:
    vs0 = small.get("vs0")
    if vs0 not in ("above_0", "near_0", "below_0"):
        return False
    if vs0 == "above_0" and small.get("vs_ema") != "below_ema":
        return False
    slope = str(small.get("slope") or "")
    trend = small.get("ema_trend") or ""
    return slope.startswith("falling") or slope.startswith("flat_below_ema") or trend == "falling"


def _small_up_in_minus(small: dict) -> bool:
    vs0 = small.get("vs0")
    if vs0 not in ("below_0", "near_0", "above_0"):
        return False
    if vs0 == "below_0" and small.get("vs_ema") != "above_ema":
        return False
    slope = str(small.get("slope") or "")
    trend = small.get("ema_trend") or ""
    return slope.startswith("rising") or slope.startswith("flat_above_ema") or trend == "rising"


def _current_div_long(cur: dict) -> bool:
    vs0 = cur.get("vs0")
    slope = str(cur.get("slope") or "")
    if vs0 in ("above_0", "near_0") and (slope.startswith("falling") or slope.startswith("flat")):
        return True
    if vs0 in ("below_0", "near_0") and cur.get("vs_ema") == "below_ema":
        return True
    return False


def _current_div_short(cur: dict) -> bool:
    vs0 = cur.get("vs0")
    slope = str(cur.get("slope") or "")
    if vs0 in ("below_0", "near_0") and (slope.startswith("rising") or slope.startswith("flat")):
        return True
    if vs0 in ("above_0", "near_0") and cur.get("vs_ema") == "above_ema":
        return True
    return False


def layer_div_side(window: list[dict]) -> int:
    """+1 buy / -1 sell: small vs middle divergence + shrinking hist + current.

    Combo buy/sell unchanged. Window = last 1..LOOK tagged packs of one TF.
    """
    if not window:
        return 0
    now = window[-1]
    n_down = sum(1 for item in window if _small_down_in_plus(item["small"]))
    n_up = sum(1 for item in window if _small_up_in_minus(item["small"]))
    hist = now["hist"]
    cur = now["current"]
    middle = now["middle"]
    if (
        _middle_holds_long(middle)
        and n_down >= LAYER_DIV_MIN
        and hist.get("hist_sign") == "above_0"
        and hist.get("hist_dir") == "hist_shrinking"
        and cur.get("ema_vs0") == "above_0"
        and _current_div_long(cur)
    ):
        return 1
    if (
        _middle_holds_short(middle)
        and n_up >= LAYER_DIV_MIN
        and hist.get("hist_sign") == "below_0"
        and hist.get("hist_dir") == "hist_shrinking"
        and cur.get("ema_vs0") == "below_0"
        and _current_div_short(cur)
    ):
        return -1
    return 0


def _tagged_window(packs: list[dict], idx: int, scales: dict, look: int = LAYER_DIV_LOOK) -> list[dict]:
    out: list[dict] = []
    for j in range(max(0, idx - look + 1), idx + 1):
        prev = packs[j - 1] if j else None
        tagged = tagged_pack(packs[j], prev, packs, j, scales)
        if tagged is not None:
            out.append(tagged)
    return out


def layer_div_at(layers: list[dict | None], idx: int | None, look: int = LAYER_DIV_LOOK) -> int:
    if idx is None or idx < 0 or idx >= len(layers):
        return 0
    start = max(0, idx - look + 1)
    window = [item for item in layers[start : idx + 1] if item is not None]
    return layer_div_side(window)


def entry_ok(m1_dir: int, m10_dir: int, m30_dir: int, senior: int, refuse: int) -> bool:
    return pullback_in_impulse(m1_dir, m10_dir, m30_dir, senior) != 0 or refuse != 0


def tagged_pack(pack: dict | None, prev: dict | None, packs: list[dict], idx: int, scales: dict) -> dict | None:
    if pack is None or (pack.get("current") or {}).get("rpm") is None:
        return None
    prev = prev or {}
    cur = _layer_tags(
        pack.get("current") or {},
        prev.get("current"),
        scales.get("current.rpm") or 1.0,
        scales.get("current.ema") or 1.0,
        _ema_older(packs, idx, "current"),
    )
    small = _layer_tags(
        pack.get("small") or {},
        prev.get("small"),
        scales.get("small.rpm") or 1.0,
        scales.get("small.ema") or 1.0,
        _ema_older(packs, idx, "small"),
    )
    middle = _layer_tags(
        pack.get("middle") or {},
        prev.get("middle"),
        scales.get("middle.rpm") or 1.0,
        scales.get("middle.ema") or 1.0,
        _ema_older(packs, idx, "middle"),
    )
    hist_nums = pack.get("hist") or {}
    hist = {
        "hist_sign": _side(hist_nums.get("hist"), scales.get("hist.hist") or 1.0, NEAR_HIST),
        "hist_dir": _hist_dir(pack.get("hist_raw") or {}),
    }
    ok = pack_tag_count(pack, scales, prev) >= MIN_PACK_TAGS
    return {
        "current": cur,
        "small": small,
        "middle": middle,
        "hist": hist,
        "setup": setup_signal(small, middle, hist, cur),
        "bias": pack_bias(cur, small, middle, hist),
        "ok": ok,
        "z": [_z(pack, layer, key, scales) for layer, key in _NUM_FIELDS],
    }


def pack_setup(pack: dict, prev: dict | None, packs: list[dict], idx: int, scales: dict) -> str:
    tagged = tagged_pack(pack, prev, packs, idx, scales)
    return "none" if tagged is None else tagged["setup"]


def pack_vec(pack: dict | None, prev: dict | None, packs: list[dict], idx: int, scales: dict) -> list[float]:
    """One TF pack → fixed vector. Missing pack is zeros with pack_ok=0."""
    tagged = tagged_pack(pack, prev, packs, idx, scales)
    if tagged is None:
        return [0.0] * TF_DIM
    cur, small, middle, hist = tagged["current"], tagged["small"], tagged["middle"], tagged["hist"]
    out = list(tagged["z"])
    out.extend(
        [
            _ZERO.get(cur["vs0"], 0.0),
            _EMA.get(cur["vs_ema"], 0.0),
            _slope_dir(cur["slope"]),
            _ZERO.get(cur["ema_vs0"], 0.0),
            _ZERO.get(small["vs0"], 0.0),
            _ZERO.get(middle["vs0"], 0.0),
            _ZERO.get(hist["hist_sign"], 0.0),
            _HIST_DIR.get(hist["hist_dir"], 0.0),
        ]
    )
    out.extend(1.0 if tagged["setup"] == name else 0.0 for name in SETUP_NAMES)
    out.append(1.0 if miss_hist_buy(small, middle, hist, cur) else 0.0)
    out.append(1.0 if miss_hist_sell(small, middle, hist, cur) else 0.0)
    out.append(tagged["bias"])
    div = layer_div_side(_tagged_window(packs, idx, scales)) if packs else 0
    out.append(1.0 if div > 0 else 0.0)
    out.append(1.0 if div < 0 else 0.0)
    out.append(1.0 if tagged["ok"] else 0.0)
    if len(out) != TF_DIM:
        raise RuntimeError(f"TF_DIM {TF_DIM} != {len(out)}")
    return out


def _fill_replay_vecs(book: dict) -> None:
    """Closed-slot vectors plus forming vector at each M1."""
    packs = book["packs"]
    scales = book["scales"]
    closed_vecs: list[list[float]] = []
    for i, pack in enumerate(packs):
        prev = packs[i - 1] if i else None
        closed_vecs.append(pack_vec(pack, prev, packs, i, scales))
    book["closed_vecs"] = closed_vecs
    m1_packs = book.get("m1_packs")
    m1_slot = book.get("m1_slot")
    if m1_packs is None or m1_slot is None:
        return
    m1_vecs: list[list[float]] = []
    for pack, slot in zip(m1_packs, m1_slot):
        idx = 0 if slot is None else slot
        prefix = packs[:idx]
        series = prefix + ([pack] if pack is not None else [])
        prev = prefix[-1] if prefix else None
        m1_vecs.append(pack_vec(pack, prev, series, len(prefix), scales))
    book["m1_vecs"] = m1_vecs


def _tf_book(raw: dict, tf: str) -> dict | None:
    m1 = raw.get("M1") or []
    if tf == "M1":
        if not m1:
            return None
        return tf_numeric(m1, "M1")
    book = replay_tf_book(m1, tf, csv=raw.get(tf) or [])
    if not book:
        return None
    _fill_replay_vecs(book)
    return book


def build_books(raw: dict[str, list[Bar]]) -> dict[str, dict]:
    """M1 as loaded; M10/M30/H4/D1 from M1 (forming at each minute, CSV only at close)."""
    books: dict[str, dict] = {}
    for tf in NET_TFS:
        book = _tf_book(raw, tf)
        if book:
            books[tf] = book
    return books


def _tagged_forming(book: dict | None, m1_i: int) -> dict | None:
    if book is None:
        return None
    packs_m1 = book.get("m1_packs")
    slots = book.get("m1_slot")
    if packs_m1 is None or slots is None:
        return None
    if m1_i < 0 or m1_i >= len(packs_m1):
        return None
    pack = packs_m1[m1_i]
    slot = slots[m1_i] if m1_i < len(slots) else None
    idx = 0 if slot is None else slot
    closed = book.get("packs") or []
    prefix = closed[:idx]
    series = prefix + ([pack] if pack is not None else [])
    prev = prefix[-1] if prefix else None
    return tagged_pack(pack, prev, series, len(prefix), book["scales"])


def _div_at_m1(book: dict | None, closed_tagged: list[dict | None], m1_i: int) -> int:
    if book is None:
        return 0
    slots = book.get("m1_slot")
    if slots is None or m1_i < 0 or m1_i >= len(slots) or slots[m1_i] is None:
        return 0
    slot = slots[m1_i]
    forming = _tagged_forming(book, m1_i)
    start = max(0, slot - LAYER_DIV_LOOK + 1)
    window = [item for item in closed_tagged[start:slot] if item is not None]
    if forming is not None:
        window.append(forming)
    return layer_div_side(window)


def _refuse_series(
    books: dict[str, dict],
    align: dict[str, list[int | None]],
    m1_dir: list[int],
    n: int,
) -> list[int]:
    d1_book = books.get("D1")
    h4_book = books.get("H4")
    replay = any(book is not None and book.get("m1_packs") is not None for book in (d1_book, h4_book))
    d1_layers = _precompute_tagged(d1_book) if d1_book else []
    h4_layers = _precompute_tagged(h4_book) if h4_book else []
    d1_idx = align.get("D1") or [None] * n
    h4_idx = align.get("H4") or [None] * n
    out: list[int] = []
    for i in range(n):
        if replay:
            d1 = _tagged_forming(d1_book, i)
            h4 = _tagged_forming(h4_book, i)
        else:
            d1 = _tagged_at(d1_layers, d1_idx[i] if i < len(d1_idx) else None)
            h4 = _tagged_at(h4_layers, h4_idx[i] if i < len(h4_idx) else None)
        d1_dir = pack_dir_from_bias(d1["bias"], d1["ok"]) if d1 else 0
        out.append(hist_refuse_side(d1_dir, h4, m1_dir[i]))
    return out


def _diverge_series(
    books: dict[str, dict],
    align: dict[str, list[int | None]],
    n: int,
) -> list[int]:
    d1_book = books.get("D1")
    h4_book = books.get("H4")
    replay = any(book is not None and book.get("m1_packs") is not None for book in (d1_book, h4_book))
    d1_layers = _precompute_tagged(d1_book) if d1_book else []
    h4_layers = _precompute_tagged(h4_book) if h4_book else []
    d1_idx = align.get("D1") or [None] * n
    h4_idx = align.get("H4") or [None] * n
    out: list[int] = []
    for i in range(n):
        if replay:
            d1s = _div_at_m1(d1_book, d1_layers, i)
            out.append(d1s if d1s else _div_at_m1(h4_book, h4_layers, i))
            continue
        d1s = layer_div_at(d1_layers, d1_idx[i] if i < len(d1_idx) else None)
        if d1s:
            out.append(d1s)
            continue
        out.append(layer_div_at(h4_layers, h4_idx[i] if i < len(h4_idx) else None))
    return out


def _precompute_tagged(book: dict) -> list[dict | None]:
    packs = book["packs"]
    scales = book["scales"]
    out: list[dict | None] = []
    for i, pack in enumerate(packs):
        prev = packs[i - 1] if i else None
        out.append(tagged_pack(pack, prev, packs, i, scales))
    return out


def _tagged_at(layers: list[dict | None], idx: int | None) -> dict | None:
    if idx is None or idx < 0 or idx >= len(layers):
        return None
    return layers[idx]


def _precompute_vecs(book: dict) -> list[list[float]]:
    packs = book["packs"]
    scales = book["scales"]
    vecs: list[list[float]] = []
    for i, pack in enumerate(packs):
        prev = packs[i - 1] if i else None
        vecs.append(pack_vec(pack, prev, packs, i, scales))
    return vecs


def _align_maps(books: dict[str, dict], m1_times: list[datetime]) -> dict[str, list[int | None]]:
    n = len(m1_times)
    out: dict[str, list[int | None]] = {"M1": list(range(n))}
    for tf in NET_TFS:
        if tf == "M1":
            continue
        book = books.get(tf)
        if not book:
            out[tf] = [None] * n
            continue
        slots = book.get("m1_slot")
        if slots is not None:
            out[tf] = list(slots)
            continue
        times = [p["dt"] for p in book["packs"]]
        out[tf] = at_or_before_indices(m1_times, times)
    return out


def _book_vecs(book: dict) -> list[list[float]] | dict:
    if book.get("m1_vecs") is not None and book.get("m1_slot") is not None:
        return {
            "closed": book.get("closed_vecs") or _precompute_vecs(book),
            "forming": book["m1_vecs"],
            "slot": book["m1_slot"],
        }
    return _precompute_vecs(book)


def _overlay_tf_dts(book: dict, tf: str) -> list[datetime]:
    times = [p["dt"] for p in book["packs"]]
    if tf == "M1":
        return times
    last = None
    for bar in reversed(book.get("m1_bars") or []):
        if bar is not None:
            last = bar.dt
            break
    if last is not None and (not times or times[-1] != last):
        return times + [last]
    return times


def _bundles_labeled(
    vecs: dict[str, list[list[float]] | dict],
    align: dict[str, list[int | None]],
    m1_i: int,
) -> list[tuple[tuple[str, str], list[float]]]:
    """Present pair-bundles at this M1, each tagged with its pair."""
    out: list[tuple[tuple[str, str], list[float]]] = []
    for senior, junior in BUNDLE_PAIRS:
        part = _bundle_chain(vecs, align, m1_i, senior, junior)
        if part is not None and len(part) == IN_DIM:
            out.append(((senior, junior), part))
    return out


def _bundles_at(
    vecs: dict[str, list[list[float]] | dict],
    align: dict[str, list[int | None]],
    m1_i: int,
) -> list[list[float]]:
    """Present pair-bundles at this M1. Same layout for every pair (senior×3 + junior×3)."""
    return [part for _pair, part in _bundles_labeled(vecs, align, m1_i)]


def _align_idx(align: dict[str, list[int | None]], m1_i: int, tf: str) -> int | None:
    idxs = align.get(tf) or []
    if m1_i < 0 or m1_i >= len(idxs):
        return None
    return idxs[m1_i]


def _chain_pack_vecs(tf_vecs: list[list[float]], idx: int | None, length: int = CHAIN_BARS) -> list[float] | None:
    """Neighboring packs of one TF ending at idx (forming last). Missing earlier bars are zeros."""
    if idx is None or idx < 0 or idx >= len(tf_vecs):
        return None
    out: list[float] = []
    start = idx - (length - 1)
    for k in range(length):
        j = start + k
        if j < 0:
            out.extend([0.0] * TF_DIM)
        else:
            out.extend(tf_vecs[j])
    if tf_vecs[idx][-1] < 1.0:
        return None
    return out


def _chain_forming(
    closed_vecs: list[list[float]],
    forming_vec: list[float] | None,
    slot_idx: int | None,
    length: int = CHAIN_BARS,
) -> list[float] | None:
    """Two frozen closed neighbors + forming last. Does not use the closed current slot."""
    if forming_vec is None or slot_idx is None:
        return None
    if len(forming_vec) != TF_DIM or forming_vec[-1] < 1.0:
        return None
    out: list[float] = []
    start = slot_idx - (length - 1)
    for k in range(length - 1):
        j = start + k
        if j < 0 or j >= slot_idx or j >= len(closed_vecs):
            out.extend([0.0] * TF_DIM)
        else:
            out.extend(closed_vecs[j])
    out.extend(forming_vec)
    return out


def _chain_from_entry(
    entry: list[list[float]] | dict | None,
    align: dict[str, list[int | None]],
    m1_i: int,
    tf: str,
) -> list[float] | None:
    if entry is None:
        return None
    if isinstance(entry, dict):
        forming = entry.get("forming") or []
        slots = entry.get("slot") or []
        if m1_i < 0 or m1_i >= len(forming) or m1_i >= len(slots):
            return None
        return _chain_forming(entry.get("closed") or [], forming[m1_i], slots[m1_i])
    return _chain_pack_vecs(entry, _align_idx(align, m1_i, tf))


def _bundle_chain(
    vecs: dict[str, list[list[float]] | dict],
    align: dict[str, list[int | None]],
    m1_i: int,
    senior: str,
    junior: str,
) -> list[float] | None:
    senior_chain = _chain_from_entry(vecs.get(senior), align, m1_i, senior)
    junior_chain = _chain_from_entry(vecs.get(junior), align, m1_i, junior)
    if senior_chain is None or junior_chain is None:
        return None
    return senior_chain + junior_chain


def bars_from_m1(m1: list[Bar], period_min: int) -> list[Bar]:
    """OHLC of period_min slots from M1 (M5 and any senior not taken from CSV)."""
    if period_min <= 1:
        return list(m1)
    out: list[Bar] = []
    cur_slot: datetime | None = None
    chunk: list[Bar] = []

    def flush() -> None:
        if not chunk or cur_slot is None:
            return
        out.append(
            Bar(
                dt=cur_slot,
                o=chunk[0].o,
                h=max(b.h for b in chunk),
                l=min(b.l for b in chunk),
                c=chunk[-1].c,
            )
        )

    for bar in m1:
        slot = slot_open(bar.dt, period_min)
        if slot != cur_slot:
            flush()
            cur_slot = slot
            chunk = [bar]
        else:
            chunk.append(bar)
    flush()
    return out


def _tf_dir_at(books: dict[str, dict], align: dict[str, list[int | None]], m1_i: int, tf: str) -> int:
    book = books.get(tf)
    if book is None:
        return 0
    packs_m1 = book.get("m1_packs")
    if packs_m1 is not None:
        if m1_i < 0 or m1_i >= len(packs_m1) or packs_m1[m1_i] is None:
            return 0
        rpm = (packs_m1[m1_i].get("current") or {}).get("rpm")
    else:
        if tf == "M1":
            idx: int | None = m1_i if m1_i < len(book["packs"]) else None
        else:
            idxs = align.get(tf) or []
            idx = idxs[m1_i] if m1_i < len(idxs) else None
        if idx is None or idx < 0 or idx >= len(book["packs"]):
            return 0
        rpm = (book["packs"][idx].get("current") or {}).get("rpm")
    scale = book["scales"].get("current.rpm") or 1.0
    side = _side(rpm, scale, NEAR_ZERO)
    if side == "above_0":
        return 1
    if side == "below_0":
        return -1
    return 0


def _h4_dir(books: dict[str, dict], align: dict[str, list[int | None]], m1_i: int) -> int:
    for tf in ("H4", "M30"):
        direction = _tf_dir_at(books, align, m1_i, tf)
        if direction:
            return direction
    return 0


def pack_agree(m1_dir: int, m10_dir: int, m30_dir: int) -> bool:
    """M10 and M30 packs agree; M1 may be flat but must not oppose."""
    if m10_dir == 0 or m30_dir == 0 or m10_dir != m30_dir:
        return False
    if m1_dir == -m10_dir:
        return False
    return True


def regime_from_dirs(senior: int, m1_dir: int) -> int:
    """Impulse/pullback from senior RPM vs M1, every bar — not from trade outcome."""
    if senior == 0:
        return 0
    if m1_dir == -senior:
        return 2
    return 1


def pullback_in_impulse(m1_dir: int, m10_dir: int, m30_dir: int, senior_dir: int) -> int:
    """+1 long / -1 short: M30 (else H4) impulse, M10 or M1 against. 0 = no dip."""
    trend = m30_dir if m30_dir != 0 else senior_dir
    if trend == 0:
        return 0
    if m10_dir == trend and m1_dir == trend:
        return 0
    if m10_dir == -trend or m1_dir == -trend:
        return trend
    return 0


def _risk_floor(entry: float) -> float:
    return max(abs(entry) * 0.0003, 1e-8)


def swing_stop_levels(n: int, legs: list[dict]) -> tuple[list[float | None], list[float | None]]:
    """Last opposite pivot price, available the bar after the pivot."""
    lows: list[float | None] = [None] * n
    highs: list[float | None] = [None] * n
    events = sorted(
        (
            (leg["end"], "lo" if leg["side"] == "down" else "hi", float(leg["end_px"]))
            for leg in legs
        ),
        key=lambda item: item[0],
    )
    last_lo = None
    last_hi = None
    e = 0
    for i in range(n):
        while e < len(events) and events[e][0] < i:
            _end, kind, px = events[e]
            if kind == "lo":
                last_lo = px
            else:
                last_hi = px
            e += 1
        lows[i] = last_lo
        highs[i] = last_hi
    return lows, highs


def trade_levels(
    side: int,
    i: int,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    swing_lo: list[float | None] | None = None,
    swing_hi: list[float | None] | None = None,
    stop_bars: int = STOP_BARS,
    r_mult: float = R_MULT,
) -> tuple[float, float, float, float] | None:
    if side == 0 or i <= 0 or i >= len(closes):
        return None
    entry = closes[i]
    left = max(0, i - stop_bars)
    if side > 0:
        stop = min(lows[left:i]) if i > left else lows[i]
        if swing_lo and swing_lo[i] is not None:
            stop = min(stop, float(swing_lo[i]))
        risk = entry - stop
        if risk < _risk_floor(entry):
            return None
        return entry, stop, risk, entry + r_mult * risk
    stop = max(highs[left:i]) if i > left else highs[i]
    if swing_hi and swing_hi[i] is not None:
        stop = max(stop, float(swing_hi[i]))
    risk = stop - entry
    if risk < _risk_floor(entry):
        return None
    return entry, stop, risk, entry - r_mult * risk


def trade_hit(
    side: int,
    i: int,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    swing_lo: list[float | None] | None = None,
    swing_hi: list[float | None] | None = None,
    stop_bars: int = STOP_BARS,
    horizon: int = TRADE_HORIZON,
    r_mult: float = R_MULT,
) -> str:
    """win if target prints before stop; same-bar both → loss."""
    lv = trade_levels(side, i, highs, lows, closes, swing_lo, swing_hi, stop_bars, r_mult)
    if lv is None:
        return "none"
    _entry, stop, _risk, target = lv
    last = min(len(closes) - 1, i + horizon)
    for j in range(i + 1, last + 1):
        if side > 0:
            hit_stop = lows[j] <= stop
            hit_tgt = highs[j] >= target
        else:
            hit_stop = highs[j] >= stop
            hit_tgt = lows[j] <= target
        if hit_stop:
            return "loss"
        if hit_tgt:
            return "win"
    return "none"


def walk_exit(
    side: int,
    i: int,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    stop: float,
    risk: float,
    target: float,
    *,
    horizon: int = TRADE_HORIZON,
    m30_dir: list[int] | None = None,
    entry: float | None = None,
) -> tuple[int, str]:
    stop_px = stop
    last = min(len(closes) - 1, i + horizon)
    for j in range(i + 1, last + 1):
        if m30_dir is not None and m30_dir[j] == -side:
            return j, "pack"
        if entry is not None and risk > 0:
            if side > 0 and closes[j] >= entry + risk:
                stop_px = max(stop_px, closes[j] - risk)
            elif side < 0 and closes[j] <= entry - risk:
                stop_px = min(stop_px, closes[j] + risk)
        if side > 0:
            if lows[j] <= stop_px:
                return j, "stop"
            if highs[j] >= target:
                return j, "target"
        else:
            if highs[j] >= stop_px:
                return j, "stop"
            if lows[j] <= target:
                return j, "target"
    return last, "time"


def horizon_flat_threshold(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    bars: int,
    frac: float = FLAT_FRAC,
) -> float:
    """Median max-side path excursion over windows of `bars` M1, times FLAT_FRAC.

    Same idea as 1-bar flat_threshold, but the typical move is this ahead window
    on this instrument — not a single M1 close-to-close.
    """
    n = len(closes)
    need = max(int(bars), 1)
    xs: list[float] = []
    if n >= need + 1:
        for i in range(n - need):
            px = closes[i]
            if px <= 0:
                continue
            last = i + need
            up = max(highs[j] for j in range(i + 1, last + 1)) - px
            dn = px - min(lows[j] for j in range(i + 1, last + 1))
            xs.append(max(up, dn) / px * 100.0)
    if xs:
        typical = float(median(xs))
        if typical > 0:
            return typical * frac
    one = flat_threshold(closes)
    return one if one > 0 else FLAT_PCT


def ahead_flat_by_pair(
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> dict[tuple[str, str], float]:
    """Per-bundle flat % for ahead_label (10 / 30 / 240 M1)."""
    by_bars: dict[int, float] = {}
    out: dict[tuple[str, str], float] = {}
    for pair in BUNDLE_PAIRS:
        bars = ahead_horizon_m1(pair)
        if bars not in by_bars:
            by_bars[bars] = horizon_flat_threshold(highs, lows, closes, bars)
        out[pair] = by_bars[bars]
    return out


def ahead_label(
    i: int,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    flat_pct: float,
    bars: int = AHEAD_BARS,
) -> int:
    """Next `bars` of this series from i: what the path can do. 0 flat, 1 up, 2 down. Not an input."""
    n = len(closes)
    last = min(n - 1, i + bars)
    if last <= i or i < 0 or closes[i] <= 0:
        return 0
    px = closes[i]
    up_exc = max(highs[j] for j in range(i + 1, last + 1)) - px
    dn_exc = px - min(lows[j] for j in range(i + 1, last + 1))
    thresh = px * (flat_pct / 100.0)
    if thresh <= 0:
        thresh = px * 0.001
    if up_exc < thresh and dn_exc < thresh:
        return 0
    if up_exc >= dn_exc:
        return 1
    return 2


def pair_ahead_labels(
    i: int,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    pair_flat: dict[tuple[str, str], float],
    fallback: float,
) -> dict[tuple[str, str], int] | None:
    """All three horizon outcomes at this M1, or None if the longest window does not fit."""
    if i + max_ahead_m1() >= len(closes):
        return None
    out: dict[tuple[str, str], int] = {}
    for pair in BUNDLE_PAIRS:
        out[pair] = ahead_label(
            i,
            highs,
            lows,
            closes,
            pair_flat.get(pair, fallback),
            bars=ahead_horizon_m1(pair),
        )
    return out


def action_probs_from_aheads(labels: dict[tuple[str, str], int]) -> tuple[float, float, float]:
    """P(flat), P(up), P(down) = share of the three ahead outcomes."""
    n = float(len(BUNDLE_PAIRS))
    p = [0.0, 0.0, 0.0]
    for pair in BUNDLE_PAIRS:
        p[int(labels[pair]) % 3] += 1.0 / n
    return p[0], p[1], p[2]


def action_from_aheads(labels: dict[tuple[str, str], int]) -> int:
    """Fact vote on train logs: 0 none, 1 buy_in, 2 sell_in. Tie → none. Not a Wa target."""
    p_flat, p_up, p_down = action_probs_from_aheads(labels)
    probs = (p_flat, p_up, p_down)
    best = int(max(range(3), key=lambda k: probs[k]))
    if probs.count(probs[best]) > 1:
        return 0
    return best


def mix_ahead_probs(
    ph_by_pair: dict[tuple[str, str], np.ndarray],
) -> np.ndarray | None:
    """Equal mean of the three ahead softmaxes. None if a pair is missing."""
    vecs: list[np.ndarray] = []
    for pair in BUNDLE_PAIRS:
        got = ph_by_pair.get(pair)
        if got is None:
            return None
        vecs.append(np.asarray(got, dtype=np.float32).reshape(-1)[:3])
    return np.mean(np.stack(vecs, axis=0), axis=0)


def pa_from_ahead_mix(ph_mean: np.ndarray | None) -> np.ndarray:
    """CSV action columns from the three-head mean. buy_out/sell_out stay 0. Not Wa."""
    pa = np.zeros(len(ACTION_NAMES), dtype=np.float32)
    if ph_mean is None:
        pa[0] = 1.0
        return pa
    pa[0] = float(ph_mean[0])
    pa[1] = float(ph_mean[1])
    pa[2] = float(ph_mean[2])
    return pa


def action_from_ph_mean(ph_mean: np.ndarray | None) -> str:
    """Point from equal mean of three ahead probabilities. No Wa, setup, veto, or exits."""
    if ph_mean is None:
        return "none"
    p = [float(ph_mean[0]), float(ph_mean[1]), float(ph_mean[2])]
    best = int(max(range(3), key=lambda k: p[k]))
    if p.count(p[best]) > 1 or best == 0:
        return "none"
    other = p[1] if best == 2 else p[2]
    if p[best] < ACTION_MIN or p[best] < other + ACTION_GAP:
        return "none"
    return "buy_in" if best == 1 else "sell_in"


def label_trades(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    senior: list[int],
    m1_dir: list[int],
    m10_dir: list[int],
    m30_dir: list[int],
    swing_lo: list[float | None] | None = None,
    swing_hi: list[float | None] | None = None,
    refuse: list[int] | None = None,
) -> tuple[list[int], list[int]]:
    """Regime every bar from senior vs M1. In: pullback-in-impulse or H4 hist-refuse, + 2R."""
    n = len(closes)
    y_r = [regime_from_dirs(senior[i], m1_dir[i]) for i in range(n)]
    y_a = [0] * n
    i = STOP_BARS
    while i < n - 2:
        side = pullback_in_impulse(m1_dir[i], m10_dir[i], m30_dir[i], senior[i])
        if side == 0 and refuse is not None:
            side = refuse[i]
        if side == 0 or trade_hit(side, i, highs, lows, closes, swing_lo=swing_lo, swing_hi=swing_hi) != "win":
            i += 1
            continue
        lv = trade_levels(side, i, highs, lows, closes, swing_lo, swing_hi)
        if lv is None:
            i += 1
            continue
        entry, stop, risk, target = lv
        j, reason = walk_exit(
            side, i, highs, lows, closes, stop, risk, target, m30_dir=m30_dir, entry=entry
        )
        if j <= i or (reason == "stop" and j <= i + 2):
            i += 1
            continue
        y_a[i] = 1 if side > 0 else 2
        y_a[j] = 3 if side > 0 else 4
        i = j + 1
    return y_r, y_a


def decide_action(
    pr: np.ndarray,
    pa: np.ndarray,
    agree: bool,
    refuse: int = 0,
    ph: np.ndarray | None = None,
) -> str:
    ri = int(pr.argmax())
    if ri == 0 or float(pr[ri]) < POINT_REGIME_MIN:
        return "none"
    ai = int(pa.argmax())
    got = "none"
    if ai != 0 and not (ai in (1, 2) and not agree):
        p = float(pa[ai])
        if p >= ACTION_MIN:
            if ai in (1, 2) and p < float(pa[1] if ai == 2 else pa[2]) + ACTION_GAP:
                got = "none"
            elif ai in (3, 4) and p < float(pa[3] if ai == 4 else pa[4]) + ACTION_GAP:
                got = "none"
            else:
                got = ACTION_NAMES[ai]
    if ph is not None and got in ("buy_in", "sell_in"):
        hi = int(ph.argmax())
        if float(ph[hi]) >= AHEAD_MIN:
            if got == "buy_in" and hi == 2:
                got = "none"
            elif got == "sell_in" and hi == 1:
                got = "none"
    if got != "none":
        return got
    if refuse == 0 or not agree:
        return "none"
    if ph is not None:
        hi = int(ph.argmax())
        if float(ph[hi]) >= AHEAD_MIN:
            if refuse > 0 and hi == 2:
                return "none"
            if refuse < 0 and hi == 1:
                return "none"
    if refuse > 0:
        if float(pa[3]) > float(pa[1]):
            return "none"
        return "buy_in"
    if float(pa[4]) > float(pa[2]):
        return "none"
    return "sell_in"


def strip_action_points(row: dict) -> dict:
    out = dict(row)
    out["action"] = "none"
    return out


def _leg_map(n: int, legs: list[dict]) -> list[dict | None]:
    out: list[dict | None] = [None] * n
    for leg in legs:
        for i in range(leg["start"], min(leg["end"] + 1, n)):
            out[i] = leg
    return out


def label_bar(leg: dict | None, i: int, senior_dir: int, entry_bars: int = 3, exit_bars: int = 3) -> tuple[int, int]:
    """regime, action indices. Geometry of the M1 leg, not mark setups."""
    if leg is None or senior_dir == 0:
        return 0, 0
    up = leg["side"] == "up"
    if up and senior_dir < 0:
        regime = 2
    elif (not up) and senior_dir > 0:
        regime = 2
    else:
        regime = 1
    start, end = leg["start"], leg["end"]
    span = end - start + 1
    n_in = 1 if span < 6 else min(entry_bars, max(1, span // 5))
    n_out = 1 if span < 6 else min(exit_bars, max(1, span // 5))
    if i <= start + n_in - 1:
        action = 1 if up else 2
    elif i >= end - n_out + 1:
        action = 3 if up else 4
    else:
        action = 0
    return regime, action


def window_indices(end: int, window: int = 6, step: int = STRIDE) -> list[int]:
    """M1 sample positions ending at `end`, spaced by `step` (helper, not net input)."""
    return [end - (window - 1 - k) * step for k in range(window)]


def _chunk_at(
    frames: list[list[float] | None],
    end: int,
) -> list[float] | None:
    if end < 0 or end >= len(frames):
        return None
    fr = frames[end]
    if fr is None or len(fr) != IN_DIM:
        return None
    return fr


def _sample_indices(start: int, stop: int, stride: int = STRIDE) -> list[int]:
    """Every M1 from start to stop (stride=1)."""
    last = stop - 1
    if last < start:
        return []
    return list(range(start, stop, stride))


def instrument_samples(
    sec: str,
    class_code: str,
    *,
    data_dir=None,
    stride: int = STRIDE,
    overlay: bool = False,
) -> dict | None:
    raw = load_instrument(
        sec,
        class_code,
        data_dir or BARS_DIR,
        tfs=KNOWN_TFS,
        max_bars=ODDS_MAX_BARS,
        skip_missing=True,
    )
    if not (raw.get("M1") and raw.get("M10") and raw.get("M30") and raw.get("H4") and raw.get("D1")):
        return None
    books = build_books(raw)
    m1 = books.get("M1")
    if not m1 or len(m1["packs"]) < WARMUP["M1"] + 2:
        return None
    vecs = {tf: _book_vecs(book) for tf, book in books.items()}
    n = min(len(m1["packs"]), len(m1["bars"]))
    if n < WARMUP["M1"] + 2:
        return None
    bars = m1["bars"][:n]
    m1_times = [p["dt"] for p in m1["packs"][:n]]
    align = _align_maps(books, m1_times)
    closes = [b.c for b in bars]
    highs = [b.h for b in bars]
    lows = [b.l for b in bars]
    senior = [_h4_dir(books, align, i) for i in range(n)]
    m1_dir = [_tf_dir_at(books, align, i, "M1") for i in range(n)]
    m10_dir = [_tf_dir_at(books, align, i, "M10") for i in range(n)]
    m30_dir = [_tf_dir_at(books, align, i, "M30") for i in range(n)]
    refuse = _refuse_series(books, align, m1_dir, n)
    diverge = _diverge_series(books, align, n)
    extra = [r if r else d for r, d in zip(refuse, diverge)]
    y_r = [regime_from_dirs(senior[i], m1_dir[i]) for i in range(n)]
    flat_pct = flat_threshold(closes)
    pair_flat: dict[tuple[str, str], float] = {}
    if not overlay:
        pair_flat = ahead_flat_by_pair(highs, lows, closes)
    xs: list[list[float]] = []
    yr: list[int] = []
    ya: list[int] = []
    yh: list[int] = []
    yhh: list[int] = []
    dts: list[datetime] = []
    agrees: list[bool] = []
    refuses: list[int] = []
    overlay_bundles: list[list[list[float]]] = []
    overlay_labeled: list[list[tuple[tuple[str, str], list[float]]]] = []
    start = WARMUP["M1"]
    stop = train_label_stop(n, overlay=overlay)
    if overlay:
        for i in _sample_indices(start, stop, stride):
            labeled = _bundles_labeled(vecs, align, i)
            if not labeled:
                continue
            overlay_labeled.append(labeled)
            overlay_bundles.append([part for _pair, part in labeled])
            xs.append(labeled[0][1])
            yr.append(y_r[i])
            ya.append(0)
            yh.append(0)
            yhh.append(ahead_head_index(labeled[0][0]))
            dts.append(m1_times[i])
            agrees.append(entry_ok(m1_dir[i], m10_dir[i], m30_dir[i], senior[i], extra[i]))
            refuses.append(extra[i])
    else:
        for i in _sample_indices(start, stop, stride):
            labels = pair_ahead_labels(i, highs, lows, closes, pair_flat, flat_pct)
            if labels is None:
                continue
            y_act = action_from_aheads(labels)
            for pair in BUNDLE_PAIRS:
                senior_tf, junior_tf = pair
                part = _bundle_chain(vecs, align, i, senior_tf, junior_tf)
                if part is None or len(part) != IN_DIM:
                    continue
                xs.append(part)
                yr.append(y_r[i])
                ya.append(y_act)
                yh.append(labels[pair])
                yhh.append(ahead_head_index(pair))
                dts.append(m1_times[i])
                agrees.append(entry_ok(m1_dir[i], m10_dir[i], m30_dir[i], senior[i], extra[i]))
                refuses.append(extra[i])
    if not xs:
        return None
    last_i = n - 1
    live_labeled = _bundles_labeled(vecs, align, last_i)
    live_bundles = [part for _pair, part in live_labeled]
    live_chunk = live_bundles[0] if live_bundles else None
    return {
        "sec": sec,
        "class_code": class_code,
        "X": np.asarray(xs, dtype=np.float32),
        "y_regime": np.asarray(yr, dtype=np.int64),
        "y_action": np.asarray(ya, dtype=np.int64),
        "y_ahead": np.asarray(yh, dtype=np.int64),
        "y_ahead_head": np.asarray(yhh, dtype=np.int64),
        "dts": dts,
        "overlay_bundles": overlay_bundles,
        "overlay_labeled": overlay_labeled,
        "live_bundles": live_bundles,
        "live_labeled": live_labeled,
        "flat_pct": flat_pct,
        "ahead_flat": pair_flat,
        "min_pct": 0.0,
        "n_legs": 0,
        "live": np.asarray(live_chunk, dtype=np.float32) if live_chunk is not None else None,
        "live_dt": m1_times[last_i],
        "live_c": m1["packs"][last_i]["c"],
        "live_agree": entry_ok(
            m1_dir[last_i], m10_dir[last_i], m30_dir[last_i], senior[last_i], extra[last_i]
        ),
        "live_regime": regime_from_dirs(senior[last_i], m1_dir[last_i]),
        "live_refuse": extra[last_i],
        "agree": np.asarray(agrees, dtype=bool),
        "refuse": np.asarray(refuses, dtype=np.int8),
        "tf_dts": {tf: _overlay_tf_dts(book, tf) for tf, book in books.items()},
    }


def softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - np.max(logits, axis=-1, keepdims=True)
    e = np.exp(np.clip(z, -30.0, 30.0))
    return e / np.sum(e, axis=-1, keepdims=True)


class MLP:
    """Trunk + regime + three ahead readouts. No action head."""

    def __init__(self, in_dim: int = IN_DIM, hidden: tuple[int, ...] = HIDDEN, rng=None):
        rng = np.random.default_rng(rng)
        self.in_dim = in_dim
        h1, h2 = hidden
        self.W1 = rng.normal(0.0, (2.0 / in_dim) ** 0.5, (in_dim, h1)).astype(np.float32)
        self.b1 = np.zeros(h1, dtype=np.float32)
        self.W2 = rng.normal(0.0, (2.0 / h1) ** 0.5, (h1, h2)).astype(np.float32)
        self.b2 = np.zeros(h2, dtype=np.float32)
        self.Wr = rng.normal(0.0, (2.0 / h2) ** 0.5, (h2, len(REGIME_NAMES))).astype(np.float32)
        self.br = np.zeros(len(REGIME_NAMES), dtype=np.float32)
        scale = (2.0 / h2) ** 0.5
        for k in range(N_AHEAD_HEADS):
            setattr(self, f"Wh{k}", rng.normal(0.0, scale, (h2, len(AHEAD_NAMES))).astype(np.float32))
            setattr(self, f"bh{k}", np.zeros(len(AHEAD_NAMES), dtype=np.float32))
        self._v = {name: np.zeros_like(getattr(self, name)) for name in _MLP_PARAMS}

    def snapshot(self) -> dict[str, np.ndarray]:
        return {name: getattr(self, name).copy() for name in self._v}

    def restore(self, snap: dict[str, np.ndarray]) -> None:
        for name, value in snap.items():
            setattr(self, name, value)

    def _ahead_logits(self, h2: np.ndarray) -> list[np.ndarray]:
        return [h2 @ getattr(self, f"Wh{k}") + getattr(self, f"bh{k}") for k in range(N_AHEAD_HEADS)]

    def forward(self, x: np.ndarray) -> tuple[np.ndarray, list[np.ndarray], dict]:
        z1 = x @ self.W1 + self.b1
        h1 = np.maximum(z1, 0.0)
        z2 = h1 @ self.W2 + self.b2
        h2 = np.maximum(z2, 0.0)
        r_log = h2 @ self.Wr + self.br
        cache = {"x": x, "z1": z1, "h1": h1, "z2": z2, "h2": h2}
        return r_log, self._ahead_logits(h2), cache

    def predict_proba(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """pr (n,3), dummy pa (n,5) all-none, phs (n, 3 heads, 3 classes). Action is not Wa."""
        r_log, h_logs, _ = self.forward(x)
        phs = np.stack([softmax(h) for h in h_logs], axis=1)
        pa = np.zeros((x.shape[0], len(ACTION_NAMES)), dtype=np.float32)
        pa[:, 0] = 1.0
        return softmax(r_log), pa, phs

    def _sgd(self, name: str, grad: np.ndarray, lr: float) -> None:
        param = getattr(self, name)
        if name.startswith("W"):
            grad = grad + WEIGHT_DECAY * param
        v = self._v[name]
        v *= MOMENTUM
        v += grad
        setattr(self, name, param - lr * v)

    def step(self, x, y_r, y_h, y_hi, w_r, w_h, lr: float) -> float:
        r_log, h_logs, cache = self.forward(x)
        pr = softmax(r_log)
        n = x.shape[0]
        y_hi = np.asarray(y_hi, dtype=np.int64)
        yr = np.zeros_like(pr)
        yh = np.zeros((n, len(AHEAD_NAMES)), dtype=np.float32)
        yr[np.arange(n), y_r] = 1.0
        yh[np.arange(n), y_h] = 1.0
        wr = w_r[y_r][:, None]
        wh = w_h[y_h][:, None]
        dr = ((pr - yr) * wr) / n
        loss_r = float(-np.mean(wr[:, 0] * np.log(np.clip(np.sum(pr * yr, axis=1), 1e-8, 1.0))))
        h2 = cache["h2"]
        d_h2 = dr @ self.Wr.T
        loss_h_sum = 0.0
        for k in range(N_AHEAD_HEADS):
            ph = softmax(h_logs[k])
            mask = y_hi == k
            dhk = np.zeros_like(ph)
            if mask.any():
                dhk[mask] = ((ph[mask] - yh[mask]) * wh[mask]) / n
                nll = np.log(np.clip(np.sum(ph * yh, axis=1), 1e-8, 1.0))
                loss_h_sum += float(-np.sum(wh[mask, 0] * nll[mask]))
            d_h2 = d_h2 + dhk @ getattr(self, f"Wh{k}").T
            self._sgd(f"Wh{k}", h2.T @ dhk, lr)
            self._sgd(f"bh{k}", dhk.sum(axis=0), lr)
        loss_h = loss_h_sum / max(n, 1)
        self._sgd("Wr", h2.T @ dr, lr)
        self._sgd("br", dr.sum(axis=0), lr)
        d_z2 = d_h2 * (cache["z2"] > 0)
        h1 = cache["h1"]
        d_h1 = d_z2 @ self.W2.T
        self._sgd("W2", h1.T @ d_z2, lr)
        self._sgd("b2", d_z2.sum(axis=0), lr)
        d_z1 = d_h1 * (cache["z1"] > 0)
        self._sgd("W1", cache["x"].T @ d_z1, lr)
        self._sgd("b1", d_z1.sum(axis=0), lr)
        return loss_r + loss_h


def _class_weights(y: np.ndarray, n_class: int) -> np.ndarray:
    counts = np.bincount(y, minlength=n_class).astype(np.float64)
    counts = np.maximum(counts, 1.0)
    w = counts.sum() / (n_class * counts)
    return (w / w.mean()).astype(np.float32)


def _split_time(n: int, val_frac: float = VAL_FRAC) -> tuple[np.ndarray, np.ndarray]:
    cut = max(1, int(n * (1.0 - val_frac)))
    return np.arange(cut), np.arange(cut, n)


def _accuracy(pred: np.ndarray, y: np.ndarray) -> float:
    if y.size == 0:
        return 0.0
    return float(np.mean(pred == y))


def _balanced_acc(pred: np.ndarray, y: np.ndarray, n_class: int) -> float:
    rec: list[float] = []
    for cls in range(n_class):
        mask = y == cls
        if not mask.any():
            continue
        rec.append(float(np.mean(pred[mask] == cls)))
    return float(np.mean(rec)) if rec else 0.0


def fit_mlp(
    Xtr: np.ndarray,
    y_r: np.ndarray,
    y_a: np.ndarray,
    y_h: np.ndarray,
    Xva: np.ndarray | None = None,
    yva_r: np.ndarray | None = None,
    yva_a: np.ndarray | None = None,
    yva_h: np.ndarray | None = None,
    *,
    y_hi: np.ndarray | None = None,
    yva_hi: np.ndarray | None = None,
    epochs: int = EPOCHS,
    batch: int = BATCH,
    lr: float = LR,
    rng=None,
) -> tuple[MLP, dict, np.ndarray, np.ndarray]:
    mean = Xtr.mean(axis=0)
    std = np.maximum(Xtr.std(axis=0), 1e-6)
    Ztr = (Xtr - mean) / std
    if y_hi is None:
        y_hi = np.zeros(len(y_h), dtype=np.int64)
    if Xva is None or yva_r is None or len(Xva) == 0:
        Xva, yva_r, yva_a, yva_h, yva_hi = Xtr[-1:], y_r[-1:], y_a[-1:], y_h[-1:], y_hi[-1:]
    if yva_h is None:
        yva_h = y_h[-1:]
    if yva_hi is None:
        yva_hi = y_hi[-1:] if len(y_hi) else np.zeros(len(yva_h), dtype=np.int64)
    Zva = (Xva - mean) / std
    model = MLP(in_dim=Xtr.shape[1], rng=rng)
    w_r = _class_weights(y_r, len(REGIME_NAMES))
    w_h = _class_weights(y_h, len(AHEAD_NAMES))
    gen = np.random.default_rng(rng)
    n = len(Ztr)
    best_score = -1.0
    best_snap = model.snapshot()
    best: dict = {"epoch": 0, "loss": 0.0, "acc_regime": 0.0, "acc_action": 0.0, "acc_ahead": 0.0}
    wait = 0
    for epoch in range(epochs):
        order = gen.permutation(n)
        losses = []
        for s in range(0, n, batch):
            idx = order[s : s + batch]
            losses.append(
                model.step(
                    Ztr[idx],
                    y_r[idx],
                    y_h[idx],
                    y_hi[idx],
                    w_r,
                    w_h,
                    lr * (0.97 ** epoch),
                )
            )
        pr, _pa, phs = model.predict_proba(Zva)
        pred_r = pr.argmax(axis=1)
        hi = np.clip(np.asarray(yva_hi, dtype=np.int64), 0, N_AHEAD_HEADS - 1)
        pred_h = phs[np.arange(len(yva_h)), hi].argmax(axis=1)
        acc_r = _accuracy(pred_r, yva_r)
        acc_h = _accuracy(pred_h, yva_h)
        bal_r = _balanced_acc(pred_r, yva_r, len(REGIME_NAMES))
        bal_h = _balanced_acc(pred_h, yva_h, len(AHEAD_NAMES))
        rec = {
            "epoch": epoch + 1,
            "loss": float(np.mean(losses)),
            "acc_regime": acc_r,
            "acc_action": 0.0,
            "acc_ahead": acc_h,
            "bal_regime": bal_r,
            "bal_action": 0.0,
            "bal_ahead": bal_h,
        }
        print(
            f"  epoch {epoch + 1}/{epochs}  loss={rec['loss']:.3f}  "
            f"val regime={acc_r:.3f} ahead={acc_h:.3f}  "
            f"bal {bal_r:.3f}/{bal_h:.3f}",
            flush=True,
        )
        score = bal_r + 0.6 * bal_h
        if score > best_score + 1e-4:
            best_score = score
            best_snap = model.snapshot()
            best = rec
            wait = 0
        else:
            wait += 1
            if wait >= PATIENCE:
                print(f"  early stop at epoch {epoch + 1}, keep epoch {best['epoch']}", flush=True)
                break
    model.restore(best_snap)
    return model, best, mean, std


def save_net(path: Path, model: MLP, mean: np.ndarray, std: np.ndarray, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "W1": model.W1,
        "b1": model.b1,
        "W2": model.W2,
        "b2": model.b2,
        "Wr": model.Wr,
        "br": model.br,
        "mean": mean,
        "std": std,
        "in_dim": np.array(model.in_dim),
        "n_ahead_heads": np.array(N_AHEAD_HEADS),
        **{f"meta_{k}": np.array(v) for k, v in meta.items()},
    }
    for k in range(N_AHEAD_HEADS):
        payload[f"Wh{k}"] = getattr(model, f"Wh{k}")
        payload[f"bh{k}"] = getattr(model, f"bh{k}")
    np.savez(path, **payload)


def load_net(path: Path | None = None) -> tuple[MLP, np.ndarray, np.ndarray]:
    file = path or weights_path()
    data = np.load(file, allow_pickle=True)
    hidden = (int(data["W1"].shape[1]), int(data["W2"].shape[1]))
    model = MLP(in_dim=int(data["in_dim"]), hidden=hidden)
    if "Wh0" not in data.files:
        raise RuntimeError("net.npz has a single ahead head; run python -m analyzer --train-net")
    for name in _MLP_PARAMS:
        if name not in data.files:
            raise RuntimeError(f"net.npz missing {name}; run python -m analyzer --train-net")
        setattr(model, name, data[name])
    return model, data["mean"], data["std"]


def _require_in_dim(model: MLP) -> None:
    if model.in_dim != IN_DIM:
        raise RuntimeError(
            f"net.npz in_dim={model.in_dim} != {IN_DIM}; run python -m analyzer --train-net"
        )


def train_net(
    sec: str | None = None,
    class_code: str | None = None,
    *,
    data_dir=None,
    dest_dir: Path | None = None,
    epochs: int = EPOCHS,
) -> dict:
    data_root = data_dir or BARS_DIR
    if sec:
        universe = [(sec, class_code or "TQBR")]
    else:
        universe = list_instruments(data_root, class_code=class_code, tfs=KNOWN_TFS)
    print(f"net train instruments={len(universe)}", flush=True)
    items: list[dict] = []
    skipped = 0
    for i, (name, cls) in enumerate(universe, start=1):
        print(f"  [{i}/{len(universe)}] {name} {cls}", flush=True)
        try:
            sample = instrument_samples(name, cls, data_dir=data_root)
        except Exception as exc:
            print(f"    skip: {exc}", flush=True)
            skipped += 1
            continue
        if sample is None:
            skipped += 1
            print("    skip: not enough bars", flush=True)
            continue
        flats = sample.get("ahead_flat") or {}
        f10 = flats.get(("M30", "M10"), sample["flat_pct"])
        f30 = flats.get(("H4", "M30"), sample["flat_pct"])
        f240 = flats.get(("D1", "H4"), sample["flat_pct"])
        ya = sample["y_action"]
        print(
            f"    n={len(sample['X'])} buy_in={int((ya == 1).sum())} "
            f"sell_in={int((ya == 2).sum())} need={max_ahead_m1()} "
            f"flat1={sample['flat_pct']:.3f}% flat10={f10:.3f}% "
            f"flat30={f30:.3f}% flat240={f240:.3f}%",
            flush=True,
        )
        items.append(sample)
    if not items:
        return {"error": "no samples", "skipped": skipped}
    Xtr, Xva, yrtr, yrva, yatr, yava, yhtr, yhva, yhitr, yhiva = [], [], [], [], [], [], [], [], [], []
    for it in items:
        tr, va = _split_time(len(it["X"]))
        heads = it.get("y_ahead_head")
        if heads is None:
            heads = np.zeros(len(it["X"]), dtype=np.int64)
        reps = FUT_TRAIN_REPEAT if it.get("class_code") == "SPBFUT" else 1
        for _ in range(reps):
            Xtr.append(it["X"][tr])
            yrtr.append(it["y_regime"][tr])
            yatr.append(it["y_action"][tr])
            yhtr.append(it["y_ahead"][tr])
            yhitr.append(heads[tr])
        if len(va):
            Xva.append(it["X"][va])
            yrva.append(it["y_regime"][va])
            yava.append(it["y_action"][va])
            yhva.append(it["y_ahead"][va])
            yhiva.append(heads[va])
    Xtr = np.concatenate(Xtr, axis=0)
    y_r = np.concatenate(yrtr)
    y_a = np.concatenate(yatr)
    y_h = np.concatenate(yhtr)
    y_hi = np.concatenate(yhitr)
    Xva_a = np.concatenate(Xva, axis=0) if Xva else Xtr[-1:]
    yva_r = np.concatenate(yrva) if yrva else y_r[-1:]
    yva_a = np.concatenate(yava) if yava else y_a[-1:]
    yva_h = np.concatenate(yhva) if yhva else y_h[-1:]
    yva_hi = np.concatenate(yhiva) if yhiva else y_hi[-1:]
    print(f"dataset train={len(Xtr)} val={len(Xva_a)} dim={Xtr.shape[1]} skipped={skipped}", flush=True)
    model, last, mean, std = fit_mlp(
        Xtr,
        y_r,
        y_a,
        y_h,
        Xva_a,
        yva_r,
        yva_a,
        yva_h,
        y_hi=y_hi,
        yva_hi=yva_hi,
        epochs=epochs,
        rng=7,
    )
    dest = dest_dir or NET_DIR
    path = weights_path(dest)
    save_net(
        path,
        model,
        mean,
        std,
        {
            "n": int(len(Xtr) + len(Xva_a)),
            "instruments": len(items),
            "chain": CHAIN_BARS,
            "stride": STRIDE,
            "ahead_heads": N_AHEAD_HEADS,
            "ahead_m30m10": ahead_horizon_m1(("M30", "M10")),
            "ahead_h4m30": ahead_horizon_m1(("H4", "M30")),
            "ahead_d1h4": ahead_horizon_m1(("D1", "H4")),
            "action_from_aheads": 1,
            "ahead_need": max_ahead_m1(),
            "no_wa": 1,
        },
    )
    print(f"saved {path}", flush=True)
    return {
        "path": str(path),
        "n": int(len(Xtr) + len(Xva_a)),
        "instruments": len(items),
        "skipped": skipped,
        **last,
    }


def predict_vec(model: MLP, mean: np.ndarray, std: np.ndarray, x: np.ndarray, *, ahead_head: int = 0) -> dict:
    row = ((x - mean) / std).astype(np.float32)[None, :]
    pr, _pa, phs = model.predict_proba(row)
    ph = phs[0, ahead_head]
    return _pred_from_proba(pr[0], pa_from_ahead_mix(ph), ph)


def _pred_from_proba(pr: np.ndarray, pa: np.ndarray, ph: np.ndarray) -> dict:
    ri = int(pr.argmax())
    hi = int(ph.argmax())
    return {
        "regime": REGIME_NAMES[ri],
        "action": action_from_ph_mean(pa[:3] if pa is not None and len(pa) >= 3 else None),
        "ahead": AHEAD_NAMES[hi],
        "regime_p": {REGIME_NAMES[i]: float(pr[i]) for i in range(len(REGIME_NAMES))},
        "action_p": {ACTION_NAMES[i]: float(pa[i]) if i < len(pa) else 0.0 for i in range(len(ACTION_NAMES))},
        "ahead_p": {AHEAD_NAMES[i]: float(ph[i]) for i in range(len(AHEAD_NAMES))},
    }


def _run_labeled(
    model: MLP,
    mean: np.ndarray,
    std: np.ndarray,
    labeled: list[tuple[tuple[str, str], list[float] | np.ndarray]],
) -> tuple[np.ndarray, np.ndarray, dict[tuple[str, str], np.ndarray]] | None:
    """Forward each present bundle. Ahead stays per pair. Action mix is from ph, not Wa."""
    prs: list[np.ndarray] = []
    ph_by_pair: dict[tuple[str, str], np.ndarray] = {}
    for pair, raw in labeled:
        x = np.asarray(raw, dtype=np.float32)
        if x.ndim != 1 or x.shape[0] != IN_DIM:
            continue
        pr, _pa, phs = model.predict_proba(((x - mean) / std).astype(np.float32)[None, :])
        prs.append(pr[0])
        ph_by_pair[pair] = phs[0, ahead_head_index(pair)]
    if not prs:
        return None
    mixed = mix_ahead_probs(ph_by_pair)
    return (
        np.mean(np.stack(prs, axis=0), axis=0),
        pa_from_ahead_mix(mixed),
        ph_by_pair,
    )


def _ph_for_tf(ph_by_pair: dict[tuple[str, str], np.ndarray], tf: str) -> np.ndarray | None:
    pair = ahead_pair_for_tf(tf)
    if pair in ph_by_pair:
        return ph_by_pair[pair]
    return None


def _mix_proba(
    model: MLP,
    mean: np.ndarray,
    std: np.ndarray,
    vecs: list[list[float]] | list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Average action (and unused MLP regime). Ahead is not mixed — use _run_labeled."""
    labeled = list(zip(BUNDLE_PAIRS[: len(vecs)], vecs))
    run = _run_labeled(model, mean, std, labeled)
    if run is None:
        return None
    pr, pa, ph_by = run
    ph = _ph_for_tf(ph_by, "M1")
    if ph is None and ph_by:
        ph = next(iter(ph_by.values()))
    if ph is None:
        return None
    return pr, pa, ph


def predict_mix(
    model: MLP,
    mean: np.ndarray,
    std: np.ndarray,
    vecs: list[list[float]] | list[np.ndarray],
    *,
    labeled: list[tuple[tuple[str, str], list[float] | np.ndarray]] | None = None,
    ahead_tf: str = "M1",
) -> dict | None:
    run = _run_labeled(model, mean, std, labeled) if labeled is not None else None
    if run is None:
        mixed = _mix_proba(model, mean, std, vecs)
        if mixed is None:
            return None
        pr, pa, ph = mixed
        return _pred_from_proba(pr, pa, ph)
    pr, pa, ph_by = run
    ph = _ph_for_tf(ph_by, ahead_tf)
    if ph is None and ph_by:
        ph = next(iter(ph_by.values()))
    if ph is None:
        return None
    return _pred_from_proba(pr, pa, ph)


def predict_instrument(sec: str, class_code: str = "TQBR", *, data_dir=None, dest_dir=None) -> dict:
    path = weights_path(dest_dir)
    if not path.is_file():
        return {"sec": sec, "error": f"no weights at {path}; run --train-net"}
    sample = instrument_samples(sec, class_code, data_dir=data_dir, overlay=True)
    if sample is None or sample.get("live") is None:
        return {"sec": sec, "error": "not enough bars for a связка window"}
    model, mean, std = load_net(path)
    _require_in_dim(model)
    live_bundles = sample.get("live_bundles") or ([sample["live"]] if sample.get("live") is not None else [])
    pred = predict_mix(
        model,
        mean,
        std,
        live_bundles,
        labeled=sample.get("live_labeled"),
        ahead_tf="M1",
    )
    if pred is None:
        return {"sec": sec, "error": "no pair-bundle at live bar"}
    return {
        "sec": sec,
        "class_code": class_code,
        "dt": sample["live_dt"],
        "c": sample["live_c"],
        **pred,
    }


def net_csv_path(sec: str, class_code: str, tf: str, dest_dir: Path | None = None) -> Path:
    return (dest_dir or NET_CSV_DIR) / f"{sec}_{class_code}_{tf}.csv"


def _pred_row(
    dt: datetime,
    pr: np.ndarray,
    pa: np.ndarray,
) -> dict:
    """Overlay row. Ahead columns = glued three-head mean (same as buy_in/sell_in)."""
    ri = int(pr.argmax())
    mix = pa[:3] if pa is not None and len(pa) >= 3 else None
    ahead = (
        np.asarray(mix, dtype=np.float32).reshape(-1)[:3]
        if mix is not None
        else np.array([1.0, 0.0, 0.0], dtype=np.float32)
    )
    hi = int(ahead.argmax())
    return {
        "dt": dt,
        "impulse": clip_line(100.0 * float(pr[1])),
        "pullback": clip_line(100.0 * float(pr[2])),
        "flat": clip_line(100.0 * float(pr[0])),
        "buy_in": clip_line(100.0 * float(pa[1] if pa is not None and len(pa) > 1 else 0.0)),
        "sell_in": clip_line(100.0 * float(pa[2] if pa is not None and len(pa) > 2 else 0.0)),
        "buy_out": 0.0,
        "sell_out": 0.0,
        "ahead_flat": clip_line(100.0 * float(ahead[0])),
        "ahead_up": clip_line(100.0 * float(ahead[1])),
        "ahead_down": clip_line(100.0 * float(ahead[2])),
        "action": action_from_ph_mean(mix),
        "regime": REGIME_NAMES[ri],
        "ahead": AHEAD_NAMES[hi],
    }


def _pack_regime_pr(idx: int) -> np.ndarray:
    pr = np.zeros(3, dtype=np.float32)
    pr[int(idx) % 3] = 1.0
    return pr


def _regime_from_pct(impulse: float, pullback: float, flat: float) -> str:
    if impulse >= pullback and impulse >= flat:
        return "impulse"
    if pullback >= flat:
        return "pullback"
    return "flat"


def smooth_regime_rows(rows: list[dict], span: int = REGIME_EMA) -> list[dict]:
    """EMA on pack regime so M30 does not saw 0↔100 each bar."""
    if not rows or span < 2:
        return rows
    alpha = 2.0 / (span + 1)
    ema = None
    keys = ("impulse", "pullback", "flat")
    for row in rows:
        x = [row[k] / 100.0 for k in keys]
        if ema is None:
            ema = x
        else:
            ema = [alpha * xi + (1.0 - alpha) * ei for xi, ei in zip(x, ema)]
        total = sum(ema) or 1.0
        for k, ei in zip(keys, ema):
            row[k] = clip_line(100.0 * ei / total)
        row["regime"] = _regime_from_pct(row["impulse"], row["pullback"], row["flat"])
    return rows


def _overlay_cache(sample: dict, model: MLP, mean: np.ndarray, std: np.ndarray) -> dict:
    pack = sample.get("y_regime")
    labeled_rows = sample.get("overlay_labeled") or []
    bundles = sample.get("overlay_bundles") or []
    runs: list[dict] = []
    for i, dt in enumerate(sample["dts"]):
        if i < len(labeled_rows) and labeled_rows[i]:
            labeled = labeled_rows[i]
        else:
            vecs = bundles[i] if i < len(bundles) else [sample["X"][i]]
            labeled = list(zip(BUNDLE_PAIRS[: len(vecs)], vecs))
        run = _run_labeled(model, mean, std, labeled)
        if run is None:
            continue
        pr_mlp, pa, ph_by = run
        runs.append(
            {
                "dt": dt,
                "i": i,
                "pr_mlp": pr_mlp,
                "pa": pa,
                "ph_by": ph_by,
                "pack": int(pack[i]) if pack is not None and i < len(pack) else None,
            }
        )
    live_labeled = sample.get("live_labeled") or []
    live_bundles = sample.get("live_bundles") or []
    live_run = None
    if live_labeled:
        live_run = _run_labeled(model, mean, std, live_labeled)
    elif live_bundles:
        live_run = _run_labeled(model, mean, std, list(zip(BUNDLE_PAIRS[: len(live_bundles)], live_bundles)))
    return {"runs": runs, "live": live_run}


def _rows_from_overlay_cache(sample: dict, cache: dict, tf: str = "M1") -> list[dict]:
    """M1 overlay rows. Ahead lines are the three-head mean; `tf` is unused."""
    _ = tf
    rows: list[dict] = []
    for run in cache.get("runs") or []:
        pr = _pack_regime_pr(run["pack"]) if run.get("pack") is not None else run["pr_mlp"]
        rows.append(_pred_row(run["dt"], pr, run["pa"]))
    live = cache.get("live")
    if live is not None:
        _pr_mlp, pa, _ph_by = live
        live_pr = _pack_regime_pr(int(sample.get("live_regime", 0)))
        live_row = _pred_row(sample["live_dt"], live_pr, pa)
        if rows and rows[-1]["dt"] == live_row["dt"]:
            rows[-1] = live_row
        else:
            rows.append(live_row)
    return smooth_regime_rows(rows)


def overlay_rows(sample: dict, model: MLP, mean: np.ndarray, std: np.ndarray, *, tf: str = "M1") -> list[dict]:
    return _rows_from_overlay_cache(sample, _overlay_cache(sample, model, mean, std), tf)


def align_net_rows(m1_rows: list[dict], times: list[datetime]) -> list[dict]:
    """One TF bar = mean of M1 overlay inside that slot (not the last M1 0/100 tick)."""
    if not m1_rows or not times:
        return []
    keys = ("impulse", "pullback", "flat", "buy_in", "sell_in", "buy_out", "sell_out", "ahead_flat", "ahead_up", "ahead_down")
    out: list[dict] = []
    j = 0
    prev = 0
    n = len(m1_rows)
    for t in times:
        while j + 1 < n and m1_rows[j + 1]["dt"] <= t:
            j += 1
        if m1_rows[j]["dt"] > t:
            continue
        chunk = m1_rows[prev : j + 1]
        prev = j + 1
        if not chunk:
            continue
        row = dict(chunk[-1])
        row["dt"] = t
        for key in keys:
            row[key] = clip_line(sum(item.get(key, 0.0) for item in chunk) / len(chunk))
        row["regime"] = _regime_from_pct(row["impulse"], row["pullback"], row["flat"])
        au, ad, af = row.get("ahead_up", 0.0), row.get("ahead_down", 0.0), row.get("ahead_flat", 0.0)
        if au >= ad and au >= af:
            row["ahead"] = "ahead_up"
        elif ad >= af:
            row["ahead"] = "ahead_down"
        else:
            row["ahead"] = "ahead_flat"
        row["action"] = chunk[-1]["action"]
        out.append(row)
    return out


def read_net_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        header = fh.readline()
        if not header:
            return []
        for line in fh:
            parts = line.strip().split(";")
            if len(parts) < 9:
                continue
            try:
                dt = datetime.strptime(parts[0], DT_FMT)
                impulse, pullback, flat = float(parts[1]), float(parts[2]), float(parts[3])
                buy_in, sell_in = float(parts[4]), float(parts[5])
                buy_out, sell_out = float(parts[6]), float(parts[7])
                ahead_flat = float(parts[9]) if len(parts) > 9 else 0.0
                ahead_up = float(parts[10]) if len(parts) > 10 else 0.0
                ahead_down = float(parts[11]) if len(parts) > 11 else 0.0
            except ValueError:
                continue
            rows.append(
                {
                    "dt": dt,
                    "impulse": impulse,
                    "pullback": pullback,
                    "flat": flat,
                    "buy_in": buy_in,
                    "sell_in": sell_in,
                    "buy_out": buy_out,
                    "sell_out": sell_out,
                    "action": parts[8],
                    "ahead_flat": ahead_flat,
                    "ahead_up": ahead_up,
                    "ahead_down": ahead_down,
                    "regime": (
                        "impulse"
                        if impulse >= pullback and impulse >= flat
                        else "pullback" if pullback >= flat else "flat"
                    ),
                }
            )
    return rows


def slot_closed(dt: datetime, tf: str, clock: datetime) -> bool:
    return dt + timedelta(minutes=PERIOD_MIN.get(tf, 1)) <= clock


def freeze_closed_rows(
    old: list[dict],
    new: list[dict],
    tf: str,
    clock: datetime,
) -> list[dict]:
    """Keep CSV values for bars that already closed; refresh only the forming slot."""
    old_map = {row["dt"]: row for row in old}
    out: list[dict] = []
    seen: set[datetime] = set()
    for row in new:
        prev = old_map.get(row["dt"])
        if prev is not None and slot_closed(row["dt"], tf, clock):
            out.append(prev)
        else:
            out.append(row)
        seen.add(row["dt"])
    for row in old:
        if row["dt"] not in seen and slot_closed(row["dt"], tf, clock):
            out.append(row)
    out.sort(key=lambda item: item["dt"])
    return out


def write_net_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        fh.write("datetime;impulse;pullback;flat;buy_in;sell_in;buy_out;sell_out;action;ahead_flat;ahead_up;ahead_down\n")
        for row in rows:
            stamp = format_odds_dt(row["dt"]) if isinstance(row["dt"], datetime) else str(row["dt"])
            fh.write(
                f"{stamp};{row['impulse']:.2f};{row['pullback']:.2f};{row['flat']:.2f};"
                f"{row['buy_in']:.2f};{row['sell_in']:.2f};{row['buy_out']:.2f};{row['sell_out']:.2f};"
                f"{row['action']};"
                f"{row.get('ahead_flat', 0.0):.2f};{row.get('ahead_up', 0.0):.2f};"
                f"{row.get('ahead_down', 0.0):.2f}\n"
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


def export_net(
    sec: str,
    class_code: str = "TQBR",
    dest_dir: Path | None = None,
    data_dir=None,
    tfs: tuple[str, ...] | None = None,
) -> dict:
    dest = Path(dest_dir or NET_CSV_DIR)
    wpath = weights_path()
    if not wpath.is_file():
        return {"sec": sec, "class_code": class_code, "error": f"no weights at {wpath}; run --train-net"}
    sample = instrument_samples(sec, class_code, data_dir=data_dir, overlay=True)
    if sample is None:
        return {"sec": sec, "class_code": class_code, "error": "not enough bars for a связка window"}
    model, mean, std = load_net(wpath)
    _require_in_dim(model)
    cache = _overlay_cache(sample, model, mean, std)
    m1_rows = _rows_from_overlay_cache(sample, cache)
    chosen = tuple(tf for tf in (tfs or NET_CHART_TFS) if tf in NET_CHART_TFS)
    if not chosen:
        chosen = NET_CHART_TFS
    names = mark_sec_names(sec, class_code, data_dir)
    files: dict[str, str] = {}
    counts: dict[str, dict] = {}
    tf_dts = sample.get("tf_dts") or {}
    clock = sample.get("live_dt") or datetime.min
    for tf in chosen:
        rows = m1_rows if tf == "M1" else align_net_rows(m1_rows, tf_dts.get(tf) or [])
        if tf not in POINT_TFS:
            rows = [strip_action_points(r) for r in rows]
        old: list[dict] = []
        for name in names:
            prev = read_net_csv(net_csv_path(name, class_code, tf, dest))
            if prev:
                old = prev
                break
        frozen = freeze_closed_rows(old, rows, tf, clock)
        if tf not in POINT_TFS:
            frozen = [strip_action_points(r) for r in frozen]
        written = None
        for name in names:
            path = net_csv_path(name, class_code, tf, dest)
            write_net_csv(path, frozen)
            written = path
        files[tf] = str(written) if written else ""
        last = frozen[-1] if frozen else None
        counts[tf] = {
            "bars": len(frozen),
            "regime": last["regime"] if last else "",
            "action": last["action"] if last else "",
            "impulse": last["impulse"] if last else 0.0,
            "pullback": last["pullback"] if last else 0.0,
            "flat": last["flat"] if last else 0.0,
            "ahead": last.get("ahead", "") if last else "",
            "ahead_up": last.get("ahead_up", 0.0) if last else 0.0,
            "ahead_down": last.get("ahead_down", 0.0) if last else 0.0,
        }
    last = m1_rows[-1] if m1_rows else None
    return {
        "sec": sec,
        "class_code": class_code,
        "dir": str(dest),
        "files": files,
        "counts": counts,
        "dt": last["dt"] if last else None,
        "c": sample["live_c"],
        "regime": last["regime"] if last else "",
        "action": last["action"] if last else "",
        "regime_p": {
            "flat": (last["flat"] if last else 0.0) / 100.0,
            "impulse": (last["impulse"] if last else 0.0) / 100.0,
            "pullback": (last["pullback"] if last else 0.0) / 100.0,
        },
        "action_p": {
            "none": 0.0,
            "buy_in": (last["buy_in"] if last else 0.0) / 100.0,
            "sell_in": (last["sell_in"] if last else 0.0) / 100.0,
            "buy_out": (last["buy_out"] if last else 0.0) / 100.0,
            "sell_out": (last["sell_out"] if last else 0.0) / 100.0,
        },
        "ahead": last.get("ahead", "") if last else "",
        "ahead_p": {
            "ahead_flat": (last.get("ahead_flat", 0.0) if last else 0.0) / 100.0,
            "ahead_up": (last.get("ahead_up", 0.0) if last else 0.0) / 100.0,
            "ahead_down": (last.get("ahead_down", 0.0) if last else 0.0) / 100.0,
        },
    }


def export_all_net(
    class_code: str | None = None,
    dest_dir: Path | None = None,
    data_dir=None,
    tfs: tuple[str, ...] | None = None,
    log=None,
) -> list[dict]:
    emit = log or (lambda msg: print(msg, flush=True))
    items = list_instruments(
        data_dir or BARS_DIR,
        class_code=class_code,
        tfs=("M1", "M10", "M30", "H4"),
    )
    emit(f"net all  n={len(items)}  class={class_code or '*'}")
    reports: list[dict] = []
    for sec, cls in items:
        try:
            report = export_net(sec, cls, dest_dir=dest_dir, data_dir=data_dir, tfs=tfs)
            reports.append(report)
            emit(format_net(report, compact=True))
        except Exception as exc:
            reports.append({"sec": sec, "class_code": cls, "error": str(exc)})
            emit(f"{sec} {cls}  error: {exc}")
    return reports


def watch_net(
    sec: str | None = None,
    class_code: str | None = None,
    dest_dir: Path | None = None,
    data_dir=None,
    tfs: tuple[str, ...] | None = None,
    poll: float = 11.0,
    sleeper=time.sleep,
    stop=None,
    log=None,
) -> int:
    return watch_marks(
        sec,
        class_code,
        dest_dir=dest_dir or NET_CSV_DIR,
        data_dir=data_dir,
        tfs=tfs or NET_WATCH_TFS,
        poll=poll,
        exporter=export_net,
        sleeper=sleeper,
        stop=stop,
        log=log,
        formatter=format_net,
        label="net",
        export_tfs=lambda _dirty: NET_CHART_TFS,
    )


def format_net(report: dict, compact: bool = False) -> str:
    if report.get("error"):
        return f"{report.get('sec', 'net')}  {report['error']}"
    if "instruments" in report and "path" in report:
        return (
            f"net saved {report['path']}  n={report['n']} instruments={report['instruments']}  "
            f"val regime={report.get('acc_regime', 0):.3f} "
            f"ahead={report.get('acc_ahead', 0):.3f}"
        )
    counts = report.get("counts") or {}
    if compact:
        bits = [
            f"{tf} rows={pack['bars']} {pack.get('regime')}/{pack.get('action')}"
            for tf, pack in counts.items()
        ]
        when = report.get("exported_at") or ""
        prefix = f"{when}  " if when else ""
        body = "  ".join(bits)
        line = f"{prefix}{report['sec']} {report['class_code']}"
        return f"{line}  {body}" if body else line
    if counts:
        lines = [f"{report['sec']} {report['class_code']}  net -> {report.get('dir')}"]
        for tf, pack in counts.items():
            lines.append(
                f"  {tf}: rows={pack['bars']}  {pack.get('regime')}  {pack.get('action')}  "
                f"imp={pack.get('impulse', 0):.0f}% pb={pack.get('pullback', 0):.0f}% fl={pack.get('flat', 0):.0f}%  "
                f"ahead={pack.get('ahead', '')}"
            )
            path = (report.get("files") or {}).get(tf)
            if path:
                lines.append(f"       {path}")
        return "\n".join(lines)
    dt = report.get("dt")
    stamp = dt.strftime("%d.%m.%Y %H:%M") if isinstance(dt, datetime) else str(dt)
    rp = report.get("regime_p") or {}
    ap = report.get("action_p") or {}
    rline = "  ".join(f"{k}={100.0 * v:.1f}%" for k, v in rp.items())
    aline = "  ".join(f"{k}={100.0 * v:.1f}%" for k, v in ap.items())
    hp = report.get("ahead_p") or {}
    hline = "  ".join(f"{k}={100.0 * v:.1f}%" for k, v in hp.items())
    return (
        f"{report['sec']} {report.get('class_code')}  {stamp} C={report.get('c', 0):.4f}\n"
        f"  regime  {report.get('regime')}  {rline}\n"
        f"  action  {report.get('action')}  {aline}\n"
        f"  ahead   {report.get('ahead')}  {hline}"
    )
