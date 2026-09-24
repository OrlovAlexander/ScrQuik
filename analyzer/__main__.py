# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from datetime import datetime

from analyzer.snapshot import analyze_instrument
from analyzer.combo import format_combo, format_m30_look, study_combo, study_m30_look
from analyzer.marks import export_all_marks, export_marks, format_marks, watch_marks


def _class_code(sec: str | None, class_code: str | None, all_classes: bool) -> str | None:
    if class_code:
        return class_code
    if all_classes and not sec:
        return None
    if sec and sec.upper().replace("-", "").startswith("CNY"):
        return "SPBFUT"
    return "TQBR"


def _default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat(sep=" ")
    raise TypeError(type(obj))


def main() -> None:
    p = argparse.ArgumentParser(description="Analyze one instrument across M1/M10/M30/H4")
    p.add_argument("--sec", default=None, help="Ticker; omit with --marks/--watch to process every barsSaver instrument")
    p.add_argument("--class-code", default=None, help="Class; default TQBR, SPBFUT for CNY*; omit with --watch to include every class")
    p.add_argument("--json", action="store_true")
    p.add_argument("--combo", action="store_true", help="H4->M1 unique states and M1 moves >= 1 percent, aggregated start/end table")
    p.add_argument("--m30", action="store_true", help="M30 moves >= 3 percent with M1 and M10 what's now at start/end")
    p.add_argument("--marks", action="store_true", help="Write setup CSV for the AnalyzerMarks QUIK overlay")
    p.add_argument("--watch", action="store_true", help="Keep re-exporting marks when barsSaver CSV grows")
    p.add_argument("--poll", type=float, default=11.0, help="Idle seconds between barsSaver checks in --watch")
    args = p.parse_args()
    cls = _class_code(args.sec, args.class_code, args.watch or args.marks)
    if args.watch or args.marks:
        if args.watch:
            if args.json:
                p.error("--json cannot be used with --watch")
            try:
                watch_marks(args.sec, cls, poll=args.poll)
            except KeyboardInterrupt:
                print("watch stopped", flush=True)
            return
        if args.sec:
            report = export_marks(args.sec, cls or "TQBR")
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2, default=_default))
                return
            print(format_marks(report))
            return
        reports = export_all_marks(cls)
        if args.json:
            print(json.dumps(reports, ensure_ascii=False, indent=2, default=_default))
            return
        return
    if not args.sec:
        p.error("--sec is required unless --marks or --watch")
    if args.m30:
        report = study_m30_look(args.sec, cls or "TQBR")
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=_default))
            return
        print(format_m30_look(report))
        return
    if args.combo:
        report = study_combo(args.sec, cls or "TQBR")
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=_default))
            return
        print(format_combo(report))
        return
    snap = analyze_instrument(args.sec, cls or "TQBR")
    if args.json:
        print(json.dumps(snap, ensure_ascii=False, indent=2, default=_default))
        return
    print(f"{snap['sec']} {snap['class_code']}  clock={snap['clock']}")
    for tf, pack in snap["tfs"].items():
        print(f"\n=== {tf}  bars={pack.get('bars')}  last={pack.get('last_bar')}  C={pack.get('close')}")
        print(f"  price    {pack.get('price_move')}")
        st = pack.get("states") or {}
        cur_st = st.get("current") or {}
        print(f"  current  rpm={ (pack.get('current') or {}).get('rpm') }  ema={(pack.get('current') or {}).get('ema')}  {cur_st.get('combo')}")
        up = pack.get("up") or {}
        for name, layer in (up.get("layers") or {}).items():
            tag = st.get(f"up_{name}") or {}
            if not layer.get("enabled"):
                print(f"  up.{name}({layer.get('tf')}) off")
                continue
            if layer.get("draw"):
                print(
                    f"  up.{name}({layer.get('tf')}) rpm={layer.get('rpm')} ema={layer.get('ema')} "
                    f"ema_vs0={tag.get('ema_vs0')} ema_slope={tag.get('ema_slope')} "
                    f"n={layer.get('agg_n')}  {tag.get('combo')}"
                )
            if layer.get("hist_draw"):
                htag = st.get("up_hist") or {}
                src = st.get(f"up_{name}") or {}
                print(
                    f"  up.hist.{name}({layer.get('tf')}) hist={layer.get('hist')} "
                    f"hist_up={layer.get('hist_up')} hist_dw={layer.get('hist_dw')} "
                    f"n={layer.get('agg_n')}  {src.get('hist_combo') or htag.get('combo')}"
                )
        align = st.get("up_align") or []
        if align:
            print(f"  up.align {', '.join(align)}")
        for ntf, npack in (pack.get("neighbors") or {}).items():
            if npack.get("status") != "closed":
                print(f"  down.{ntf} {npack.get('status')}")
                continue
            ncur = (npack.get("current") or {}).get("combo")
            print(
                f"  down.{ntf} closed={npack.get('bar')}  "
                f"price={npack.get('price_move')}  current={ncur}"
            )
        for lname, divs in (up.get("divs") or {}).items():
            for d in divs:
                print(f"  div.{lname} {d['kind']} {d.get('dt1')} -> {d.get('dt2')}")
        if tf == "M30":
            pat = pack.get("one2one_121")
            if not pat:
                print("  121: none")
            else:
                print(
                    f"  121 {pat['direction']} AB={pat['ab']:.3f} CD={pat['cd']:.3f} "
                    f"D={pat['D']['dt']} @{pat['D']['price']} stop={pat['stop']} tp1={pat['tp1']}"
                )


if __name__ == "__main__":
    main()
