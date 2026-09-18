# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from datetime import datetime

from analyzer.snapshot import analyze_instrument


def _default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat(sep=" ")
    raise TypeError(type(obj))


def main() -> None:
    p = argparse.ArgumentParser(description="Analyze one instrument across M1/M10/M30/H4")
    p.add_argument("--sec", required=True)
    p.add_argument("--class-code", default="TQBR")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    snap = analyze_instrument(args.sec, args.class_code)
    if args.json:
        print(json.dumps(snap, ensure_ascii=False, indent=2, default=_default))
        return
    print(f"{snap['sec']} {snap['class_code']}  clock={snap['clock']}")
    for tf, pack in snap["tfs"].items():
        print(f"\n=== {tf}  bars={pack.get('bars')}  last={pack.get('last_bar')}  C={pack.get('close')}")
        cur = pack.get("current") or {}
        print(f"  current  rpm={cur.get('rpm')}  ema={cur.get('ema')}")
        up = pack.get("up") or {}
        for name, layer in (up.get("layers") or {}).items():
            if not layer.get("enabled"):
                print(f"  up.{name}({layer.get('tf')}) off")
                continue
            print(
                f"  up.{name}({layer.get('tf')}) rpm={layer.get('rpm')} ema={layer.get('ema')} "
                f"hist={layer.get('hist')} n={layer.get('agg_n')}"
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
