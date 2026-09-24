# -*- coding: utf-8 -*-
"""Unique H4→M30→M10→M1 state tree, buy/sell rpm-up setups, and >1% price moves."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from analyzer.bars import Bar, load_instrument, BARS_DIR
from analyzer.neighbors import last_closed_indices
from analyzer.price import classify_moves
from analyzer.rpm_current import compute_current
from analyzer.rpm_up import compute_up
from analyzer.settings import hist_layer_names, load_up_settings
from analyzer.states import current_tags, hist_tags, layer_tags

CHART_TFS = ("H4", "M30", "M10", "M1")
LOOK_TFS_M30 = ("M10", "M1")
MIN_MOVE_PCT = 1.0
M30_MOVE_PCT = 3.0
M30_SHOW_LAST = 20
SETUP_LOOKBACK = {"M1": 100, "M10": 50}
SETUP_NAMES = frozenset({"buy", "sell", "buy1", "sell1", "buy2", "sell2"})
WARMUP = {"M1": 200, "M10": 120, "M30": 80, "H4": 60}
PERIOD_MIN = {"M1": 1, "M10": 10, "M30": 30, "H4": 240}


def _tags_match(pack: dict | None, **expect) -> bool:
    if not pack:
        return False
    return all(pack.get(key) == value for key, value in expect.items())


def _buy_stack(small: dict, middle: dict, hist: dict, current: dict | None = None) -> bool:
    down = dict(
        vs0="below_0",
        vs_ema="below_ema",
        ema_vs0="below_0",
        ema_trend="falling",
    )
    return (
        _tags_match(small, **down)
        and _tags_match(middle, **down)
        and _tags_match(hist, hist_sign="below_0", hist_dir="hist_growing")
        and _tags_match(current, vs0="below_0", vs_ema="below_ema", ema_vs0="below_0")
    )


def _sell_stack(small: dict, middle: dict, hist: dict, current: dict | None = None) -> bool:
    up = dict(
        vs0="above_0",
        vs_ema="above_ema",
        ema_vs0="above_0",
        ema_trend="rising",
    )
    return (
        _tags_match(small, **up)
        and _tags_match(middle, **up)
        and _tags_match(hist, hist_sign="above_0", hist_dir="hist_growing")
        and _tags_match(current, vs0="above_0", vs_ema="above_ema", ema_vs0="above_0")
    )


def _buy_m10_cross(current: dict | None, small: dict, middle: dict, hist: dict) -> bool:
    """M10 2026-08-25 17:20: current below 0 rising, small above 0 below EMA falling,
    middle above 0 above EMA falling, hist above 0 shrinking.
    """
    return (
        _tags_match(current, vs0="below_0", vs_ema="below_ema", slope="rising_below_ema")
        and _tags_match(
            small,
            vs0="above_0",
            vs_ema="below_ema",
            slope="falling_below_ema",
            ema_vs0="above_0",
            ema_slope="falling",
        )
        and _tags_match(
            middle,
            vs0="above_0",
            vs_ema="above_ema",
            slope="falling_above_ema",
            ema_vs0="above_0",
            ema_slope="falling",
        )
        and _tags_match(hist, hist_sign="above_0", hist_dir="hist_shrinking")
    )


def _buy2_stack(small: dict, middle: dict, hist: dict, current: dict | None = None) -> bool:
    """Si M1 2026-09-22 18:55: current below 0 below EMA, current EMA above 0 falling;
    small above 0 above EMA rising; middle above 0 below EMA, EMA above 0 falling;
    hist above 0 shrinking.
    """
    return (
        _tags_match(
            current,
            vs0="below_0",
            vs_ema="below_ema",
            ema_vs0="above_0",
            ema_trend="falling",
        )
        and _tags_match(
            small,
            vs0="above_0",
            vs_ema="above_ema",
            ema_vs0="above_0",
            ema_trend="rising",
            slope="rising_above_ema",
        )
        and _tags_match(
            middle,
            vs0="above_0",
            vs_ema="below_ema",
            ema_vs0="above_0",
            ema_trend="falling",
        )
        and _tags_match(hist, hist_sign="above_0", hist_dir="hist_shrinking")
    )


def _sell2_stack(small: dict, middle: dict, hist: dict, current: dict | None = None) -> bool:
    """Mirror of _buy2_stack."""
    return (
        _tags_match(
            current,
            vs0="above_0",
            vs_ema="above_ema",
            ema_vs0="below_0",
            ema_trend="rising",
        )
        and _tags_match(
            small,
            vs0="below_0",
            vs_ema="below_ema",
            ema_vs0="below_0",
            ema_trend="falling",
            slope="falling_below_ema",
        )
        and _tags_match(
            middle,
            vs0="below_0",
            vs_ema="above_ema",
            ema_vs0="below_0",
            ema_trend="rising",
        )
        and _tags_match(hist, hist_sign="below_0", hist_dir="hist_shrinking")
    )


def _sell_m10_cross(current: dict | None, small: dict, middle: dict, hist: dict) -> bool:
    """Mirror of _buy_m10_cross."""
    return (
        _tags_match(current, vs0="above_0", vs_ema="above_ema", slope="falling_above_ema")
        and _tags_match(
            small,
            vs0="below_0",
            vs_ema="above_ema",
            slope="rising_above_ema",
            ema_vs0="below_0",
            ema_slope="rising",
        )
        and _tags_match(
            middle,
            vs0="below_0",
            vs_ema="below_ema",
            slope="rising_below_ema",
            ema_vs0="below_0",
            ema_slope="rising",
        )
        and _tags_match(hist, hist_sign="below_0", hist_dir="hist_shrinking")
    )


def setup_signal(
    small: dict,
    middle: dict,
    hist: dict,
    current: dict | None = None,
) -> str:
    """Classic stack = buy/sell. M10 17:20 = buy1/sell1. Si M1 18:55 = buy2/sell2."""
    if _buy_stack(small, middle, hist, current):
        return "buy"
    if _sell_stack(small, middle, hist, current):
        return "sell"
    if _buy_m10_cross(current, small, middle, hist):
        return "buy1"
    if _sell_m10_cross(current, small, middle, hist):
        return "sell1"
    if _buy2_stack(small, middle, hist, current):
        return "buy2"
    if _sell2_stack(small, middle, hist, current):
        return "sell2"
    return "none"


def bar_key(price_move: str | None, current: dict, small: dict, middle: dict, hist: dict) -> str | None:
    if not current.get("combo") or not small.get("combo") or not middle.get("combo") or not hist.get("combo"):
        return None
    if price_move in {None, "unknown"}:
        return None
    setup = setup_signal(small, middle, hist, current)
    return (
        f"{setup}|p={price_move}|c={current['combo']}"
        f"|s={small['combo']}|m={middle['combo']}|h={hist['combo']}"
    )


def zigzag_moves(bars: list[Bar], min_pct: float = MIN_MOVE_PCT) -> list[dict]:
    """Non-overlapping directional legs of at least min_pct, confirmed by a reverse of min_pct."""
    n = len(bars)
    if n < 3:
        return []
    moves: list[dict] = []
    start_i = 0
    ext_i = 0
    direction = 0

    def _pct(a: float, b: float) -> float:
        if a <= 0:
            return 0.0
        return (b - a) / a * 100.0

    def _add(side: str, i0: int, i1: int) -> None:
        p0, p1 = bars[i0].c, bars[i1].c
        pct = abs(_pct(p0, p1))
        if pct < min_pct:
            return
        moves.append(
            {
                "side": side,
                "start": i0,
                "end": i1,
                "start_dt": bars[i0].dt,
                "end_dt": bars[i1].dt,
                "start_px": p0,
                "end_px": p1,
                "pct": round(pct, 3),
            }
        )

    for i in range(1, n):
        px = bars[i].c
        start_px = bars[start_i].c
        ext_px = bars[ext_i].c
        if direction == 0:
            chg = _pct(start_px, px)
            if chg >= min_pct:
                direction = 1
                ext_i = i
            elif chg <= -min_pct:
                direction = -1
                ext_i = i
            continue
        if direction == 1:
            if px >= ext_px:
                ext_i = i
            elif ext_px > 0 and (ext_px - px) / ext_px * 100.0 >= min_pct:
                _add("up", start_i, ext_i)
                start_i = ext_i
                ext_i = i
                direction = -1
        else:
            if px <= ext_px:
                ext_i = i
            elif ext_px > 0 and (px - ext_px) / ext_px * 100.0 >= min_pct:
                _add("down", start_i, ext_i)
                start_i = ext_i
                ext_i = i
                direction = 1
    if direction == 1:
        _add("up", start_i, ext_i)
    elif direction == -1:
        _add("down", start_i, ext_i)
    return moves


def tf_series(bars: list[Bar], tf: str, *, setups_only: bool = False) -> list[dict]:
    current = compute_current(bars)
    cur = current_tags(current)
    up_set = load_up_settings(tf)
    up = compute_up(bars, up_set, track_divs=not setups_only)
    small = layer_tags(up["series"], "small")
    middle = layer_tags(up["series"], "middle")
    hist_names = hist_layer_names(up_set)
    hist_name = hist_names[0] if hist_names else "up"
    hist = hist_tags(up["series"], hist_name)
    moves = None if setups_only else classify_moves(bars, tf)
    out = []
    for i, bar in enumerate(bars):
        setup = setup_signal(small[i], middle[i], hist[i], cur[i])
        if setups_only:
            out.append({"dt": bar.dt, "setup": setup})
            continue
        key = bar_key(moves[i], cur[i], small[i], middle[i], hist[i])
        out.append(
            {
                "dt": bar.dt,
                "key": key,
                "setup": setup,
                "price_move": moves[i],
            }
        )
    return out


def _empty_node() -> dict:
    return {
        "n": 0,
        "buy": 0,
        "sell": 0,
        "starts": 0,
        "ends": 0,
        "children": {},
    }


def _touch(node: dict, setup: str) -> None:
    node["n"] += 1
    if setup.startswith("buy"):
        node["buy"] += 1
    elif setup.startswith("sell"):
        node["sell"] += 1


def _child(node: dict, key: str) -> dict:
    kids = node["children"]
    if key not in kids:
        kids[key] = _empty_node()
    return kids[key]


def _setup_of(key: str) -> str:
    if key.startswith("buy2|"):
        return "buy2"
    if key.startswith("sell2|"):
        return "sell2"
    if key.startswith("buy1|"):
        return "buy1"
    if key.startswith("sell1|"):
        return "sell1"
    if key.startswith("buy|"):
        return "buy"
    if key.startswith("sell|"):
        return "sell"
    return "none"


def parse_key(key: str | None) -> dict:
    empty = {"setup": "na", "price": "na", "cur": "na", "small": "na", "middle": "na", "hist": "na"}
    if not key:
        return empty
    bits = key.split("|")
    fields = dict(empty)
    fields["setup"] = bits[0] if bits else "na"
    cur: str | None = None
    acc: list[str] = []
    for bit in bits[1:]:
        if bit.startswith("p="):
            fields["price"] = bit[2:]
            continue
        tagged = None
        if bit.startswith("c="):
            tagged = "cur"
            bit = bit[2:]
        elif bit.startswith("s="):
            tagged = "small"
            bit = bit[2:]
        elif bit.startswith("m="):
            tagged = "middle"
            bit = bit[2:]
        elif bit.startswith("h="):
            tagged = "hist"
            bit = bit[2:]
        if tagged:
            if cur:
                fields[cur] = "|".join(acc)
            cur = tagged
            acc = [bit]
        else:
            acc.append(bit)
    if cur:
        fields[cur] = "|".join(acc)
    return fields


def _part(combo: str, idx: int) -> str:
    bits = combo.split("|")
    return bits[idx] if idx < len(bits) else "na"


def compact_state(key: str | None) -> str:
    f = parse_key(key)
    if f["setup"] == "na" and f["price"] == "na":
        return "na"
    c0, c1 = _part(f["cur"], 0), _part(f["cur"], 1)
    s0, s1 = _part(f["small"], 0), _part(f["small"], 1)
    m0, m1 = _part(f["middle"], 0), _part(f["middle"], 1)
    h0, h1 = _part(f["hist"], 0), _part(f["hist"], 1).replace("hist_", "")
    return f"{f['setup']} p={f['price']} c={c0}/{c1} s={s0}/{s1} m={m0}/{m1} h={h0}/{h1}"


def build_tree(frames: dict[str, dict]) -> dict:
    root = _empty_node()
    m1 = frames["M1"]
    times = {tf: frames[tf]["times"] for tf in CHART_TFS}
    keys = {tf: frames[tf]["keys"] for tf in CHART_TFS}
    setups = {tf: frames[tf]["setups"] for tf in CHART_TFS}
    warm = WARMUP["M1"]
    last = len(m1["bars"]) - 1
    mapped = {
        tf: last_closed_indices(m1["times"], times[tf], PERIOD_MIN[tf]) if tf != "M1" else list(range(len(m1["times"])))
        for tf in CHART_TFS
    }
    samples = 0
    for i in range(warm, last):
        idx = {
            "M1": i,
            "M10": mapped["M10"][i],
            "M30": mapped["M30"][i],
            "H4": mapped["H4"][i],
        }
        if any(idx[tf] is None or idx[tf] < WARMUP[tf] for tf in CHART_TFS):
            continue
        path = {tf: keys[tf][idx[tf]] for tf in CHART_TFS}
        if any(path[tf] is None for tf in CHART_TFS):
            continue
        samples += 1
        node = root
        _touch(node, setups["H4"][idx["H4"]])
        for tf in CHART_TFS:
            node = _child(node, path[tf])
            _touch(node, _setup_of(path[tf]))
    root["samples"] = samples
    return root


def _path_at(frames: dict[str, dict], when, event_tf: str, event_i: int) -> dict | None:
    path = {}
    for tf in CHART_TFS:
        if tf == event_tf:
            i = event_i
        else:
            i = last_closed_indices([when], frames[tf]["times"], PERIOD_MIN[tf])[0]
        if i is None or i < WARMUP[tf]:
            if tf == event_tf:
                return None
            path[tf] = None
            continue
        key = frames[tf]["keys"][i]
        if key is None:
            if tf == event_tf:
                return None
            path[tf] = None
            continue
        path[tf] = {
            "i": i,
            "dt": frames[tf]["times"][i].isoformat(sep=" "),
            "key": key,
            "setup": frames[tf]["setups"][i],
            "compact": compact_state(key),
            "fields": parse_key(key),
        }
    return path


def _mark_path(root: dict, path: dict, field: str) -> None:
    node = root
    for tf in CHART_TFS:
        pack = path.get(tf)
        if not pack:
            break
        key = pack["key"]
        if key not in node["children"]:
            node["children"][key] = _empty_node()
        node = node["children"][key]
        node[field] += 1


def m1_moves(frames: dict[str, dict], min_pct: float = MIN_MOVE_PCT, root: dict | None = None) -> list[dict]:
    bars = frames["M1"]["bars"]
    last = max(0, len(bars) - 1)
    found = []
    for mv in zigzag_moves(bars[:last], min_pct):
        start_path = _path_at(frames, mv["start_dt"], "M1", mv["start"])
        end_path = _path_at(frames, mv["end_dt"], "M1", mv["end"])
        found.append(
            {
                "tf": "M1",
                "side": mv["side"],
                "pct": mv["pct"],
                "start_dt": mv["start_dt"].isoformat(sep=" "),
                "end_dt": mv["end_dt"].isoformat(sep=" "),
                "start_px": mv["start_px"],
                "end_px": mv["end_px"],
                "start": start_path,
                "end": end_path,
            }
        )
        if root is not None and start_path:
            _mark_path(root, start_path, "starts")
        if root is not None and end_path:
            _mark_path(root, end_path, "ends")
    found.sort(key=lambda r: -r["pct"])
    return found


def _states_at(frames: dict[str, dict], when, tfs: tuple[str, ...]) -> dict:
    path = {}
    for tf in tfs:
        i = last_closed_indices([when], frames[tf]["times"], PERIOD_MIN[tf])[0]
        if i is None or i < WARMUP[tf]:
            path[tf] = None
            continue
        key = frames[tf]["keys"][i]
        if key is None:
            path[tf] = None
            continue
        path[tf] = {
            "i": i,
            "dt": frames[tf]["times"][i].isoformat(sep=" "),
            "key": key,
            "setup": frames[tf]["setups"][i],
            "compact": compact_state(key),
            "fields": parse_key(key),
        }
    return path


def find_setup_left(
    setups: list[str],
    end_i: int,
    max_bars: int,
    warm: int = 0,
) -> dict | None:
    """Most recent buy/sell bar in (end_i - max_bars, end_i], then onset of that run."""
    if end_i < 0 or end_i >= len(setups):
        return None
    lo = max(warm, end_i - max_bars)
    hit = None
    for i in range(end_i, lo - 1, -1):
        if setups[i] in SETUP_NAMES:
            hit = i
            break
    if hit is None:
        return None
    setup = setups[hit]
    onset = hit
    while onset > warm and setups[onset - 1] == setup:
        onset -= 1
    return {
        "setup": setup,
        "hit_i": hit,
        "onset_i": onset,
        "bars_ago": end_i - onset,
        "run_bars": hit - onset + 1,
        "clipped": onset == warm and warm > 0 and onset > 0 and setups[onset - 1] == setup,
    }


def setup_drawdown(bars: list[Bar], onset_i: int, end_i: int, setup: str) -> float | None:
    """Adverse excursion from setup close through end_i, percent of close.

    Buy: (close - min low) / close. Sell: (max high - close) / close.
    """
    if onset_i < 0 or end_i < onset_i or end_i >= len(bars):
        return None
    px = bars[onset_i].c
    if px <= 0:
        return None
    chunk = bars[onset_i : end_i + 1]
    if setup in {"buy", "buy1", "buy2"}:
        worst = min(b.l for b in chunk)
        return round((px - worst) / px * 100.0, 3)
    if setup in {"sell", "sell1", "sell2"}:
        worst = max(b.h for b in chunk)
        return round((worst - px) / px * 100.0, 3)
    return None


def _setup_look(frames: dict[str, dict], tf: str, start_dt, end_dt) -> dict:
    empty = {
        "setup": "none",
        "onset_dt": None,
        "onset_px": None,
        "bars_ago": None,
        "run_bars": None,
        "dd_pct": None,
        "compact": "na",
        "fields": parse_key(None),
        "clipped": False,
    }
    times = frames[tf]["times"]
    ref = last_closed_indices([start_dt], times, PERIOD_MIN[tf])[0]
    end_i = last_closed_indices([end_dt], times, PERIOD_MIN[tf])[0]
    if ref is None or ref < WARMUP[tf]:
        return empty
    found = find_setup_left(frames[tf]["setups"], ref, SETUP_LOOKBACK[tf], WARMUP[tf])
    if found is None:
        return empty
    onset_i = found["onset_i"]
    if end_i is None or end_i < onset_i:
        end_i = ref
    bars = frames[tf]["bars"]
    key = frames[tf]["keys"][onset_i]
    return {
        "setup": found["setup"],
        "onset_dt": bars[onset_i].dt.isoformat(sep=" "),
        "onset_px": bars[onset_i].c,
        "bars_ago": found["bars_ago"],
        "run_bars": found["run_bars"],
        "dd_pct": setup_drawdown(bars, onset_i, end_i, found["setup"]),
        "compact": compact_state(key) if key else "na",
        "fields": parse_key(key),
        "clipped": found["clipped"],
    }


def m30_moves(frames: dict[str, dict], min_pct: float = M30_MOVE_PCT) -> list[dict]:
    bars = frames["M30"]["bars"]
    last = max(0, len(bars) - 1)
    found = []
    for mv in zigzag_moves(bars[:last], min_pct):
        found.append(
            {
                "tf": "M30",
                "side": mv["side"],
                "pct": mv["pct"],
                "start_dt": mv["start_dt"].isoformat(sep=" "),
                "end_dt": mv["end_dt"].isoformat(sep=" "),
                "start_px": mv["start_px"],
                "end_px": mv["end_px"],
                "start": _states_at(frames, mv["start_dt"], LOOK_TFS_M30),
                "end": _states_at(frames, mv["end_dt"], LOOK_TFS_M30),
                "look": {
                    tf: _setup_look(frames, tf, mv["start_dt"], mv["end_dt"])
                    for tf in LOOK_TFS_M30
                },
            }
        )
    found.sort(key=lambda r: r["start_dt"])
    return found


def _count_states(moves: list[dict], tf: str, when: str) -> list[dict]:
    acc: dict[str, dict] = defaultdict(lambda: {"n": 0, "up": 0, "down": 0, "sum_pct": 0.0})
    for mv in moves:
        state = ((mv.get(when) or {}).get(tf) or {}).get("compact") or "na"
        row = acc[state]
        row["n"] += 1
        row["sum_pct"] += mv["pct"]
        row[mv["side"]] += 1
    rows = [{"state": state, **_agg_row(pack)} for state, pack in acc.items()]
    rows.sort(key=lambda r: (-r["n"], -(r["mean_pct"] or 0)))
    return rows


def _count_looks(moves: list[dict], tf: str) -> list[dict]:
    acc: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "up": 0, "down": 0, "sum_pct": 0.0, "sum_dd": 0.0, "n_dd": 0, "sum_ago": 0.0, "n_ago": 0}
    )
    for mv in moves:
        pack = (mv.get("look") or {}).get(tf) or {}
        setup = pack.get("setup") or "none"
        row = acc[setup]
        row["n"] += 1
        row["sum_pct"] += mv["pct"]
        row[mv["side"]] += 1
        if pack.get("dd_pct") is not None:
            row["sum_dd"] += pack["dd_pct"]
            row["n_dd"] += 1
        if pack.get("bars_ago") is not None:
            row["sum_ago"] += pack["bars_ago"]
            row["n_ago"] += 1
    rows = []
    for setup, pack in acc.items():
        rows.append(
            {
                "setup": setup,
                **_agg_row(pack),
                "mean_dd": round(pack["sum_dd"] / pack["n_dd"], 2) if pack["n_dd"] else None,
                "mean_bars_ago": round(pack["sum_ago"] / pack["n_ago"], 1) if pack["n_ago"] else None,
            }
        )
    rows.sort(key=lambda r: (-r["n"], r["setup"]))
    return rows


def _listed_move(mv: dict) -> dict:
    out = {
        "side": mv["side"],
        "pct": mv["pct"],
        "start_dt": mv["start_dt"],
        "end_dt": mv["end_dt"],
        "start_px": mv["start_px"],
        "end_px": mv["end_px"],
    }
    for when in ("start", "end"):
        for tf in LOOK_TFS_M30:
            pack = (mv.get(when) or {}).get(tf)
            out[f"{when}_{tf}"] = (pack or {}).get("compact") or "na"
            out[f"{when}_{tf}_fields"] = (pack or {}).get("fields") or parse_key(None)
            out[f"{when}_{tf}_bar"] = (pack or {}).get("dt")
    look = mv.get("look") or {}
    for tf in LOOK_TFS_M30:
        pack = look.get(tf) or {}
        out[f"look_{tf}"] = pack.get("setup") or "none"
        out[f"look_{tf}_onset"] = pack.get("onset_dt")
        out[f"look_{tf}_px"] = pack.get("onset_px")
        out[f"look_{tf}_bars_ago"] = pack.get("bars_ago")
        out[f"look_{tf}_run"] = pack.get("run_bars")
        out[f"look_{tf}_dd"] = pack.get("dd_pct")
        out[f"look_{tf}_compact"] = pack.get("compact") or "na"
        out[f"look_{tf}_fields"] = pack.get("fields") or parse_key(None)
        out[f"look_{tf}_clipped"] = pack.get("clipped")
    return out


def _agg_row(acc: dict) -> dict:
    n = acc["n"]
    return {
        "n": n,
        "up": acc["up"],
        "down": acc["down"],
        "mean_pct": round(acc["sum_pct"] / n, 2) if n else None,
    }


def aggregate_start_end(moves: list[dict], min_n: int = 1, tfs: tuple[str, ...] | None = None) -> dict:
    """Group moves by start vs end 'what's now' on the chosen TF ladder."""
    tfs = tfs or CHART_TFS
    usable = [m for m in moves if m.get("start") and m.get("end")]
    by_tf: dict[str, dict[tuple[str, str], dict]] = {tf: defaultdict(lambda: {"n": 0, "up": 0, "down": 0, "sum_pct": 0.0}) for tf in tfs}
    by_field: dict[str, dict[tuple[str, str, str], dict]] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "up": 0, "down": 0, "sum_pct": 0.0}))
    ladder: dict[tuple, dict] = defaultdict(lambda: {"n": 0, "up": 0, "down": 0, "sum_pct": 0.0})
    field_names = ("setup", "price", "cur", "small", "middle", "hist")

    def bump(acc: dict, mv: dict) -> None:
        acc["n"] += 1
        acc["sum_pct"] += mv["pct"]
        acc[mv["side"]] += 1

    for mv in usable:
        start, end = mv["start"], mv["end"]
        ladder_key = tuple(
            ((start.get(tf) or {}).get("compact") or "na", (end.get(tf) or {}).get("compact") or "na")
            for tf in tfs
        )
        bump(ladder[ladder_key], mv)
        for tf in tfs:
            s = (start.get(tf) or {}).get("compact") or "na"
            e = (end.get(tf) or {}).get("compact") or "na"
            bump(by_tf[tf][(s, e)], mv)
            sf = (start.get(tf) or {}).get("fields") or parse_key(None)
            ef = (end.get(tf) or {}).get("fields") or parse_key(None)
            for name in field_names:
                bump(by_field[tf][(name, sf.get(name, "na"), ef.get(name, "na"))], mv)

    def dump_pairs(src: dict[tuple[str, str], dict]) -> list[dict]:
        rows = []
        for (start, end), acc in src.items():
            if acc["n"] < min_n:
                continue
            rows.append({"start": start, "end": end, **_agg_row(acc)})
        rows.sort(key=lambda r: (-r["n"], -(r["mean_pct"] or 0)))
        return rows

    field_tables = {}
    for tf in tfs:
        rows = []
        for (name, start, end), acc in by_field[tf].items():
            if acc["n"] < min_n:
                continue
            rows.append({"field": name, "start": start, "end": end, **_agg_row(acc)})
        rows.sort(key=lambda r: (-r["n"], r["field"]))
        field_tables[tf] = rows

    ladder_rows = []
    for key, acc in ladder.items():
        if acc["n"] < min_n:
            continue
        row = _agg_row(acc)
        for i, tf in enumerate(tfs):
            row[f"start_{tf}"] = key[i][0]
            row[f"end_{tf}"] = key[i][1]
        ladder_rows.append(row)
    ladder_rows.sort(key=lambda r: (-r["n"], -(r["mean_pct"] or 0)))
    return {
        "moves_with_path": len(usable),
        "tfs": list(tfs),
        "by_tf": {tf: dump_pairs(by_tf[tf]) for tf in tfs},
        "by_field": field_tables,
        "ladder": ladder_rows,
    }


