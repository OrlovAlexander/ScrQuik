# -*- coding: utf-8 -*-
"""Discrete RPM-current / RPM-up tags for the snapshot."""

from __future__ import annotations

from statistics import median

NEAR_ZERO = 0.25
NEAR_EMA = 0.15
NEAR_HIST = 0.15
NEAR_SLOPE = 0.08
EMA_TREND_BARS = 5


def _median_abs(values: list[float | None]) -> float:
    xs = [abs(v) for v in values if v is not None]
    if not xs:
        return 1.0
    m = float(median(xs))
    return m if m > 0 else 1.0


def _side(value: float | None, scale: float, near: float) -> str:
    if value is None:
        return "na"
    if abs(value) < near * scale:
        return "near_0"
    return "above_0" if value > 0 else "below_0"


def _vs_ema(rpm: float | None, ema: float | None, scale: float) -> str:
    if rpm is None or ema is None:
        return "na"
    if abs(rpm - ema) < NEAR_EMA * scale:
        return "near_ema"
    return "above_ema" if rpm > ema else "below_ema"


def _slope_only(value: float | None, prev: float | None, scale: float) -> str:
    if value is None or prev is None:
        return "na"
    delta = value - prev
    if abs(delta) < NEAR_SLOPE * scale:
        return "flat"
    return "rising" if delta > 0 else "falling"


def _slope_tag(rpm: float | None, prev: float | None, ema: float | None, scale: float) -> str:
    if rpm is None or prev is None or ema is None:
        return "na"
    rel = _slope_only(rpm, prev, scale)
    if rpm > ema:
        band = "above_ema"
    elif rpm < ema:
        band = "below_ema"
    else:
        band = "at_ema"
    return f"{rel}_{band}"


def _ema_state(ema: float | None, prev_ema: float | None, scale: float) -> tuple[str, str]:
    return _side(ema, scale, NEAR_ZERO), _slope_only(ema, prev_ema, scale)


def current_tags(rows: list[dict]) -> list[dict]:
    rpm_scale = _median_abs([r.get("rpm") for r in rows])
    ema_scale = _median_abs([r.get("ema") for r in rows])
    out: list[dict] = []
    prev_rpm: float | None = None
    prev_ema: float | None = None
    ema_hist: list[float | None] = []
    for row in rows:
        rpm = row.get("rpm")
        ema = row.get("ema")
        vs0 = _side(rpm, rpm_scale, NEAR_ZERO)
        vs_ema = _vs_ema(rpm, ema, rpm_scale)
        slope = _slope_tag(rpm, prev_rpm, ema, rpm_scale)
        ema_vs0, ema_slope = _ema_state(ema, prev_ema, ema_scale)
        ema_hist.append(ema)
        ema_trend = "na"
        if len(ema_hist) > EMA_TREND_BARS:
            older = ema_hist[-1 - EMA_TREND_BARS]
            if ema is not None and older is not None:
                ema_trend = _slope_only(ema, older, ema_scale)
        combo = None
        if rpm is not None and ema is not None:
            combo = f"{vs0}|{vs_ema}|{slope}"
        out.append(
            {
                "vs0": vs0,
                "vs_ema": vs_ema,
                "slope": slope,
                "ema_vs0": ema_vs0,
                "ema_slope": ema_slope,
                "ema_trend": ema_trend,
                "combo": combo,
            }
        )
        if rpm is not None:
            prev_rpm = rpm
        if ema is not None:
            prev_ema = ema
    return out


def _hist_dir(chunk: dict) -> str:
    """Growing = bar getting taller away from zero.

    Above 0 that is hist_up (more positive). Below 0 that is hist_dw
    (more negative, grows downward). Toward zero is shrinking.
    """
    up = chunk.get("hist_up") is not None
    dw = chunk.get("hist_dw") is not None
    if not up and not dw:
        return "na"
    hist = chunk.get("hist")
    if hist is not None and hist < 0:
        return "hist_growing" if dw else "hist_shrinking"
    return "hist_growing" if up else "hist_shrinking"


