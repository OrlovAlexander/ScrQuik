# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CHART_TFS = ("M1", "M10", "M30", "H4")
BARS_DIR = Path(r"C:\QuikFinam\LuaScripts\barsSaver\data")
SEC_FILE_ALIASES = {
    ("CNY12.26", "SPBFUT"): ("CR", "SPBFUT"),
    ("CNY-12.26", "SPBFUT"): ("CR", "SPBFUT"),
    ("CRZ6", "SPBFUT"): ("CR", "SPBFUT"),
}


def csv_path(sec: str, class_code: str, tf: str, data_dir: Path = BARS_DIR) -> Path:
    """Resolve barsSaver CSV; futures may live under a short root (CRZ6 -> CR)."""
    root = data_dir or BARS_DIR
    candidates = [root / f"{sec}_{class_code}_{tf}_.csv"]
    alias = SEC_FILE_ALIASES.get((sec, class_code))
    if alias:
        candidates.append(root / f"{alias[0]}_{alias[1]}_{tf}_.csv")
    if class_code == "SPBFUT" and len(sec) > 2:
        candidates.append(root / f"{sec[:-2]}_{class_code}_{tf}_.csv")
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def csv_live_sec(path: Path) -> str | None:
    """Sec code from the first data row (CRZ6 inside CR_SPBFUT_*.csv)."""
    if not path.is_file():
        return None
    with path.open(encoding="utf-8", errors="replace") as fh:
        fh.readline()
        line = fh.readline()
    if not line:
        return None
    bit = line.split(";")[0].strip()
    return bit or None


@dataclass(slots=True)
class Bar:
    dt: datetime
    o: float
    h: float
    l: float
    c: float


def parse_dt(date_time: str) -> datetime:
    return datetime.strptime(date_time.strip(), "%d.%m.%Y %H:%M:%S")


def _parse_bar_line(line: str) -> Bar | None:
    line = line.strip()
    if not line:
        return None
    parts = line.split(";")
    if len(parts) < 11:
        return None
    try:
        return Bar(
            dt=parse_dt(parts[5]),
            o=float(parts[7].replace(",", ".")),
            h=float(parts[8].replace(",", ".")),
            l=float(parts[9].replace(",", ".")),
            c=float(parts[10].replace(",", ".")),
        )
    except ValueError:
        return None


def load_csv(path: Path, max_bars: int | None = None) -> list[Bar]:
    if not path.is_file():
        raise FileNotFoundError(path)
    if max_bars is None:
        bars: list[Bar] = []
        with path.open(encoding="utf-8", errors="replace") as fh:
            fh.readline()
            for line in fh:
                bar = _parse_bar_line(line)
                if bar is not None:
                    bars.append(bar)
        return bars
    limit = max(1, int(max_bars))
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        nbytes = min(size, max(65536, limit * 200 + 4096))
        fh.seek(max(0, size - nbytes), 0)
        raw = fh.read()
    text = raw.decode("utf-8", errors="replace")
    if size > nbytes:
        cut = text.find("\n")
        if cut >= 0:
            text = text[cut + 1 :]
    bars = []
    for line in text.splitlines():
        bar = _parse_bar_line(line)
        if bar is not None:
            bars.append(bar)
    if len(bars) > limit:
        bars = bars[-limit:]
    return bars


def load_instrument(
    sec: str,
    class_code: str = "TQBR",
    data_dir: Path = BARS_DIR,
    tfs: tuple[str, ...] | None = None,
    max_bars: int | dict[str, int] | None = None,
) -> dict[str, list[Bar]]:
    out: dict[str, list[Bar]] = {}
    missing: list[str] = []
    for tf in tfs or CHART_TFS:
        path = csv_path(sec, class_code, tf, data_dir)
        if not path.is_file():
            missing.append(str(path))
            continue
        limit = max_bars.get(tf) if isinstance(max_bars, dict) else max_bars
        out[tf] = load_csv(path, max_bars=limit)
    if missing:
        raise FileNotFoundError("missing barsSaver CSV: " + "; ".join(missing))
    return out


def typical(bar: Bar) -> float:
    return (bar.c * 2.0 + bar.h + bar.l) / 4.0


def parse_bars_filename(name: str) -> tuple[str, str, str] | None:
    """Parse GAZP_TQBR_M10_.csv -> (sec, class_code, tf)."""
    if not name.endswith("_.csv"):
        return None
    core = name[:-5]
    for tf in sorted(CHART_TFS, key=len, reverse=True):
        token = "_" + tf
        if core.endswith(token):
            head = core[: -len(token)]
            sec, sep, class_code = head.rpartition("_")
            if sep and sec and class_code:
                return sec, class_code, tf
            return None
    return None


def list_instruments(
    data_dir: Path | None = None,
    class_code: str | None = None,
    tfs: tuple[str, ...] | None = None,
) -> list[tuple[str, str]]:
    """Instruments in barsSaver data that have every requested TF."""
    root = data_dir or BARS_DIR
    need = set(tfs or CHART_TFS)
    found: dict[tuple[str, str], set[str]] = {}
    if not root.is_dir():
        return []
    for path in root.glob("*.csv"):
        parsed = parse_bars_filename(path.name)
        if parsed is None:
            continue
        sec, cls, tf = parsed
        if class_code and cls != class_code:
            continue
        if tf not in need:
            continue
        found.setdefault((sec, cls), set()).add(tf)
    return sorted(key for key, have in found.items() if have >= need)