def _unique_counts(node: dict, depth: int = 0) -> list[int]:
    counts = [0, 0, 0, 0]
    if depth >= 4:
        return counts
    counts[depth] = len(node.get("children") or {})
    for child in (node.get("children") or {}).values():
        sub = _unique_counts(child, depth + 1)
        for i in range(depth + 1, 4):
            counts[i] += sub[i]
    return counts


def tree_stats(root: dict) -> dict:
    uniq = _unique_counts(root, 0)
    return {
        "samples": root.get("samples", 0),
        "unique_h4": uniq[0],
        "unique_m30_under_h4": uniq[1],
        "unique_m10_under_m30": uniq[2],
        "unique_m1_under_m10": uniq[3],
        "unique_full_paths": uniq[3],
        "h4_buy_keys": sum(1 for k in root["children"] if k.startswith("buy|")),
        "h4_sell_keys": sum(1 for k in root["children"] if k.startswith("sell|")),
        "bars_buy": root.get("buy", 0),
        "bars_sell": root.get("sell", 0),
    }


def top_h4(root: dict, n: int = 12) -> list[dict]:
    rows = []
    for key, child in root["children"].items():
        rows.append(
            {
                "key": key,
                "n": child["n"],
                "buy": child["buy"],
                "sell": child["sell"],
                "starts": child["starts"],
                "ends": child["ends"],
                "unique_m30": len(child["children"]),
                "setup": _setup_of(key),
            }
        )
    rows.sort(key=lambda r: (-r["n"], -r["unique_m30"]))
    return rows[:n]


