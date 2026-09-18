# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

INI_PATH = Path(r"C:\Users\koaln\RiderProjects\ScrQuik\RPM_TF_Up_5.ini")
O2O_INI = Path(r"C:\Users\koaln\RiderProjects\ScrQuik\One2One_121.ini")


@dataclass(slots=True)
class LayerSettings:
    tf: str
    period: int
    period_slow: int
    draw: int
    hist_draw: int
    div_draw: int
    label_draw: int

    def enabled(self) -> bool:
        return self.draw == 1 or self.hist_draw == 1 or self.div_draw == 1 or self.label_draw == 1


@dataclass(slots=True)
class UpSettings:
    chart_tf: str
    small: LayerSettings
    middle: LayerSettings
    up: LayerSettings
    div_seg_period: int
    div_segs_max: int
    div_pivot_span_max: int
    div_draw_hidden: int
    div_draw_weak: int


def _i(section, key: str, default: int = 0) -> int:
    return int(section.get(key, default))


def _layer(section, prefix: str, tf_key: str) -> LayerSettings:
    return LayerSettings(
        tf=section.get(tf_key, ""),
        period=_i(section, prefix + "_Period"),
        period_slow=_i(section, prefix + "_PeriodSlow"),
        draw=_i(section, prefix + "_Draw"),
        hist_draw=_i(section, prefix + "_HistDraw"),
        div_draw=_i(section, prefix + "_DivDraw"),
        label_draw=_i(section, prefix + "_LabelDraw"),
    )


def load_up_settings(chart_tf: str, ini_path: Path = INI_PATH) -> UpSettings:
    parser = configparser.ConfigParser()
    parser.read(ini_path, encoding="utf-8")
    name = f"RPM_TF_Up_5.{chart_tf}"
    if name not in parser:
        raise KeyError(f"no section [{name}] in {ini_path}")
    s = parser[name]
    return UpSettings(
        chart_tf=chart_tf,
        small=_layer(s, "1_Small", "1_Small_TF"),
        middle=_layer(s, "2_Middle", "2_Middle_TF"),
        up=_layer(s, "3_Up", "3_Up_TF"),
        div_seg_period=_i(s, "Div_SegPeriod", 2),
        div_segs_max=_i(s, "Div_SegsMax", 80),
        div_pivot_span_max=_i(s, "Div_PivotSpanMax", 1),
        div_draw_hidden=_i(s, "Div_DrawHidden"),
        div_draw_weak=_i(s, "Div_DrawWeak"),
    )


@dataclass(slots=True)
class One2OneSettings:
    depth: int
    deviation: int
    backstep: int
    ratio_tol: float
    sym_tol: float


def load_one2one_settings(ini_path: Path = O2O_INI) -> One2OneSettings:
    parser = configparser.ConfigParser()
    parser.read(ini_path, encoding="utf-8")
    if "One2One_121" not in parser:
        raise KeyError(f"no section [One2One_121] in {ini_path}")
    s = parser["One2One_121"]
    return One2OneSettings(
        depth=_i(s, "Depth", 12),
        deviation=_i(s, "Deviation", 5),
        backstep=_i(s, "Backstep", 3),
        ratio_tol=float(s.get("ratioTolerance", 0)),
        sym_tol=float(s.get("symmetryTolerance", 999)),
    )
