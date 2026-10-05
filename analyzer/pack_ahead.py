# -*- coding: utf-8 -*-
"""Similar forming D1 pack on D1 / H4 / M30; price to the next D1 close.

Last-bar pack only. Does not use the --odds overlay (odds evolved into --net).
"""

from __future__ import annotations

from datetime import datetime
from statistics import median

from analyzer.bars import BARS_DIR, load_instrument
from analyzer.odds import (
    MIN_PACK_TAGS,
    ODDS_MAX_BARS,
    SIM_MIN,
    append_forming,
    classify_outcome,
    flat_threshold,
    forming_d1,
    pack_feat,
    pack_sim,
    pack_tag_count,
    sample_shares,
    series_clock,
    tf_numeric,
)

PACK_AHEAD_TFS = ("D1", "H4", "M30")


def _tf_book(raw: dict, tf: str, clock: datetime) -> dict | None:
    m1 = raw.get("M1") or []
    fillers = m1 or raw.get("H4") or raw.get("M30") or []
    if tf == "D1":
        bars = forming_d1(raw.get("D1") or [], fillers)
    elif tf == "M1":
        bars = list(m1)
    else:
        bars = append_forming(raw.get(tf) or [], tf, m1, clock)
    if not bars:
        return None
    return tf_numeric(bars, tf)


def _next_d1(d1_packs: list[dict], analog_dt: datetime) -> dict | None:
    day = analog_dt.date()
    for pack in d1_packs:
        if pack["dt"].date() > day:
            return pack
    return None


def _feat_at(book: dict, i: int, tf: str, scales: dict) -> dict | None:
    packs = book["packs"]
    pack = packs[i]
    if pack.get("current", {}).get("rpm") is None:
        return None
    prev = packs[i - 1] if i else None
    if pack_tag_count(pack, scales, prev) < MIN_PACK_TAGS:
        return None
    feat = pack_feat(pack, prev, scales, tf)
    feat["i"] = i
    feat["tf"] = tf
    return feat


def _analogs_on(
    book: dict,
    tf: str,
    live: dict,
    scales: dict,
    d1_packs: list[dict],
    flat_pct: float,
    *,
    skip_last: bool,
    sim_min: float,
) -> list[dict]:
    hits: list[dict] = []
    last = len(book["packs"]) - 1
    for i in range(len(book["packs"])):
        if skip_last and i == last:
            continue
        feat = _feat_at(book, i, tf, scales)
        if feat is None:
            continue
        sim = pack_sim(feat, live, sim_min)
        if sim < sim_min:
            continue
        nxt = _next_d1(d1_packs, feat["dt"])
        live_d1 = d1_packs[-1]
        if nxt is None or feat["c"] <= 0:
            continue
        if nxt["dt"] == live_d1["dt"]:
            continue
        move = (nxt["c"] - feat["c"]) / feat["c"] * 100.0
        hits.append(
            {
                "tf": tf,
                "dt": feat["dt"],
                "c": feat["c"],
                "sim": sim,
                "next_dt": nxt["dt"],
                "next_c": nxt["c"],
                "move": move,
                "out": classify_outcome(feat["c"], nxt["c"], flat_pct),
            }
        )
    return hits


def pack_ahead(
    sec: str,
    class_code: str = "TQBR",
    *,
    sim_min: float = SIM_MIN,
    data_dir=None,
) -> dict:
    raw = load_instrument(
        sec,
        class_code,
        data_dir or BARS_DIR,
        tfs=("M1", "M30", "H4", "D1"),
        max_bars=ODDS_MAX_BARS,
        skip_missing=True,
    )
    clock = series_clock(raw)
    books = {tf: _tf_book(raw, tf, clock or datetime.min) for tf in PACK_AHEAD_TFS}
    d1 = books.get("D1")
    if not d1 or len(d1["packs"]) < 2:
        return {"sec": sec, "class_code": class_code, "error": "no D1 pack"}
    live_i = len(d1["packs"]) - 1
    live_scales = d1["scales"]
    live = _feat_at(d1, live_i, "D1", live_scales)
    if live is None:
        return {"sec": sec, "class_code": class_code, "error": "forming D1 is not a pack"}
    closes = [p["c"] for p in d1["packs"]]
    flat_pct = flat_threshold(closes)
    by_tf: dict[str, dict] = {}
    for tf in PACK_AHEAD_TFS:
        book = books.get(tf)
        if not book:
            by_tf[tf] = {"n": 0, "hits": [], "up": 0.0, "down": 0.0, "flat": 0.0, "med_move": 0.0}
            continue
        hits = _analogs_on(
            book,
            tf,
            live,
            live_scales,
            d1["packs"],
            flat_pct,
            skip_last=(tf == "D1"),
            sim_min=sim_min,
        )
        share = sample_shares([h["out"] for h in hits])
        moves = [h["move"] for h in hits]
        by_tf[tf] = {
            **share,
            "hits": hits,
            "med_move": float(median(moves)) if moves else 0.0,
        }
    last = d1["packs"][live_i]
    return {
        "sec": sec,
        "class_code": class_code,
        "clock": clock,
        "live_dt": last["dt"],
        "live_c": last["c"],
        "flat_pct": flat_pct,
        "live": live,
        "by_tf": by_tf,
    }


def format_pack_ahead(report: dict) -> str:
    if report.get("error"):
        return f"{report.get('sec')}  {report['error']}"
    live_dt = report["live_dt"]
    stamp = live_dt.strftime("%d.%m.%Y") if isinstance(live_dt, datetime) else str(live_dt)
    lines = [
        f"{report['sec']} {report['class_code']}  D1 forming {stamp} C={report['live_c']:.4f}  "
        f"flat={report['flat_pct']:.3f}%  (pack, not chain)"
    ]
    for tf in PACK_AHEAD_TFS:
        pack = report["by_tf"][tf]
        n = int(pack["n"])
        lines.append(
            f"  {tf}: n={n}  up={pack['up']:.1f}% down={pack['down']:.1f}% flat={pack['flat']:.1f}%"
            f"  med_move={pack['med_move']:+.3f}%"
        )
        shown = sorted(pack["hits"], key=lambda h: h["sim"], reverse=True)[:5]
        for hit in shown:
            dt = hit["dt"].strftime("%d.%m.%Y %H:%M") if isinstance(hit["dt"], datetime) else hit["dt"]
            lines.append(
                f"       {dt}  C={hit['c']:.4f}  {hit['out']} {hit['move']:+.3f}%  sim={hit['sim']:.2f}"
            )
    return "\n".join(lines)