def load_frames(
    sec: str,
    class_code: str = "TQBR",
    data_dir: Path | None = None,
) -> tuple[str, dict[str, dict]]:
    books = load_instrument(sec, class_code, data_dir or BARS_DIR)
    clock = max(books[tf][-1].dt for tf in CHART_TFS)
    frames: dict[str, dict] = {}
    for tf in CHART_TFS:
        bars = [b for b in books[tf] if b.dt <= clock]
        series = tf_series(bars, tf)
        frames[tf] = {
            "bars": bars,
            "times": [b.dt for b in bars],
            "keys": [row["key"] for row in series],
            "setups": [row["setup"] for row in series],
            "series": series,
            "last_bar": bars[-1].dt.isoformat(sep=" ") if bars else None,
        }
    return clock.isoformat(sep=" "), frames


def study_combo(
    sec: str,
    class_code: str = "TQBR",
    data_dir: Path | None = None,
    min_pct: float = MIN_MOVE_PCT,
) -> dict:
    clock, frames = load_frames(sec, class_code, data_dir)
    root = build_tree(frames)
    moves = m1_moves(frames, min_pct, root=root)
    stats = tree_stats(root)
    agg = aggregate_start_end(moves)
    return {
        "sec": sec,
        "class_code": class_code,
        "clock": clock,
        "kind": "combo_h4_to_m1",
        "min_move_pct": min_pct,
        "stats": stats,
        "top_h4": top_h4(root),
        "move_count": len(moves),
        "moves_with_path": agg["moves_with_path"],
        "agg": {
            "by_tf": {tf: pack[:20] for tf, pack in agg["by_tf"].items()},
            "by_field": {tf: [r for r in pack if r["field"] in {"setup", "price", "hist"}][:24] for tf, pack in agg["by_field"].items()},
            "ladder": agg["ladder"][:20],
        },
    }


