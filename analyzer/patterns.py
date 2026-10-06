# -*- coding: utf-8 -*-
"""Pair-bundle pattern search for shares and --train-net.

Pairs: связкаМ1М10, связкаМ5М10, связкаМ10М20. Each side a pack ≥5.
Chain window 5 bars of that TF. Analog sim ≥ 60% on both chains.
Outcome of a hit — next close of the senior TF of the pair.
Shares (n, up, down, flat) go into the net vector; not the pack frame.
"""

from __future__ import annotations

from analyzer.odds import (
    BUNDLE_NAMES,
    BUNDLE_PAIRS,
    CHAIN_BARS,
    MIN_PACK_TAGS,
    SIM_MIN,
    at_or_before_indices,
    chain_sim,
    classify_outcome,
    flat_threshold,
    pack_feat,
    pack_key,
    pack_tag_count,
    sample_shares,
)

PATTERN_FIELDS = ("ok", "up", "down", "flat")
PATTERN_PAIR_DIM = len(PATTERN_FIELDS)
PATTERN_DIM = PATTERN_PAIR_DIM * len(BUNDLE_PAIRS)


def empty_pattern_vec() -> list[float]:
    return [0.0] * PATTERN_DIM


def pair_chain_sim(
    hist_hi: list[dict],
    hist_lo: list[dict],
    live_hi: list[dict],
    live_lo: list[dict],
    sim_min: float = SIM_MIN,
) -> float:
    """Both TF chains of the pair must pass; then mean of the two sims."""
    hi = chain_sim(hist_hi, live_hi, sim_min)
    if hi < sim_min:
        return 0.0
    lo = chain_sim(hist_lo, live_lo, sim_min)
    if lo < sim_min:
        return 0.0
    return (hi + lo) / 2.0


def _chain_frame(feat: dict) -> dict:
    return {
        "pos": feat.get("pos") or {},
        "layers": feat.get("layers") or {},
        "geom": feat.get("geom") or {},
        "mag": feat.get("mag") or {},
        "current": feat.get("current") or {},
        "other": feat.get("other") or {},
        "key": feat.get("key") or (),
    }


def tf_chain_frames(
    book: dict,
    tf: str,
    *,
    length: int = CHAIN_BARS,
) -> list[list[dict] | None]:
    """5-bar chain ending at each pack of this TF, or None if a pack is short."""
    packs = book.get("packs") or []
    scales = book.get("scales") or {}
    feats: list[dict | None] = []
    for i, pack in enumerate(packs):
        prev = packs[i - 1] if i else None
        if pack.get("current", {}).get("rpm") is None:
            feats.append(None)
            continue
        if pack_tag_count(pack, scales, prev) < MIN_PACK_TAGS:
            feats.append(None)
            continue
        feat = pack_feat(pack, prev, scales, tf)
        feat["key"] = pack_key(pack, scales, prev)
        feats.append(feat)
    chains: list[list[dict] | None] = []
    for i in range(len(feats)):
        if i + 1 < length:
            chains.append(None)
            continue
        chunk = feats[i - length + 1 : i + 1]
        if any(item is None for item in chunk):
            chains.append(None)
            continue
        chains.append([_chain_frame(item) for item in chunk])
    return chains


def _pair_share_rows(
    hi_book: dict,
    lo_book: dict,
    senior: str,
    junior: str,
    *,
    sim_min: float = SIM_MIN,
    length: int = CHAIN_BARS,
) -> list[tuple[float, float, float, float]]:
    hi_chains = tf_chain_frames(hi_book, senior, length=length)
    lo_chains = tf_chain_frames(lo_book, junior, length=length)
    hi_packs = hi_book.get("packs") or []
    lo_packs = lo_book.get("packs") or []
    hi_closes = [p["c"] for p in hi_packs]
    lo_at_hi = at_or_before_indices(
        [p["dt"] for p in hi_packs],
        [p["dt"] for p in lo_packs],
    )
    flat_pct = flat_threshold(hi_closes)
    rows: list[tuple[float, float, float, float]] = []
    for j, live_hi in enumerate(hi_chains):
        lo_i = lo_at_hi[j] if j < len(lo_at_hi) else None
        live_lo = None
        if lo_i is not None and 0 <= lo_i < len(lo_chains):
            live_lo = lo_chains[lo_i]
        if live_hi is None or live_lo is None:
            rows.append((0.0, 0.0, 0.0, 0.0))
            continue
        hits: list[str] = []
        for jp in range(j):
            past_hi = hi_chains[jp]
            if past_hi is None:
                continue
            if jp + 1 >= j:
                continue
            lo_jp = lo_at_hi[jp] if jp < len(lo_at_hi) else None
            if lo_jp is None or lo_jp < 0 or lo_jp >= len(lo_chains):
                continue
            past_lo = lo_chains[lo_jp]
            if past_lo is None:
                continue
            if pair_chain_sim(past_hi, past_lo, live_hi, live_lo, sim_min) < sim_min:
                continue
            hits.append(classify_outcome(hi_closes[jp], hi_closes[jp + 1], flat_pct))
        share = sample_shares(hits)
        rows.append((1.0, share["up"] / 100.0, share["down"] / 100.0, share["flat"] / 100.0))
    return rows


def pattern_feat_series(
    books: dict[str, dict],
    align: dict[str, list[int | None]],
    n_m1: int,
    *,
    sim_min: float = SIM_MIN,
    length: int = CHAIN_BARS,
) -> list[list[float]]:
    """One 12-float vector per M1: ok/up/down/flat for each pair, aligned to senior slot."""
    tables: dict[tuple[str, str], list[tuple[float, float, float, float]]] = {}
    for senior, junior in BUNDLE_PAIRS:
        hi = books.get(senior)
        lo = books.get(junior)
        if not hi or not lo:
            tables[(senior, junior)] = []
            continue
        tables[(senior, junior)] = _pair_share_rows(
            hi, lo, senior, junior, sim_min=sim_min, length=length
        )
    out: list[list[float]] = []
    for i in range(n_m1):
        vec: list[float] = []
        for pair in BUNDLE_PAIRS:
            senior, _junior = pair
            rows = tables.get(pair) or []
            idxs = align.get(senior) or []
            sidx = idxs[i] if i < len(idxs) else None
            if sidx is None or sidx < 0 or sidx >= len(rows):
                vec.extend((0.0, 0.0, 0.0, 0.0))
                continue
            vec.extend(rows[sidx])
        if len(vec) != PATTERN_DIM:
            vec = empty_pattern_vec()
        out.append(vec)
    return out


def pattern_pair_names() -> tuple[str, ...]:
    return tuple(BUNDLE_NAMES[pair] for pair in BUNDLE_PAIRS)
