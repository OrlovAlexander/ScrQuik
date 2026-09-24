# -*- coding: utf-8 -*-
from __future__ import annotations

import struct
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WND = Path(r"C:\QuikFinam\finam.wnd")
OUT = REPO_ROOT / "config" / "RPM_TF_Up_5.ini"

KEYS_ORDER = [
    "Name",
    "1_Small_TF",
    "1_Small_Period",
    "1_Small_PeriodSlow",
    "1_Small_Draw",
    "1_Small_HistDraw",
    "1_Small_DivDraw",
    "1_Small_LabelDraw",
    "2_Middle_TF",
    "2_Middle_Period",
    "2_Middle_PeriodSlow",
    "2_Middle_Draw",
    "2_Middle_HistDraw",
    "2_Middle_DivDraw",
    "2_Middle_LabelDraw",
    "3_Up_TF",
    "3_Up_Period",
    "3_Up_PeriodSlow",
    "3_Up_Draw",
    "3_Up_HistDraw",
    "3_Up_DivDraw",
    "3_Up_LabelDraw",
    "Div_SegPeriod",
    "Div_SegsMax",
    "Div_PivotSpanMax",
    "Div_DrawHidden",
    "Div_DrawWeak",
    "Div_Log",
]

# RPM-up layers are higher than the chart; live packs map 1:1 to these TFs.
CHART_TF_BY_SMALL = {
    "Mn5": "M1",
    "Mn20": "M10",
    "H1": "M30",
    "H12": "H4",
}
TF_ORDER = ["M1", "M10", "M30", "H4"]


def parse_entries(data: bytes, start: int, end: int) -> list[tuple[int, str, object]]:
    out: list[tuple[int, str, object]] = []
    i = max(0, start)
    end = min(end, len(data))
    while i + 8 <= end:
        typ, key_len = struct.unpack_from("<II", data, i)
        if not (1 <= key_len <= 80):
            i += 1
            continue
        key_b = data[i + 8 : i + 8 + key_len]
        if not key_b.isascii() or not all(32 <= b <= 126 for b in key_b):
            i += 1
            continue
        key = key_b.decode("ascii")
        j = i + 8 + key_len
        if j + 4 > len(data):
            break
        if typ == 1:
            slen = struct.unpack_from("<I", data, j)[0]
            if slen > 400 or j + 4 + slen > len(data):
                i += 1
                continue
            val = data[j + 4 : j + 4 + slen].decode("ascii", "replace")
            out.append((i, key, val))
            i = j + 4 + slen
        elif typ == 0:
            val = struct.unpack_from("<i", data, j)[0]
            out.append((i, key, val))
            i = j + 4
        else:
            i += 1
    return out


def all_pos(data: bytes, needle: bytes) -> list[int]:
    out: list[int] = []
    s = 0
    while True:
        i = data.find(needle, s)
        if i < 0:
            break
        out.append(i)
        s = i + 1
    return out


def pack_from(data: bytes, kpos: int) -> dict:
    start = kpos - 200
    divpos = data.find(b"1_Small_DivDraw", kpos - 250, kpos + 1)
    if divpos >= 0:
        start = divpos - 8
    pms: dict = {}
    for _, key, val in parse_entries(data, start, kpos + 700):
        if key == "Name" or key.startswith(("1_Small", "2_Middle", "3_Up", "Div_")):
            pms[key] = val
        if key == "Name":
            break
    return pms


def nearest_chart_id(chart_ids: list[tuple[int, str]], kpos: int) -> str | None:
    after = [cid for pos, cid in chart_ids if pos >= kpos]
    return after[0] if after else None


def main() -> None:
    data = WND.read_bytes()
    smalls = all_pos(data, b"1_Small_TF")
    chart_ids = [
        (pos, val)
        for pos, key, val in parse_entries(data, 0, len(data))
        if key == "ChartId" and isinstance(val, str)
    ]

    by_tf: dict[str, dict] = {}
    charts_by_tf: dict[str, list[str]] = defaultdict(list)

    for kpos in smalls:
        pms = pack_from(data, kpos)
        small_tf = str(pms.get("1_Small_TF", ""))
        chart_tf = CHART_TF_BY_SMALL.get(small_tf)
        if not chart_tf or "1_Small_Period" not in pms:
            print("skip", kpos, small_tf, sorted(pms))
            continue
        if pms.get("Name") != "*RPM_TF_Up_5":
            print("WARN name", pms.get("Name"), "at", kpos)
        if chart_tf not in by_tf:
            by_tf[chart_tf] = pms
        elif tuple(sorted(pms.items())) != tuple(sorted(by_tf[chart_tf].items())):
            print("WARN distinct config for", chart_tf, "at", kpos)
        cid = nearest_chart_id(chart_ids, kpos)
        if chart_tf == "M30" and cid and cid not in charts_by_tf[chart_tf]:
            charts_by_tf[chart_tf].append(cid)
        print(
            chart_tf,
            cid,
            pms.get("Name"),
            {k: pms[k] for k in ("1_Small_TF", "2_Middle_TF", "3_Up_TF") if k in pms},
        )

    missing = [tf for tf in TF_ORDER if tf not in by_tf]
    if missing:
        raise SystemExit(f"missing TFs: {missing}")

    lines = [
        "; *RPM_TF_Up_5 live settings from finam.wnd",
        "; one section per chart timeframe (M1 / M10 / M30 / H4)",
        "",
    ]
    for tf in TF_ORDER:
        pms = by_tf[tf]
        lines.append(f"[RPM_TF_Up_5.{tf}]")
        lines.append("source=finam.wnd")
        lines.append(f"chart_tf={tf}")
        cids = charts_by_tf.get(tf, [])
        if cids:
            lines.append("chart_ids=" + ",".join(cids))
        lines.append("")
        for key in KEYS_ORDER:
            if key in pms:
                lines.append(f"{key}={pms[key]}")
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT)
    print("sections", list(by_tf))


if __name__ == "__main__":
    main()
