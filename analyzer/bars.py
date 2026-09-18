# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CHART_TFS = ("M1", "M10", "M30", "H4")
BARS_DIR = Path(r"C:\QuikFinam\LuaScripts\barsSaver\data")


@dataclass(slots=True)
class Bar:
    dt: datetime
    o: float
    h: float
    l: float
    c: float


def csv_path(sec: str, class_code: str, tf: str, data_dir: Path = BARS_DIR) -> Path:
    return data_dir / f"{sec}_{class_code}_{tf}_.csv"


def parse_dt(date_time: str) -> datetime:
    return datetime.strptime(date_time.strip(), "%d.%m.%Y %H:%M:%S")


def load_csv(path: Path) -> list[Bar]:
    if not path.is_file():
        raise FileNotFoundError(path)
    bars: list[Bar] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        header = fh.readline()
        if not header:
            return bars
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split(";")
            if len(parts) < 11:
                continue
            bars.append(
                Bar(
                    dt=parse_dt(parts[5]),
                    o=float(parts[7].replace(",", ".")),
                    h=float(parts[8].replace(",", ".")),
                    l=float(parts[9].replace(",", ".")),
                    c=float(parts[10].replace(",", ".")),
                )
            )
    return bars


def load_instrument(
    sec: str,
    class_code: str = "TQBR",
    data_dir: Path = BARS_DIR,
) -> dict[str, list[Bar]]:
    out: dict[str, list[Bar]] = {}
    missing: list[str] = []
    for tf in CHART_TFS:
        path = csv_path(sec, class_code, tf, data_dir)
        if not path.is_file():
            missing.append(str(path))
            continue
        out[tf] = load_csv(path)
    if missing:
        raise FileNotFoundError("missing barsSaver CSV: " + "; ".join(missing))
    return out


def typical(bar: Bar) -> float:
    return (bar.c * 2.0 + bar.h + bar.l) / 4.0
