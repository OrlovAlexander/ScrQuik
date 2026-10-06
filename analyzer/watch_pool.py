# -*- coding: utf-8 -*-
"""Supervisor: --watch-net worker processes sharded across instruments."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from analyzer.bars import BARS_DIR, KNOWN_TFS, list_instruments
from analyzer.net import NET_WATCH_TFS

REPO_ROOT = Path(__file__).resolve().parent.parent
JOBS_CAP = 8
BLAS_THREAD_KEYS = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def parse_watch_only(raw: str | None) -> list[tuple[str, str]] | None:
    """'GAZP:TQBR,CNY12.26:SPBFUT' or 'GAZP' (TQBR)."""
    if not raw or not raw.strip():
        return None
    out: list[tuple[str, str]] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        if ":" in token:
            sec, cls = token.split(":", 1)
            out.append((sec.strip(), (cls.strip() or "TQBR")))
        else:
            out.append((token, "TQBR"))
    return out or None


def auto_jobs(
    n: int,
    jobs: int | None,
    *,
    cpu: int | None = None,
    cap: int = JOBS_CAP,
) -> int:
    """None → CPU count capped at `cap`. 0 or less → one process per instrument.

    Explicit positive `jobs` is also capped: >~8 concurrent export_net thrash
    RAM/CPU so CSV updates look frozen.
    """
    if n <= 0:
        return 0
    limit = max(1, int(cap))
    if jobs is None:
        cores = cpu if cpu is not None else (os.cpu_count() or 4)
        return max(1, min(n, int(cores), limit))
    if jobs <= 0:
        return n
    return max(1, min(int(jobs), n, limit))


def split_universe(
    universe: list[tuple[str, str]],
    jobs: int,
) -> list[list[tuple[str, str]]]:
    """jobs<=0 → one shard per instrument. Else round-robin into `jobs` shards."""
    if not universe:
        return []
    n = len(universe)
    n_jobs = n if jobs <= 0 else max(1, min(int(jobs), n))
    shards: list[list[tuple[str, str]]] = [[] for _ in range(n_jobs)]
    for i, item in enumerate(universe):
        shards[i % n_jobs].append(item)
    return [shard for shard in shards if shard]


def worker_cmd(shard: list[tuple[str, str]], poll: float) -> list[str]:
    cmd = [sys.executable, "-u", "-m", "analyzer", "--watch-net", "--poll", str(poll)]
    if len(shard) == 1:
        sec, cls = shard[0]
        cmd.extend(["--sec", sec, "--class-code", cls])
        return cmd
    packed = ",".join(f"{sec}:{cls}" for sec, cls in shard)
    cmd.extend(["--watch-only", packed])
    return cmd


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    for key in BLAS_THREAD_KEYS:
        env[key] = "1"
    return env


def watch_net_pool(
    class_code: str | None = None,
    *,
    data_dir: Path | None = None,
    poll: float = 11.0,
    jobs: int | None = None,
    sleeper=time.sleep,
    stop=None,
    log=None,
    popen=subprocess.Popen,
    spawn_pause: float = 0.15,
) -> int:
    """Spawn `--watch-net` subprocesses. jobs=None → CPU count, max JOBS_CAP."""
    emit = log or (lambda msg: print(msg, flush=True))
    bars_root = data_dir or BARS_DIR
    universe = list_instruments(bars_root, class_code=class_code, tfs=NET_WATCH_TFS)
    if not universe:
        universe = list_instruments(bars_root, class_code=class_code, tfs=KNOWN_TFS)
    if not universe:
        emit("watch-net-pool: no instruments in barsSaver")
        return 0
    n_jobs = auto_jobs(len(universe), jobs)
    shards = split_universe(universe, n_jobs)
    how = "auto" if jobs is None else str(jobs)
    emit(
        f"watch-net-pool instruments={len(universe)} workers={len(shards)} "
        f"jobs={how}  poll={poll:.0f}s  bars={bars_root}"
    )
    for i, shard in enumerate(shards, start=1):
        names = ",".join(sec for sec, _cls in shard)
        emit(f"  worker {i}/{len(shards)}  {names}")
    kw: dict = {
        "env": _worker_env(),
        "cwd": str(REPO_ROOT),
        "stdin": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    cmds = [worker_cmd(shard, poll) for shard in shards]
    workers: list[dict] = []
    try:
        for cmd in cmds:
            proc = _spawn(popen, cmd, kw, emit)
            workers.append({"cmd": cmd, "proc": proc, "fails": 0, "next": 0.0})
            if spawn_pause:
                sleeper(spawn_pause)
        while workers and not (stop and stop()):
            now = time.monotonic()
            for w in workers:
                proc = w["proc"]
                if proc is None:
                    if now < w["next"]:
                        continue
                    w["proc"] = _spawn(popen, w["cmd"], kw, emit)
                    continue
                code = proc.poll()
                if code is None:
                    w["fails"] = 0
                    continue
                if stop and stop():
                    break
                w["fails"] = min(int(w["fails"]) + 1, 4)
                delay = min(30.0, 2.0 ** w["fails"])
                emit(f"watch-net-pool worker exit={code} retry in {delay:.0f}s")
                w["proc"] = None
                w["next"] = now + delay
            sleeper(1.0)
    except KeyboardInterrupt:
        emit("watch-net-pool stopping")
    finally:
        _stop_workers([w["proc"] for w in workers if w.get("proc") is not None], emit)
    return len(shards)


def _spawn(popen, cmd: list[str], kw: dict, emit):
    try:
        return popen(cmd, **kw)
    except OSError as exc:
        emit(f"watch-net-pool spawn failed: {exc}")
        return None


def _stop_workers(procs: list, emit) -> None:
    for proc in procs:
        if proc is None or proc.poll() is not None:
            continue
        try:
            proc.terminate()
        except OSError:
            pass
    deadline = time.monotonic() + 8.0
    for proc in procs:
        if proc is None:
            continue
        wait = deadline - time.monotonic()
        if wait <= 0:
            break
        try:
            proc.wait(timeout=wait)
        except Exception:
            pass
    for proc in procs:
        if proc is None or proc.poll() is not None:
            continue
        emit("watch-net-pool kill hung worker")
        try:
            proc.kill()
        except OSError:
            pass