def _short(key: str, width: int = 88) -> str:
    if len(key) <= width:
        return key
    return key[: width - 3] + "..."


def format_combo(report: dict, include_tree: bool = False) -> str:
    st = report["stats"]
    lines = [
        f"{report['sec']} {report['class_code']}  clock={report['clock']}  "
        f"combo H4->M30->M10->M1  M1 move>={report['min_move_pct']}%"
    ]
    lines.append(
        f"  samples={st['samples']}  unique H4={st['unique_h4']}  "
        f"M30={st['unique_m30_under_h4']}  M10={st['unique_m10_under_m30']}  "
        f"M1 paths={st['unique_full_paths']}"
    )
    lines.append(
        f"  M1 moves={report['move_count']}  with path={report['moves_with_path']}"
    )
    agg = report.get("agg") or {}
    for tf in CHART_TFS:
        rows = (agg.get("by_tf") or {}).get(tf) or []
        lines.append(f"\n=== {tf} start -> end  (top {len(rows)})")
        lines.append(f"  {'n':<5} {'up':<4} {'dn':<4} {'pct':<6}  start -> end")
        for row in rows[:12]:
            lines.append(
                f"  {row['n']:<5} {row['up']:<4} {row['down']:<4} {row['mean_pct']:<6}  "
                f"{_short(row['start'], 52)}  ->  {_short(row['end'], 52)}"
            )
        fields = (agg.get("by_field") or {}).get(tf) or []
        if fields:
            lines.append(f"  fields:")
            for row in fields[:12]:
                lines.append(
                    f"    {row['field']:<6} {row['start']:<28} -> {row['end']:<28}  "
                    f"n={row['n']:<4} up={row['up']} dn={row['down']} pct={row['mean_pct']}"
                )
    ladder = agg.get("ladder") or []
    if ladder:
        lines.append(f"\n=== ladder H4/M30/M10/M1 start -> end  n={len(ladder)} shown")
        for row in ladder[:8]:
            lines.append(
                f"  n={row['n']} up={row['up']} dn={row['down']} pct={row['mean_pct']}"
            )
            lines.append(f"    start H4 {_short(row['start_H4'], 100)}")
            lines.append(f"    end   H4 {_short(row['end_H4'], 100)}")
            lines.append(f"    start M1 {_short(row['start_M1'], 100)}")
            lines.append(f"    end   M1 {_short(row['end_M1'], 100)}")
    if include_tree:
        lines.append("\n  tree keys omitted (use --json)")
    return "\n".join(lines)