def layer_tags(series: list[dict], name: str) -> list[dict]:
    """Small/middle: RPM line vs zero and its EMA; EMA vs zero and EMA slope."""
    rpms = [(row.get(name) or {}).get("rpm") for row in series]
    emas = [(row.get(name) or {}).get("ema") for row in series]
    rpm_scale = _median_abs(rpms)
    ema_scale = _median_abs(emas)
    out: list[dict] = []
    prev_rpm: float | None = None
    prev_ema: float | None = None
    ema_hist: list[float | None] = []
    for row in series:
        chunk = row.get(name) or {}
        rpm = chunk.get("rpm")
        ema = chunk.get("ema")
        vs0 = _side(rpm, rpm_scale, NEAR_ZERO)
        vs_ema = _vs_ema(rpm, ema, rpm_scale)
        slope = _slope_tag(rpm, prev_rpm, ema, rpm_scale)
        ema_vs0, ema_slope = _ema_state(ema, prev_ema, ema_scale)
        ema_hist.append(ema)
        ema_trend = "na"
        if len(ema_hist) > EMA_TREND_BARS:
            older = ema_hist[-1 - EMA_TREND_BARS]
            if ema is not None and older is not None:
                ema_trend = _slope_only(ema, older, ema_scale)
        combo = None
        if rpm is not None and ema is not None:
            combo = f"{vs0}|{vs_ema}|{slope}|ema_{ema_vs0}|ema_{ema_slope}"
        out.append(
            {
                "vs0": vs0,
                "vs_ema": vs_ema,
                "slope": slope,
                "ema_vs0": ema_vs0,
                "ema_slope": ema_slope,
                "ema_trend": ema_trend,
                "combo": combo,
            }
        )
        if rpm is not None:
            prev_rpm = rpm
        if ema is not None:
            prev_ema = ema
    return out


def hist_tags(series: list[dict], name: str = "up") -> list[dict]:
    """Histogram sign and direction. No RPM line, no EMA."""
    hists = [(row.get(name) or {}).get("hist") for row in series]
    hist_scale = _median_abs(hists)
    out: list[dict] = []
    for row in series:
        chunk = row.get(name) or {}
        hist = chunk.get("hist")
        hist_sign = _side(hist, hist_scale, NEAR_HIST)
        hist_dir = _hist_dir(chunk)
        combo = None
        if hist is not None:
            combo = f"{hist_sign}|{hist_dir}"
        out.append({"hist_sign": hist_sign, "hist_dir": hist_dir, "combo": combo})
    return out


def _align_rpm(small: dict, middle: dict) -> str | None:
    signs = [s for s in (small.get("vs0"), middle.get("vs0")) if s not in {None, "na"}]
    if len(signs) < 2:
        return None
    if all(s == "above_0" for s in signs):
        return "small_middle_above_0"
    if all(s == "below_0" for s in signs):
        return "small_middle_below_0"
    if all(s == "near_0" for s in signs):
        return "small_middle_near_0"
    return "small_middle_mixed"


def _align_ema(small: dict, middle: dict) -> str | None:
    signs = [s for s in (small.get("ema_vs0"), middle.get("ema_vs0")) if s not in {None, "na"}]
    if len(signs) < 2:
        return None
    if all(s == "above_0" for s in signs):
        return "small_middle_ema_above_0"
    if all(s == "below_0" for s in signs):
        return "small_middle_ema_below_0"
    if all(s == "near_0" for s in signs):
        return "small_middle_ema_near_0"
    return "small_middle_ema_mixed"


def _align_up_hist(up: dict) -> str | None:
    sign = up.get("hist_sign")
    direction = up.get("hist_dir")
    if sign in {None, "na"} or direction in {None, "na"}:
        return None
    short = direction.replace("hist_", "")
    return f"up_hist_{sign}_{short}"


def _stack_disagree(small: dict, middle: dict) -> str | None:
    a, b = small.get("vs0"), middle.get("vs0")
    if a in {None, "na"} or b in {None, "na"}:
        return None
    if a == "above_0" and b == "below_0":
        return "small_above_middle_below"
    if a == "below_0" and b == "above_0":
        return "small_below_middle_above"
    return None


def up_align_tags(small: list[dict], middle: list[dict], up: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s, m, u in zip(small, middle, up):
        keys = []
        for tag in (_align_rpm(s, m), _align_ema(s, m), _stack_disagree(s, m), _align_up_hist(u)):
            if tag:
                keys.append(tag)
        out.append({"keys": keys})
    return out
