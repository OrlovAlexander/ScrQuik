# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from analyzer.bars import Bar, load_instrument, BARS_DIR
from analyzer.one2one import current_pattern
from analyzer.rpm_current import compute_current
from analyzer.rpm_up import compute_up
from analyzer.settings import load_one2one_settings, load_up_settings

CHART_TFS = ("M1", "M10", "M30", "H4")
UP_TF = {
    "M1": {"small": "Mn5", "middle": "Mn10", "up": "Mn20"},
    "M10": {"small": "Mn20", "middle": "Mn30", "up": "H2"},
    "M30": {"small": "H1", "middle": "H2", "up": "H4"},
    "H4": {"small": "H12", "middle": "D1", "up": "W1"},
}


def assert_layout(snap: dict) -> None:
    tfs = snap.get("tfs") or {}
    missing = [tf for tf in CHART_TFS if tf not in tfs]
    if missing:
        raise RuntimeError(f"missing TFs: {missing}")
    for tf in CHART_TFS:
        pack = tfs[tf]
        if pack.get("error"):
            raise RuntimeError(f"{tf}: {pack['error']}")
        if not pack.get("current") or pack["current"].get("rpm") is None:
            raise RuntimeError(f"{tf}: RPM-current missing")
        up = pack.get("up") or {}
        layers = up.get("layers") or {}
        expect = UP_TF[tf]
        for name, tf_name in expect.items():
            layer = layers.get(name) or {}
            if layer.get("tf") != tf_name:
                raise RuntimeError(f"{tf} up.{name} tf={layer.get('tf')} expected {tf_name}")
        if tf == "M30":
            if "one2one_121" not in pack:
                raise RuntimeError("M30: One2One_121 missing")
        elif "one2one_121" in pack:
            raise RuntimeError(f"{tf}: One2One_121 must not be present")


def _last_current(rows: list[dict]) -> dict | None:
    for row in reversed(rows):
        if row.get("rpm") is not None:
            return {
                "dt": row["dt"].isoformat(sep=" ") if isinstance(row["dt"], datetime) else row["dt"],
                "rpm": row["rpm"],
                "ema": row["ema"],
            }
    return None


def _last_up(up_out: dict, settings) -> dict:
    series = up_out["series"]
    last = series[-1] if series else {}
    layers = {}
    cfg = {"small": settings.small, "middle": settings.middle, "up": settings.up}
    for name in ("small", "middle", "up"):
        chunk = last.get(name) or {}
        st = cfg[name]
        layers[name] = {
            "tf": chunk.get("tf") or up_out["layers"][name],
            "enabled": st.enabled(),
            "rpm": chunk.get("rpm"),
            "ema": chunk.get("ema"),
            "hist": chunk.get("hist"),
            "hist_up": chunk.get("hist_up"),
            "hist_dw": chunk.get("hist_dw"),
            "agg_n": chunk.get("agg_n"),
        }
    return {"layers": layers, "divs": up_out["divs"]}


def _at_or_before(bars: list[Bar], when: datetime) -> int | None:
    idx = None
    for i, b in enumerate(bars):
        if b.dt <= when:
            idx = i
        else:
            break
    return idx


def analyze_instrument(
    sec: str,
    class_code: str = "TQBR",
    data_dir: Path | None = None,
    when: datetime | None = None,
) -> dict:
    books = load_instrument(sec, class_code, data_dir or BARS_DIR)

    clock = when
    if clock is None:
        clock = max(books[tf][-1].dt for tf in CHART_TFS if books.get(tf))

    o2o = load_one2one_settings()
    tfs: dict[str, dict] = {}
    for tf in CHART_TFS:
        bars = books[tf]
        cut = _at_or_before(bars, clock)
        if cut is None:
            tfs[tf] = {"bars": 0, "error": "no bars at/before clock"}
            continue
        window = bars[: cut + 1]
        current = compute_current(window)
        up_set = load_up_settings(tf)
        up = compute_up(window, up_set)
        pack = {
            "bars": len(window),
            "last_bar": window[-1].dt.isoformat(sep=" "),
            "close": window[-1].c,
            "current": _last_current(current),
            "up": _last_up(up, up_set),
        }
        if tf == "M30":
            pack["one2one_121"] = current_pattern(window, settings=o2o)
        tfs[tf] = pack

    snap = {
        "sec": sec,
        "class_code": class_code,
        "clock": clock.isoformat(sep=" "),
        "tfs": tfs,
    }
    assert_layout(snap)
    return snap
