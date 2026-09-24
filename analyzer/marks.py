# -*- coding: utf-8 -*-
"""Export analyzer setups to CSV for the QUIK overlay indicator."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from analyzer.bars import BARS_DIR, Bar, csv_live_sec, csv_path, list_instruments, load_instrument, SEC_FILE_ALIASES
from analyzer.combo import tf_series

MARKS_DIR = Path(r"C:\QuikFinam\LuaIndicators\analyzer_marks")
MARKS_TFS = ("M1", "M10")
MARKS_MAX_BARS = {"M1": 6000, "M10": 2000}
DT_FMT = "%d.%m.%Y %H:%M:%S"
SETUP_CODE = {"none": 0, "buy": 1, "sell": 2, "buy1": 3, "sell1": 4, "buy2": 5, "sell2": 6}
_WRITE_TRIES = 6
_WRITE_WAIT = 0.12
DIRTY_BUDGET_SEC = 21.0


def format_mark_dt(dt: datetime) -> str:
    return dt.strftime(DT_FMT)


def mark_rows(series: list[dict]) -> list[dict]:
    """Tag the first bar of each setup run as onset."""
    rows: list[dict] = []
    prev = "none"
    for row in series:
        setup = row.get("setup") or "none"
        onset = 1 if setup != "none" and setup != prev else 0
        rows.append(
            {
                "dt": row["dt"],
                "setup": setup,
                "onset": onset,
                "code": SETUP_CODE.get(setup, 0),
            }
        )
        prev = setup
    return rows


def write_marks_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        fh.write("datetime;setup;onset;code\n")
        for row in rows:
            dt = row["dt"]
            stamp = format_mark_dt(dt) if isinstance(dt, datetime) else str(dt)
            fh.write(f"{stamp};{row['setup']};{row['onset']};{row['code']}\n")
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


def marks_path(sec: str, class_code: str, tf: str, dest_dir: Path | None = None) -> Path:
    return (dest_dir or MARKS_DIR) / f"{sec}_{class_code}_{tf}.csv"


def mark_sec_names(sec: str, class_code: str, data_dir: Path | None = None) -> list[str]:
    """File stems the chart may ask for: CR, CRZ6, CNY12.26."""
    names: list[str] = []
    for name in (sec, csv_live_sec(csv_path(sec, class_code, MARKS_TFS[0], data_dir or BARS_DIR))):
        if name and name not in names:
            names.append(name)
    for (alias, cls), (root, _rcls) in SEC_FILE_ALIASES.items():
        if cls == class_code and root in names and alias not in names:
            names.append(alias)
    return names


def count_marks(rows: list[dict]) -> dict:
    counts = {
        "bars": len(rows),
        "onset": 0,
        "buy": 0,
        "sell": 0,
        "buy1": 0,
        "sell1": 0,
        "buy2": 0,
        "sell2": 0,
        "none": 0,
    }
    for row in rows:
        setup = row["setup"]
        if setup in counts:
            counts[setup] += 1
        if row["onset"]:
            counts["onset"] += 1
    return counts


def export_marks(
    sec: str,
    class_code: str = "TQBR",
    dest_dir: Path | None = None,
    data_dir: Path | None = None,
    tfs: tuple[str, ...] | None = None,
) -> dict:
    dest = Path(dest_dir or MARKS_DIR)
    chosen = tfs or MARKS_TFS
    data_root = data_dir or BARS_DIR
    books = load_instrument(
        sec,
        class_code,
        data_root,
        tfs=chosen,
        max_bars=MARKS_MAX_BARS,
    )
    names = mark_sec_names(sec, class_code, data_root)
    files: dict[str, str] = {}
    counts: dict[str, dict] = {}
    for tf in chosen:
        bars: list[Bar] = books[tf]
        rows = mark_rows(tf_series(bars, tf, setups_only=True))
        written = None
        for name in names:
            path = marks_path(name, class_code, tf, dest)
            write_marks_csv(path, rows)
            written = path
        files[tf] = str(written)
        counts[tf] = count_marks(rows)
    return {
        "sec": sec,
        "class_code": class_code,
        "dir": str(dest),
        "files": files,
        "counts": counts,
    }


def format_marks(report: dict, compact: bool = False) -> str:
    counts = report.get("counts") or {}
    if compact:
        bits = [
            f"{tf} {pack['onset']}/{pack['bars']}"
            for tf, pack in counts.items()
        ]
        when = report.get("exported_at") or ""
        prefix = f"{when}  " if when else ""
        body = "  ".join(bits)
        line = f"{prefix}{report['sec']} {report['class_code']}"
        return f"{line}  {body}" if body else line
    lines = [
        f"{report['sec']} {report['class_code']}  marks -> {report['dir']}",
    ]
    for tf, pack in counts.items():
        lines.append(
            f"  {tf}: bars={pack['bars']} onset={pack['onset']} "
            f"buy={pack['buy']} sell={pack['sell']} buy1={pack['buy1']} sell1={pack['sell1']} "
            f"buy2={pack['buy2']} sell2={pack['sell2']}"
        )
        lines.append(f"       {report['files'][tf]}")
    return "\n".join(lines)


def bars_fingerprint(
    sec: str,
    class_code: str = "TQBR",
    data_dir: Path | None = None,
    tfs: tuple[str, ...] | None = None,
) -> tuple:
    """size + mtime of barsSaver CSVs; changes when a new bar is appended."""
    root = data_dir or BARS_DIR
    parts = []
    for tf in tfs or MARKS_TFS:
        path = csv_path(sec, class_code, tf, root)
        if not path.is_file():
            parts.append((tf, 0, 0))
            continue
        st = path.stat()
        parts.append((tf, st.st_size, st.st_mtime_ns))
    return tuple(parts)


def export_all_marks(
    class_code: str | None = None,
    dest_dir: Path | None = None,
    data_dir: Path | None = None,
    tfs: tuple[str, ...] | None = None,
    exporter: Callable[..., dict] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[dict]:
    run = exporter or export_marks
    emit = log or (lambda msg: print(msg, flush=True))
    items = list_instruments(data_dir or BARS_DIR, class_code=class_code, tfs=tfs or MARKS_TFS)
    emit(f"marks all  n={len(items)}  class={class_code or '*'}")
    reports: list[dict] = []
    for sec, cls in items:
        try:
            report = run(sec, cls, dest_dir=dest_dir, data_dir=data_dir, tfs=tfs)
            reports.append(report)
            emit(format_marks(report, compact=True))
        except Exception as exc:
            reports.append({"sec": sec, "class_code": cls, "error": str(exc)})
            emit(f"{sec} {cls}  error: {exc}")
    return reports


def watch_marks(
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
    """Re-export marks whenever barsSaver CSV files grow. Returns export count."""
    wait = max(1.0, float(poll))
    budget = max(wait, DIRTY_BUDGET_SEC)
    run = exporter or export_marks
    emit = log or (lambda msg: print(msg, flush=True))
    chosen = tfs or MARKS_TFS
    bars_root = data_dir or BARS_DIR
    dest = dest_dir or MARKS_DIR
    scope = sec or f"* {class_code or 'ALL'}"
    emit(f"watch {scope}  poll={wait:.0f}s  budget={budget:.0f}s  bars={bars_root}  marks={dest}")
    last: dict[tuple[str, str, str], tuple] = {}
    exports = 0
    cycle = 0
    while not (stop and stop()):
        cycle += 1
        t0 = time.monotonic()
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            if sec:
                universe = [(sec, class_code or "TQBR")]
            else:
                universe = list_instruments(bars_root, class_code=class_code, tfs=chosen)
            dirty: list[tuple[str, str, str, tuple]] = []
            dirty_by_tf: dict[str, int] = {tf: 0 for tf in chosen}
            for tf in chosen:
                for name, cls in universe:
                    fp = bars_fingerprint(name, cls, bars_root, (tf,))
                    if fp != last.get((name, cls, tf)):
                        dirty.append((name, cls, tf, fp))
                        dirty_by_tf[tf] = dirty_by_tf.get(tf, 0) + 1
            tf_bits = " ".join(f"{tf}={dirty_by_tf.get(tf, 0)}" for tf in chosen)
            emit(f"{stamp}  poll#{cycle}  n={len(universe)}  dirty={len(dirty)}  {tf_bits}")
            done = 0
            for name, cls, tf, fp in dirty:
                if done and (time.monotonic() - t0) >= budget:
                    left = len(dirty) - done
                    emit(f"{stamp}  defer {left}  next poll")
                    break
                try:
                    report = run(
                        name,
                        cls,
                        dest_dir=dest,
                        data_dir=bars_root,
                        tfs=(tf,),
                    )
                    report["exported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    emit(format_marks(report, compact=True))
                    last[(name, cls, tf)] = fp
                    exports += 1
                    done += 1
                except FileNotFoundError as exc:
                    last.pop((name, cls, tf), None)
                    emit(f"watch wait {name} {tf}: {exc}")
                except Exception as exc:
                    emit(f"watch error {name} {tf}: {exc}")
        except KeyboardInterrupt:
            emit("watch stopped")
            break
        elapsed = time.monotonic() - t0
        rest = wait - elapsed
        if stop and stop():
            break
        if rest > 0:
            sleeper(rest)
    return exports
