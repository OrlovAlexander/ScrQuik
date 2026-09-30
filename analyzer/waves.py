# -*- coding: utf-8 -*-
"""Swing pivots, zigzag legs, left/right 1-5 geometry.

Heuristic inspired by public Krechetov statistical-wave talks; not a copy of
his strategy. Independent of RPM buy/sell setups. Confirms on closed bars only.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from analyzer.bars import BARS_DIR, Bar, load_instrument
from analyzer.marks import mark_sec_names, marks_path, watch_marks

WAVE_TFS = ("M1", "M10", "M30")
WAVE_WINDOW = {"M1": 120, "M10": 90, "M30": 90}
WAVE_LOOKBACK = {"M1": 1600, "M10": 800, "M30": 800}
WAVE_MIN_PCT = {"M1": 0.15, "M10": 0.2, "M30": 0.25}
WAVES_DIR = Path(r"C:\QuikFinam\LuaIndicators\analyzer_waves")
DT_FMT = "%d.%m.%Y %H:%M:%S"
_WRITE_TRIES = 6
_WRITE_WAIT = 0.12

# 4->5 amplitude vs 2->3; time of those legs; channel distances vs width.
PENDULUM_AMP = (0.35, 1.0)
PENDULUM_TIME = (0.35, 2.5)
CHANNEL_AT_1 = (0.35, 1.8)
CHANNEL_AT_5 = (0.25, 1.15)
MAX_LEG_TIME_RATIO = 5.0
NECK_TILT_FRAC = 0.35
MIN_LEG_BARS = 2


def _pct(a: float, b: float) -> float:
    if a <= 0:
        return 0.0
    return (b - a) / a * 100.0


def _abs_pct(a: float, b: float) -> float:
    return abs(_pct(a, b))


def swing_pivots(bars: list[Bar], min_pct: float) -> list[dict]:
    """Percent zigzag on bar high/low. Last unconfirmed extreme has confirmed=False."""
    n = len(bars)
    if n < 3 or min_pct <= 0:
        return []
    pivots: list[dict] = []
    i_high = 0
    i_low = 0
    trend = 0

    def add(kind: str, i: int, confirmed: bool = True) -> None:
        if pivots and pivots[-1]["i"] == i:
            return
        px = bars[i].h if kind == "high" else bars[i].l
        pivots.append(
            {
                "kind": kind,
                "i": i,
                "dt": bars[i].dt,
                "price": px,
                "confirmed": confirmed,
            }
        )

    for i in range(1, n):
        if bars[i].h >= bars[i_high].h:
            i_high = i
        if bars[i].l <= bars[i_low].l:
            i_low = i
        if trend == 0:
            span = _abs_pct(bars[i_low].l, bars[i_high].h)
            if span < min_pct:
                continue
            if i_high > i_low:
                add("low", i_low)
                trend = 1
                i_low = i
            else:
                add("high", i_high)
                trend = -1
                i_high = i
            continue
        if trend == 1:
            if bars[i].h >= bars[i_high].h:
                i_high = i
                i_low = i
            elif _abs_pct(bars[i_high].h, bars[i].l) >= min_pct:
                add("high", i_high)
                trend = -1
                i_low = i
                i_high = i
        else:
            if bars[i].l <= bars[i_low].l:
                i_low = i
                i_high = i
            elif _abs_pct(bars[i_low].l, bars[i].h) >= min_pct:
                add("low", i_low)
                trend = 1
                i_high = i
                i_low = i
    if trend == 1:
        add("high", i_high, confirmed=False)
    elif trend == -1:
        add("low", i_low, confirmed=False)
    return pivots


def legs_from_pivots(pivots: list[dict]) -> list[dict]:
    legs: list[dict] = []
    for a, b in zip(pivots, pivots[1:]):
        side = "up" if b["price"] >= a["price"] else "down"
        legs.append(
            {
                "side": side,
                "start": a["i"],
                "end": b["i"],
                "start_dt": a["dt"],
                "end_dt": b["dt"],
                "start_px": a["price"],
                "end_px": b["price"],
                "start_kind": a["kind"],
                "end_kind": b["kind"],
                "pct": round(_abs_pct(a["price"], b["price"]), 3),
                "bars": b["i"] - a["i"],
                "confirmed": bool(a["confirmed"] and b["confirmed"]),
            }
        )
    return legs


def _line_price(i: int, a: dict, b: dict) -> float:
    span = b["i"] - a["i"]
    if span == 0:
        return a["price"]
    t = (i - a["i"]) / span
    return a["price"] + t * (b["price"] - a["price"])


def _vert(p: dict, a: dict, b: dict) -> float:
    return p["price"] - _line_price(p["i"], a, b)


def _leg_bars(a: dict, b: dict) -> int:
    return b["i"] - a["i"]


def _seq_ok(pts: list[dict]) -> bool:
    if any(_leg_bars(a, b) < MIN_LEG_BARS for a, b in zip(pts, pts[1:])):
        return False
    kinds = [p["kind"] for p in pts]
    if any(x == y for x, y in zip(kinds, kinds[1:])):
        return False
    return True


def _time_ok(pts: list[dict]) -> str | None:
    spans = [_leg_bars(a, b) for a, b in zip(pts, pts[1:])]
    if not spans or min(spans) <= 0:
        return "ragged_time"
    if max(spans) / min(spans) > MAX_LEG_TIME_RATIO:
        return "ragged_time"
    return None


def _approaches(p2: dict, p3: dict, p4: dict, p5: dict) -> str | None:
    first = _abs_pct(p2["price"], p3["price"])
    second = _abs_pct(p4["price"], p5["price"])
    if first <= 0:
        return "4to5_longer"
    ratio = second / first
    if ratio > PENDULUM_AMP[1] or second > first:
        return "4to5_longer"
    if ratio < PENDULUM_AMP[0]:
        return "pendulum_amp"
    t1 = _leg_bars(p2, p3)
    t2 = _leg_bars(p4, p5)
    if t1 <= 0:
        return "pendulum_time"
    tr = t2 / t1
    if tr < PENDULUM_TIME[0] or tr > PENDULUM_TIME[1]:
        return "pendulum_time"
    return None


def _channel_ok(p1: dict, p2: dict, p3: dict, p4: dict, p5: dict, min_pct: float) -> str | None:
    width = abs(_vert(p3, p2, p4))
    mid = (p2["price"] + p4["price"]) / 2.0
    if mid <= 0:
        return "channel"
    neck_pct = abs(p4["price"] - p2["price"]) / mid * 100.0
    if neck_pct < min_pct * NECK_TILT_FRAC:
        return "flat_neck"
    if width <= 0:
        return "channel"
    d1 = _vert(p1, p2, p4)
    d3 = _vert(p3, p2, p4)
    d5 = _vert(p5, p2, p4)
    if d1 * d3 <= 0 or d5 * d3 <= 0:
        return "channel"
    r1 = abs(d1) / width
    r5 = abs(d5) / width
    if r1 < CHANNEL_AT_1[0] or r1 > CHANNEL_AT_1[1]:
        return "channel"
    if r5 < CHANNEL_AT_5[0] or r5 > CHANNEL_AT_5[1]:
        return "channel"
    return None


def _pack_wave(
    kind: str,
    side: str,
    pts: list[dict],
    start: dict | None,
    min_pct: float,
    n_bars: int,
    window: int,
) -> dict:
    numbered = pts
    p1, p2, p4, p5 = numbered[0], numbered[1], numbered[3], numbered[4]
    status = "complete" if p5["confirmed"] else "forming"
    in_window = p5["i"] >= max(0, n_bars - window)
    target_now = _line_price(p5["i"], p1, p4)
    stop = p5["price"]
    return {
        "kind": kind,
        "side": side,
        "status": status,
        "in_window": in_window,
        "min_pct": min_pct,
        "start": None
        if start is None
        else {
            "kind": start["kind"],
            "i": start["i"],
            "dt": start["dt"],
            "price": start["price"],
        },
        "points": [
            {
                "n": n,
                "kind": p["kind"],
                "i": p["i"],
                "dt": p["dt"],
                "price": p["price"],
                "confirmed": p["confirmed"],
            }
            for n, p in enumerate(numbered, start=1)
        ],
        "legs": legs_from_pivots(([] if start is None else [start]) + numbered),
        "stop": stop,
        "target_1_4_at_5": round(target_now, 6),
        "neck_2_4": {
            "p2": p2["price"],
            "p4": p4["price"],
            "slope_px_per_bar": round(
                (p4["price"] - p2["price"]) / max(1, p4["i"] - p2["i"]), 8
            ),
        },
    }


def _right_wave(pts: list[dict], min_pct: float) -> tuple[dict | None, str | None]:
    if len(pts) != 5 or not _seq_ok(pts):
        return None, "sequence"
    p1, p2, p3, p4, p5 = pts
    if p5["kind"] == "low":
        side = "buy"
        if p2["kind"] != "high" or p4["kind"] != "high":
            return None, "sequence"
        if p4["price"] >= p2["price"]:
            return None, "neck_wrong_way"
        if p3["price"] >= p1["price"]:
            return None, "shoulder_not_smaller"
        if p5["price"] < p3["price"]:
            return None, "5_beyond_3"
    elif p5["kind"] == "high":
        side = "sell"
        if p2["kind"] != "low" or p4["kind"] != "low":
            return None, "sequence"
        if p4["price"] >= p2["price"]:
            return None, "neck_wrong_way"
        if p3["price"] <= p1["price"]:
            return None, "shoulder_not_smaller"
        if p5["price"] > p3["price"]:
            return None, "5_beyond_3"
    else:
        return None, "sequence"
    bad = _approaches(p2, p3, p4, p5) or _time_ok(pts) or _channel_ok(p1, p2, p3, p4, p5, min_pct)
    if bad:
        return None, bad
    return {"kind": "right", "side": side, "pts": pts, "start": None}, None


def _left_wave(pts6: list[dict], min_pct: float) -> tuple[dict | None, str | None]:
    if len(pts6) != 6 or not _seq_ok(pts6):
        return None, "sequence"
    highs = sum(1 for p in pts6 if p["kind"] == "high")
    lows = sum(1 for p in pts6 if p["kind"] == "low")
    if highs != 3 or lows != 3:
        return None, "not_three_and_three"
    start, p1, p2, p3, p4, p5 = pts6
    numbered = [p1, p2, p3, p4, p5]
    if p5["kind"] == "high":
        side = "sell"
        if p1["kind"] != "high" or p3["kind"] != "high":
            return None, "sequence"
        if p3["price"] <= p1["price"]:
            return None, "shoulder_not_smaller"
        if p5["price"] > p3["price"]:
            return None, "5_beyond_3"
    else:
        side = "buy"
        if p1["kind"] != "low" or p3["kind"] != "low":
            return None, "sequence"
        if p3["price"] >= p1["price"]:
            return None, "shoulder_not_smaller"
        if p5["price"] < p3["price"]:
            return None, "5_beyond_3"
    bad = (
        _approaches(p2, p3, p4, p5)
        or _time_ok(pts6)
        or _channel_ok(p1, p2, p3, p4, p5, min_pct)
    )
    if bad:
        return None, bad
    return {"kind": "left", "side": side, "pts": numbered, "start": start}, None


def find_waves(
    bars: list[Bar],
    min_pct: float,
    window: int,
) -> dict:
    pivots = swing_pivots(bars, min_pct)
    legs = legs_from_pivots(pivots)
    rejects: dict[str, int] = {}
    waves: list[dict] = []
    n = len(bars)

    def bump(reason: str) -> None:
        rejects[reason] = rejects.get(reason, 0) + 1

    def consider(raw: dict | None, reason: str | None) -> None:
        if raw is None:
            bump(reason or "reject")
            return
        wave = _pack_wave(
            raw["kind"],
            raw["side"],
            raw["pts"],
            raw["start"],
            min_pct,
            n,
            window,
        )
        key = (wave["kind"], wave["side"], wave["points"][4]["i"], wave["status"])
        if any(
            (w["kind"], w["side"], w["points"][4]["i"], w["status"]) == key for w in waves
        ):
            return
        waves.append(wave)

    confirmed = [p for p in pivots if p["confirmed"]]
    series_list = [confirmed]
    if pivots and not pivots[-1]["confirmed"] and confirmed:
        series_list.append(confirmed + [pivots[-1]])

    for series in series_list:
        for i in range(0, len(series) - 4):
            consider(*_right_wave(series[i : i + 5], min_pct))
        for i in range(0, len(series) - 5):
            consider(*_left_wave(series[i : i + 6], min_pct))

    waves.sort(key=lambda w: (w["points"][4]["i"], 0 if w["status"] == "complete" else 1))
    current = None
    for w in reversed(waves):
        if w["in_window"]:
            current = w
            if w["status"] == "complete":
                break
    return {
        "min_pct": min_pct,
        "window": window,
        "pivots": pivots,
        "legs": legs,
        "waves": waves,
        "current": current,
        "reject_counts": rejects,
    }


def study_waves(sec: str, class_code: str = "TQBR") -> dict:
    series = load_instrument(
        sec, class_code, tfs=WAVE_TFS, max_bars=dict(WAVE_LOOKBACK)
    )
    tfs: dict[str, dict] = {}
    clock = None
    for tf in WAVE_TFS:
        bars = series.get(tf) or []
        pack = find_waves(bars, WAVE_MIN_PCT[tf], WAVE_WINDOW[tf])
        last = bars[-1] if bars else None
        tfs[tf] = {
            "bars": len(bars),
            "last_bar": None if last is None else last.dt,
            "close": None if last is None else last.c,
            **pack,
        }
        if last is not None and (clock is None or last.dt > clock):
            clock = last.dt
    align_side = None
    align_tfs: list[str] = []
    sides = []
    for tf in WAVE_TFS:
        cur = (tfs.get(tf) or {}).get("current")
        if cur:
            sides.append((tf, cur["side"]))
    if sides:
        uniq = {s for _, s in sides}
        if len(uniq) == 1:
            align_side = next(iter(uniq))
            align_tfs = [tf for tf, _ in sides]
    return {
        "sec": sec,
        "class_code": class_code,
        "clock": clock,
        "tfs": tfs,
        "align": {"side": align_side, "tfs": align_tfs},
    }


def _fmt_dt(dt) -> str:
    if dt is None:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M")


def _fmt_pt(p: dict) -> str:
    k = "H" if p["kind"] == "high" else "L"
    return f"{p['n']} {k} {_fmt_dt(p['dt'])} {p['price']:.4f}"


def format_waves(report: dict) -> str:
    align = report.get("align") or {}
    lines = [
        f"{report['sec']} {report['class_code']}  clock={_fmt_dt(report.get('clock'))}  "
        f"waves (Krechetov-like heuristic)  M1x{WAVE_WINDOW['M1']} M10x{WAVE_WINDOW['M10']} "
        f"M30x{WAVE_WINDOW['M30']}"
    ]
    if align.get("side"):
        lines.append(f"  align {align['side']} on {', '.join(align.get('tfs') or [])}")
    else:
        lines.append("  align none (no same-side current wave across TFs)")
    for tf in WAVE_TFS:
        pack = (report.get("tfs") or {}).get(tf) or {}
        waves = pack.get("waves") or []
        legs = pack.get("legs") or []
        cur = pack.get("current")
        lines.append(
            f"\n=== {tf}  bars={pack.get('bars')}  last={_fmt_dt(pack.get('last_bar'))}  "
            f"C={pack.get('close')}  min_pct={pack.get('min_pct')}%  "
            f"pivots={len(pack.get('pivots') or [])}  waves={len(waves)}"
        )
        shown = [lg for lg in legs if lg.get("confirmed")][-8:]
        if shown:
            lines.append("  legs:")
            for lg in shown:
                lines.append(
                    f"    {lg['side']:<4} {lg['pct']:<6}  "
                    f"{_fmt_dt(lg['start_dt'])} {lg['start_px']:.4f} -> "
                    f"{_fmt_dt(lg['end_dt'])} {lg['end_px']:.4f}  bars={lg['bars']}"
                )
        if not cur:
            lines.append("  current: none")
        else:
            lines.append(
                f"  current: {cur['kind']} {cur['side']} {cur['status']}  "
                f"stop={cur['stop']:.4f}  target_1-4@{cur['target_1_4_at_5']:.4f}"
            )
            if cur.get("start"):
                s = cur["start"]
                k = "H" if s["kind"] == "high" else "L"
                lines.append(f"    0 {k} {_fmt_dt(s['dt'])} {s['price']:.4f}")
            for p in cur.get("points") or []:
                extra = "" if p.get("confirmed") else " forming"
                lines.append(f"    {_fmt_pt(p)}{extra}")
        extra = [w for w in waves if w is not cur][-3:]
        for w in extra:
            p5 = w["points"][4]
            lines.append(
                f"  also {w['kind']} {w['side']} {w['status']}  "
                f"p5={_fmt_dt(p5['dt'])} {p5['price']:.4f}"
            )
        rej = pack.get("reject_counts") or {}
        if rej and not cur:
            top = sorted(rej.items(), key=lambda kv: -kv[1])[:4]
            bits = ", ".join(f"{k}={v}" for k, v in top)
            lines.append(f"  rejects: {bits}")
    if report.get("files"):
        lines.append("")
        for tf in WAVE_TFS:
            path = (report.get("files") or {}).get(tf)
            if path:
                lines.append(f"  csv {tf}: {path}")
            path14 = (report.get("files") or {}).get(f"{tf}_14")
            if path14:
                lines.append(f"  csv {tf} 1-4: {path14}")
    return "\n".join(lines)


def format_pivot_dt(dt: datetime) -> str:
    return dt.strftime(DT_FMT)


def write_waves_csv(path: Path, pivots: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        fh.write("datetime;kind;price;confirmed\n")
        for p in pivots:
            dt = p["dt"]
            stamp = format_pivot_dt(dt) if isinstance(dt, datetime) else str(dt)
            conf = 1 if p.get("confirmed") else 0
            fh.write(f"{stamp};{p['kind']};{p['price']:.6f};{conf}\n")
    _replace_csv(tmp, path)


def last_zigzag_14(pivots: list[dict]) -> list[dict]:
    """1-4 of the last five confirmed zigzag pivots, even if geometry filters reject."""
    confirmed = [p for p in pivots if p.get("confirmed")]
    pts = confirmed[-5:]
    if len(pts) < 5:
        return []
    p5 = pts[4]
    side = "buy" if p5.get("kind") == "low" else "sell"
    return [
        {
            "kind": "zz",
            "side": side,
            "status": "zigzag",
            "points": [
                {"n": n, "dt": p["dt"], "price": p["price"]}
                for n, p in enumerate(pts, start=1)
            ],
        }
    ]


def target_rows(waves: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for w in waves:
        pts = w.get("points") or []
        if len(pts) < 4:
            continue
        p1, p4 = pts[0], pts[3]
        p5 = pts[4] if len(pts) > 4 else {}
        rows.append(
            {
                "dt1": p1["dt"],
                "px1": p1["price"],
                "dt4": p4["dt"],
                "px4": p4["price"],
                "dt5": p5.get("dt"),
                "px5": p5.get("price"),
                "side": w.get("side") or "",
                "kind": w.get("kind") or "",
                "status": w.get("status") or "",
            }
        )
    return rows


def write_targets_csv(path: Path, waves: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        fh.write("dt1;px1;dt4;px4;dt5;px5;side;kind;status\n")
        for row in target_rows(waves):
            dt1 = row["dt1"]
            dt4 = row["dt4"]
            dt5 = row["dt5"]
            s1 = format_pivot_dt(dt1) if isinstance(dt1, datetime) else str(dt1 or "")
            s4 = format_pivot_dt(dt4) if isinstance(dt4, datetime) else str(dt4 or "")
            s5 = (
                format_pivot_dt(dt5)
                if isinstance(dt5, datetime)
                else (str(dt5) if dt5 else "")
            )
            px5 = row["px5"]
            px5s = f"{px5:.6f}" if px5 is not None else ""
            fh.write(
                f"{s1};{row['px1']:.6f};{s4};{row['px4']:.6f};{s5};{px5s};"
                f"{row['side']};{row['kind']};{row['status']}\n"
            )
    _replace_csv(tmp, path)


def _replace_csv(tmp: Path, path: Path) -> None:
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


def targets_path(sec: str, class_code: str, tf: str, dest_dir: Path | None = None) -> Path:
    return (dest_dir or WAVES_DIR) / f"{sec}_{class_code}_{tf}_14.csv"


def export_waves(
    sec: str,
    class_code: str = "TQBR",
    dest_dir: Path | None = None,
    data_dir: Path | None = None,
    tfs: tuple[str, ...] | None = None,
) -> dict:
    dest = Path(dest_dir or WAVES_DIR)
    chosen = tfs or WAVE_TFS
    data_root = data_dir or BARS_DIR
    lookback = {tf: WAVE_LOOKBACK[tf] for tf in chosen if tf in WAVE_LOOKBACK}
    books = load_instrument(sec, class_code, data_root, tfs=chosen, max_bars=lookback)
    names = mark_sec_names(sec, class_code, data_root)
    files: dict[str, str] = {}
    counts: dict[str, dict] = {}
    tfs_pack: dict[str, dict] = {}
    clock = None
    for tf in chosen:
        bars = books.get(tf) or []
        pack = find_waves(bars, WAVE_MIN_PCT[tf], WAVE_WINDOW[tf])
        last = bars[-1] if bars else None
        tfs_pack[tf] = {
            "bars": len(bars),
            "last_bar": None if last is None else last.dt,
            "close": None if last is None else last.c,
            **pack,
        }
        if last is not None and (clock is None or last.dt > clock):
            clock = last.dt
        written = None
        written14 = None
        for name in names:
            path = marks_path(name, class_code, tf, dest)
            write_waves_csv(path, pack["pivots"])
            path14 = targets_path(name, class_code, tf, dest)
            write_targets_csv(path14, last_zigzag_14(pack["pivots"]))
            written = path
            written14 = path14
        files[tf] = str(written)
        if written14 is not None:
            files[f"{tf}_14"] = str(written14)
        n_piv = len(pack["pivots"])
        n_legs = len(pack["legs"])
        n_wav = len(pack["waves"])
        counts[tf] = {
            "pivots": n_piv,
            "legs": n_legs,
            "waves": n_wav,
            "onset": n_piv,
            "bars": len(bars),
            "buy": 0,
            "sell": 0,
            "buy1": 0,
            "sell1": 0,
            "buy2": 0,
            "sell2": 0,
        }
    align_side = None
    align_tfs: list[str] = []
    sides = []
    for tf in WAVE_TFS:
        cur = (tfs_pack.get(tf) or {}).get("current")
        if cur:
            sides.append((tf, cur["side"]))
    if sides:
        uniq = {s for _, s in sides}
        if len(uniq) == 1:
            align_side = next(iter(uniq))
            align_tfs = [tf for tf, _ in sides]
    return {
        "sec": sec,
        "class_code": class_code,
        "dir": str(dest),
        "clock": clock,
        "files": files,
        "counts": counts,
        "tfs": tfs_pack,
        "align": {"side": align_side, "tfs": align_tfs},
    }


def format_waves_export(report: dict, compact: bool = False) -> str:
    counts = report.get("counts") or {}
    if compact:
        bits = [
            f"{tf} piv={pack.get('pivots', 0)}/{pack.get('bars', 0)} 14={pack.get('waves', 0)}"
            for tf, pack in counts.items()
        ]
        when = report.get("exported_at") or ""
        prefix = f"{when}  " if when else ""
        body = "  ".join(bits)
        line = f"{prefix}{report['sec']} {report['class_code']}"
        return f"{line}  {body}" if body else line
    return format_waves(report)


def watch_waves(
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
    return watch_marks(
        sec,
        class_code,
        dest_dir=dest_dir or WAVES_DIR,
        data_dir=data_dir,
        tfs=tfs or WAVE_TFS,
        poll=poll,
        exporter=exporter or export_waves,
        sleeper=sleeper,
        stop=stop,
        log=log,
        formatter=format_waves_export,
        label="waves",
    )