def study_m30_look(
    sec: str,
    class_code: str = "TQBR",
    data_dir: Path | None = None,
    min_pct: float = M30_MOVE_PCT,
    last_n: int = M30_SHOW_LAST,
) -> dict:
    clock, frames = load_frames(sec, class_code, data_dir)
    moves = m30_moves(frames, min_pct)
    shown = moves[-last_n:] if last_n and last_n > 0 else moves
    agg = aggregate_start_end(shown, tfs=LOOK_TFS_M30)
    return {
        "sec": sec,
        "class_code": class_code,
        "clock": clock,
        "kind": "m30_move_m10_m1",
        "min_move_pct": min_pct,
        "move_count": len(moves),
        "shown": len(shown),
        "moves_with_path": agg["moves_with_path"],
        "moves": [_listed_move(mv) for mv in shown],
        "unique": {
            tf: {"start": _count_states(shown, tf, "start"), "end": _count_states(shown, tf, "end")}
            for tf in LOOK_TFS_M30
        },
        "look": {tf: _count_looks(shown, tf) for tf in LOOK_TFS_M30},
        "lookback": dict(SETUP_LOOKBACK),
        "agg": {
            "by_tf": agg["by_tf"],
            "by_field": {
                tf: [r for r in pack if r["field"] in {"setup", "price", "hist"}]
                for tf, pack in agg["by_field"].items()
            },
            "ladder": agg["ladder"],
        },
    }


