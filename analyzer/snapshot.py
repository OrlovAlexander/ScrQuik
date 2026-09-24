# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from analyzer.bars import Bar, load_instrument, BARS_DIR
from analyzer.neighbors import neighbor_tfs, last_closed_indices
from analyzer.one2one import current_pattern
from analyzer.price import classify_moves
from analyzer.rpm_current import compute_current
from analyzer.rpm_up import compute_up
from analyzer.settings import load_one2one_settings, load_up_settings, hist_layer_names
from analyzer.states import current_tags, hist_tags, layer_tags, up_align_tags

CHART_TFS = ("H4", "M30", "M10", "M1")
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
            "draw": st.draw == 1,
            "hist_draw": st.hist_draw == 1,
            "agg_n": chunk.get("agg_n"),
        }
        if st.draw == 1:
            layers[name]["rpm"] = chunk.get("rpm")
            layers[name]["ema"] = chunk.get("ema")
        if st.hist_draw == 1:
            layers[name]["hist"] = chunk.get("hist")
            layers[name]["hist_up"] = chunk.get("hist_up")
            layers[name]["hist_dw"] = chunk.get("hist_dw")
    return {"layers": layers, "divs": up_out["divs"]}


def _at_or_before(bars: list[Bar], when: datetime) -> int | None:
    idx = None
    for i, b in enumerate(bars):
        if b.dt <= when:
            idx = i
        else:
            break
    return idx


def _attach_hist(line: dict | None, hist: dict | None) -> dict | None:
    if line is None:
        return dict(hist) if hist else None
    if hist is None:
        return line
    out = dict(line)
    out["hist_sign"] = hist.get("hist_sign")
    out["hist_dir"] = hist.get("hist_dir")
    out["hist_combo"] = hist.get("combo")
    return out


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
    windows: dict[str, list[Bar]] = {}
    rows: dict[str, dict] = {}
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
        moves = classify_moves(window, tf)
        cur_st = current_tags(current)
        small = layer_tags(up["series"], "small")
        middle = layer_tags(up["series"], "middle")
        hist_names = hist_layer_names(up_set)
        hist_name = hist_names[0] if hist_names else None
        hist_st = hist_tags(up["series"], hist_name) if hist_name else []
        align = up_align_tags(small, middle, hist_st if hist_st else [{} for _ in up["series"]])
        hist_last = None
        if hist_name and hist_st:
            hist_last = {
                **hist_st[-1],
                "layer": hist_name,
                "tf": getattr(up_set, hist_name).tf,
            }
        small_last = small[-1] if small else None
        middle_last = middle[-1] if middle else None
        hist_row = hist_st[-1] if hist_st else None
        if hist_name == "small":
            small_last = _attach_hist(small_last, hist_row)
        elif hist_name == "middle":
            middle_last = _attach_hist(middle_last, hist_row)
        pack = {
            "bars": len(window),
            "last_bar": window[-1].dt.isoformat(sep=" "),
            "close": window[-1].c,
            "price_move": moves[-1] if moves else None,
            "current": _last_current(current),
            "up": _last_up(up, up_set),
            "states": {
                "current": cur_st[-1] if cur_st else None,
                "up_small": small_last,
                "up_middle": middle_last,
                "up_hist": hist_last,
                "up_align": (align[-1] or {}).get("keys") if align else [],
            },
        }
        if tf == "M30":
            pack["one2one_121"] = current_pattern(window, settings=o2o)
        tfs[tf] = pack
        windows[tf] = window
        rows[tf] = {"moves": moves, "current": cur_st, "up_align": align}

    for tf, pack in tfs.items():
        if pack.get("error") or tf not in windows:
            continue
        neigh = {}
        for other in neighbor_tfs(tf):
            if other not in windows or tfs[other].get("error"):
                continue
            src = windows[other]
            idx = last_closed_indices([clock], [b.dt for b in src])[0]
            if idx is None:
                neigh[other] = {"status": "no_closed_bar"}
                continue
            src_rows = rows[other]
            align_row = src_rows["up_align"][idx] if src_rows["up_align"] else {}
            neigh[other] = {
                "status": "closed",
                "bar": src[idx].dt.isoformat(sep=" "),
                "close": src[idx].c,
                "price_move": src_rows["moves"][idx],
                "current": src_rows["current"][idx],
                "up_align": (align_row or {}).get("keys") or [],
            }
        pack["neighbors"] = neigh

    snap = {
        "sec": sec,
        "class_code": class_code,
        "clock": clock.isoformat(sep=" "),
        "tfs": tfs,
    }
    assert_layout(snap)
    return snap