def _fields_line(fields: dict | None) -> str:
    f = fields or parse_key(None)
    return (
        f"setup={f.get('setup')} p={f.get('price')} "
        f"c={f.get('cur')} s={f.get('small')} m={f.get('middle')} h={f.get('hist')}"
    )


def format_m30_look(report: dict) -> str:
    lines = [
        f"{report['sec']} {report['class_code']}  clock={report['clock']}  "
        f"M30 move>={report['min_move_pct']}%  look M10+M1"
    ]
    lines.append(
        f"  moves={report['move_count']}  shown last {report.get('shown', len(report.get('moves') or []))}"
    )
    lookback = report.get("lookback") or SETUP_LOOKBACK
    lines.append(
        f"  setup lookback M1={lookback.get('M1')} bars  M10={lookback.get('M10')} bars  "
        f"(onset + drawdown to M30 end)"
    )
    lines.append("\n=== each M30 move: M10 and M1 what's now + setup in history")
    for i, mv in enumerate(report.get("moves") or [], 1):
        lines.append(
            f"\n  #{i} {mv['side']} {mv['pct']}%  "
            f"start_bar={mv['start_dt']}  end_bar={mv['end_dt']}  "
            f"{mv['start_px']} -> {mv['end_px']}"
        )
        for tf in LOOK_TFS_M30:
            lines.append(f"    {tf} start bar={mv.get(f'start_{tf}_bar')}  {mv.get(f'start_{tf}')}")
            lines.append(f"         {_fields_line(mv.get(f'start_{tf}_fields'))}")
            lines.append(f"    {tf} end   bar={mv.get(f'end_{tf}_bar')}  {mv.get(f'end_{tf}')}")
            lines.append(f"         {_fields_line(mv.get(f'end_{tf}_fields'))}")
            look = mv.get(f"look_{tf}") or "none"
            if look == "none":
                lines.append(f"    {tf} setup none in lookback")
            else:
                lines.append(
                    f"    {tf} setup {look}  ago={mv.get(f'look_{tf}_bars_ago')}  "
                    f"run={mv.get(f'look_{tf}_run')}  dd={mv.get(f'look_{tf}_dd')}%  "
                    f"onset={mv.get(f'look_{tf}_onset')} @{mv.get(f'look_{tf}_px')}"
                )
                lines.append(f"         {mv.get(f'look_{tf}_compact')}")
                lines.append(f"         {_fields_line(mv.get(f'look_{tf}_fields'))}")
    unique = report.get("unique") or {}
    for tf in LOOK_TFS_M30:
        pack = unique.get(tf) or {}
        for when, title in (("start", "at start"), ("end", "at end")):
            rows = pack.get(when) or []
            lines.append(f"\n=== unique {tf} {title}  ({len(rows)})")
            for row in rows:
                lines.append(
                    f"  n={row['n']:<4} up={row['up']:<4} dn={row['down']:<4} "
                    f"pct={row['mean_pct']:<6}  {_short(row['state'], 100)}"
                )
    agg = report.get("agg") or {}
    for tf in LOOK_TFS_M30:
        rows = (agg.get("by_tf") or {}).get(tf) or []
        lines.append(f"\n=== {tf} start -> end  ({len(rows)})")
        lines.append(f"  {'n':<5} {'up':<4} {'dn':<4} {'pct':<6}  start -> end")
        for row in rows:
            lines.append(
                f"  {row['n']:<5} {row['up']:<4} {row['down']:<4} {row['mean_pct']:<6}  "
                f"{_short(row['start'], 48)}  ->  {_short(row['end'], 48)}"
            )
        fields = (agg.get("by_field") or {}).get(tf) or []
        if fields:
            lines.append("  fields:")
            for row in fields[:16]:
                lines.append(
                    f"    {row['field']:<6} {row['start']:<28} -> {row['end']:<28}  "
                    f"n={row['n']:<4} up={row['up']} dn={row['down']} pct={row['mean_pct']}"
                )
    look = report.get("look") or {}
    for tf in LOOK_TFS_M30:
        rows = look.get(tf) or []
        lines.append(f"\n=== {tf} setup in last {lookback.get(tf)} bars  ({len(rows)})")
        lines.append(f"  {'setup':<8} {'n':<5} {'up':<4} {'dn':<4} {'pct':<6} {'dd':<6} {'ago':<6}")
        for row in rows:
            lines.append(
                f"  {row['setup']:<8} {row['n']:<5} {row['up']:<4} {row['down']:<4} "
                f"{row['mean_pct']:<6} {str(row.get('mean_dd')):<6} {str(row.get('mean_bars_ago')):<6}"
            )
    return "\n".join(lines)
