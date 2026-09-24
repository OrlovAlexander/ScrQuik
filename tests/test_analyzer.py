# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path

from analyzer.bars import Bar, BARS_DIR, csv_path, typical
from analyzer.price import MOVES, classify_moves
from analyzer.rpm_current import compute_current, fir_typical, half_history_start
from analyzer.settings import hist_layer_names, load_up_settings
from analyzer.snapshot import CHART_TFS, analyze_instrument, assert_layout
from analyzer.states import current_tags, hist_tags, layer_tags
from analyzer.neighbors import NEIGHBOR_PAIRS, last_closed_indices, neighbor_tfs


class FirGoldTests(unittest.TestCase):
    def test_constant_typical_is_zero(self):
        t0 = datetime(2026, 1, 1, 10, 0)
        bars = [
            Bar(t0 + timedelta(minutes=i), 10, 10, 10, 10) for i in range(20)
        ]
        rpm = fir_typical(bars, 19)
        self.assertAlmostEqual(rpm, 0.0, places=12)

    def test_single_last_bar(self):
        t0 = datetime(2026, 1, 1, 10, 0)
        bars = [Bar(t0 + timedelta(minutes=i), 0, 0, 0, 0) for i in range(12)]
        bars[-1] = Bar(bars[-1].dt, 12, 12, 12, 12)
        self.assertAlmostEqual(typical(bars[-1]), 12.0)
        self.assertAlmostEqual(fir_typical(bars, 11), 1.6)

    def test_current_skips_first_bar(self):
        t0 = datetime(2026, 1, 1, 10, 0)
        bars = [Bar(t0 + timedelta(minutes=i), 10, 10, 10, 10) for i in range(5)]
        rows = compute_current(bars)
        self.assertIsNone(rows[0]["rpm"])
        self.assertIsNone(rows[1]["rpm"])
        self.assertIsNotNone(rows[2]["rpm"])

    def test_current_half_history_start(self):
        self.assertEqual(half_history_start(1), 0)
        self.assertEqual(half_history_start(10), 5)
        t0 = datetime(2026, 1, 1, 10, 0)
        bars = [Bar(t0 + timedelta(minutes=i), 10, 10, 10, 10) for i in range(10)]
        rows = compute_current(bars)
        self.assertTrue(all(r["rpm"] is None for r in rows[:5]))
        self.assertTrue(all(r["rpm"] is not None for r in rows[5:]))


class IniLayoutTests(unittest.TestCase):
    def test_up_sections_match_chart_tf(self):
        expect = {
            "M1": ("Mn5", "Mn10", "Mn20"),
            "M10": ("Mn20", "Mn30", "H2"),
            "M30": ("H1", "H2", "H4"),
            "H4": ("H12", "D1", "W1"),
        }
        for tf, layers in expect.items():
            st = load_up_settings(tf)
            self.assertEqual(st.small.tf, layers[0])
            self.assertEqual(st.middle.tf, layers[1])
            self.assertEqual(st.up.tf, layers[2])
        self.assertEqual(hist_layer_names(load_up_settings("M1")), ("up",))
        self.assertEqual(hist_layer_names(load_up_settings("M10")), ("small",))
        self.assertEqual(hist_layer_names(load_up_settings("M30")), ("up",))
        self.assertEqual(hist_layer_names(load_up_settings("H4")), ("up",))


@unittest.skipUnless(
    csv_path("GAZP", "TQBR", "M1").is_file(),
    "barsSaver GAZP CSV not present",
)
class GazpLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = analyze_instrument("GAZP", "TQBR", BARS_DIR)

    def test_layout(self):
        assert_layout(self.snap)

    def test_all_tfs_have_current_and_up(self):
        for tf in CHART_TFS:
            pack = self.snap["tfs"][tf]
            self.assertGreater(pack["bars"], 12)
            self.assertIsNotNone(pack["current"]["rpm"])
            layers = pack["up"]["layers"]
            self.assertEqual(set(layers), {"small", "middle", "up"})

    def test_121_only_on_m30(self):
        self.assertIn("one2one_121", self.snap["tfs"]["M30"])
        for tf in ("M1", "M10", "H4"):
            self.assertNotIn("one2one_121", self.snap["tfs"][tf])

    def test_price_move_and_states(self):
        for tf in CHART_TFS:
            pack = self.snap["tfs"][tf]
            self.assertIn(pack["price_move"], MOVES + ("unknown",))
            st = pack["states"]
            self.assertIsNotNone(st["current"]["combo"])
            self.assertIn("vs0", st["up_small"])
            self.assertIn("ema_vs0", st["up_small"])
            self.assertIn("ema_slope", st["up_small"])
            hist = st["up_hist"]
            self.assertIsNotNone(hist)
            self.assertIn("hist_sign", hist)
            self.assertNotIn("ema_vs0", hist)
            self.assertNotIn("vs0", hist)
            self.assertIsInstance(st["up_align"], list)
            align = " ".join(st["up_align"])
            self.assertNotIn("all_rpm_", align)

    def test_hist_comes_from_live_draw_slot(self):
        expect = {
            "M1": ("up", "Mn20"),
            "M10": ("small", "Mn20"),
            "M30": ("up", "H4"),
            "H4": ("up", "W1"),
        }
        for tf, (layer, hist_tf) in expect.items():
            hist = self.snap["tfs"][tf]["states"]["up_hist"]
            self.assertEqual(hist["layer"], layer, tf)
            self.assertEqual(hist["tf"], hist_tf, tf)
            self.assertIsNotNone(hist["combo"], tf)
            small = self.snap["tfs"][tf]["states"]["up_small"]
            if layer == "small":
                self.assertEqual(small.get("hist_sign"), hist["hist_sign"], tf)
                self.assertEqual(small.get("hist_dir"), hist["hist_dir"], tf)
                self.assertEqual(small.get("hist_combo"), hist["combo"], tf)
            else:
                self.assertNotIn("hist_sign", small, tf)

    def test_only_downward_neighbors(self):
        expect = {
            "H4": ("M30",),
            "M30": ("M10",),
            "M10": ("M1",),
            "M1": (),
        }
        for tf, names in expect.items():
            neigh = self.snap["tfs"][tf]["neighbors"]
            self.assertEqual(tuple(neigh), names)
        self.assertNotIn("H4", self.snap["tfs"]["M30"]["neighbors"])
        self.assertNotIn("M30", self.snap["tfs"]["M10"]["neighbors"])
        self.assertNotIn("M10", self.snap["tfs"]["M1"]["neighbors"])
        self.assertNotIn("M1", self.snap["tfs"]["H4"]["neighbors"])
        for tf, names in expect.items():
            for other in names:
                pack = self.snap["tfs"][tf]["neighbors"][other]
                self.assertEqual(pack.get("status"), "closed")
                self.assertIn(pack.get("price_move"), MOVES + ("unknown",))


class PriceMoveTests(unittest.TestCase):
    def _bars(self, closes: list[float]) -> list[Bar]:
        t0 = datetime(2026, 1, 1, 10, 0)
        out = []
        for i, c in enumerate(closes):
            out.append(Bar(t0 + timedelta(minutes=i), c, c + 0.2, c - 0.2, c))
        return out

    def test_flat_range(self):
        bars = self._bars([10.0] * 30)
        moves = classify_moves(bars, "M10")
        self.assertEqual(set(moves[12:]), {"flat"})

    def test_up_and_start_up(self):
        closes = [10.0] * 16 + [10.0 + 0.4 * i for i in range(1, 16)]
        moves = classify_moves(self._bars(closes), "M10")
        self.assertIn("start_up", moves)
        self.assertIn("up", moves)

    def test_down_and_start_down(self):
        closes = [12.0] * 16 + [12.0 - 0.4 * i for i in range(1, 16)]
        moves = classify_moves(self._bars(closes), "M10")
        self.assertIn("start_down", moves)
        self.assertIn("down", moves)


class StateTests(unittest.TestCase):
    def test_current_falling_above_ema(self):
        rows = [
            {"rpm": 2.0, "ema": 1.0},
            {"rpm": 1.6, "ema": 1.05},
        ]
        tags = current_tags(rows)
        self.assertEqual(tags[1]["vs0"], "above_0")
        self.assertEqual(tags[1]["vs_ema"], "above_ema")
        self.assertEqual(tags[1]["slope"], "falling_above_ema")
        self.assertEqual(tags[1]["ema_vs0"], "above_0")
        self.assertEqual(tags[1]["ema_slope"], "flat")

    def test_up_layer_uses_hist_not_rpm_sign(self):
        series = [
            {
                "small": {"rpm": 1.0, "ema": 0.4},
                "up": {"hist": 0.5, "hist_up": 0.5, "hist_dw": None, "ema": 0.3},
            },
            {
                "small": {"rpm": 1.2, "ema": 0.55},
                "up": {"hist": 0.8, "hist_up": 0.8, "hist_dw": None, "ema": 0.5},
            },
        ]
        line = layer_tags(series, "small")
        hist = hist_tags(series, "up")
        self.assertEqual(line[1]["ema_vs0"], "above_0")
        self.assertEqual(line[1]["ema_slope"], "rising")
        self.assertIn("ema_above_0", line[1]["combo"])
        self.assertIn("ema_rising", line[1]["combo"])
        self.assertEqual(hist[1]["hist_sign"], "above_0")
        self.assertEqual(hist[1]["hist_dir"], "hist_growing")
        self.assertEqual(hist[1]["combo"], "above_0|hist_growing")
        self.assertNotIn("ema_vs0", hist[1])
        self.assertNotIn("vs0", hist[1])
        self.assertNotIn("vs_ema", hist[1])

    def test_hist_grows_down_when_more_negative(self):
        series = [
            {"up": {"hist": -0.4, "hist_up": None, "hist_dw": -0.4}},
            {"up": {"hist": -0.9, "hist_up": None, "hist_dw": -0.9}},
            {"up": {"hist": -0.5, "hist_up": -0.5, "hist_dw": None}},
        ]
        hist = hist_tags(series, "up")
        self.assertEqual(hist[1]["hist_dir"], "hist_growing")
        self.assertEqual(hist[1]["combo"], "below_0|hist_growing")
        self.assertEqual(hist[2]["hist_dir"], "hist_shrinking")

    def test_ema_falling_below_zero(self):
        series = [
            {"small": {"rpm": -1.0, "ema": -0.4}},
            {"small": {"rpm": -1.2, "ema": -0.7}},
        ]
        line = layer_tags(series, "small")
        self.assertEqual(line[1]["ema_vs0"], "below_0")
        self.assertEqual(line[1]["ema_slope"], "falling")

    def test_ema_trend_over_five_bars(self):
        series = [{"small": {"rpm": 0.2, "ema": 0.10 + i * 0.003}} for i in range(8)]
        line = layer_tags(series, "small")
        self.assertEqual(line[1]["ema_slope"], "flat")
        self.assertEqual(line[7]["ema_trend"], "rising")

    def test_current_ema_trend_over_five_bars(self):
        rows = [{"rpm": 2.0 - i * 0.2, "ema": 1.50 - i * 0.12} for i in range(8)]
        tags = current_tags(rows)
        self.assertEqual(tags[1]["ema_slope"], "falling")
        self.assertEqual(tags[7]["ema_trend"], "falling")


class NeighborAlignTests(unittest.TestCase):
    def test_pairs_look_downward_only(self):
        self.assertEqual(NEIGHBOR_PAIRS, (("H4", "M30"), ("M30", "M10"), ("M10", "M1")))
        self.assertEqual(neighbor_tfs("H4"), ("M30",))
        self.assertEqual(neighbor_tfs("M30"), ("M10",))
        self.assertEqual(neighbor_tfs("M10"), ("M1",))
        self.assertEqual(neighbor_tfs("M1"), ())
        self.assertNotIn("H4", neighbor_tfs("M30"))
        self.assertNotIn("M1", neighbor_tfs("H4"))

    def test_last_closed_skips_forming_bar(self):
        t0 = datetime(2026, 1, 1, 10, 0)
        hi = [t0 + timedelta(minutes=10 * i) for i in range(4)]
        lo = [t0 + timedelta(minutes=m) for m in (5, 10, 15, 20, 25)]
        idx = last_closed_indices(lo, hi)
        self.assertEqual(idx, [None, 0, 0, 1, 1])

    def test_period_closes_bar_across_session_gap(self):
        t0 = datetime(2026, 1, 9, 23, 50)
        src = [t0, datetime(2026, 1, 12, 10, 0)]
        event = [datetime(2026, 1, 12, 8, 0)]
        self.assertEqual(last_closed_indices(event, src), [None])
        self.assertEqual(last_closed_indices(event, src, period_minutes=10), [0])

    def test_gazp_closed_neighbor_has_no_lookahead(self):
        if not csv_path("GAZP", "TQBR", "M1").is_file():
            self.skipTest("barsSaver GAZP CSV not present")
        from analyzer.bars import load_instrument

        books = load_instrument("GAZP")
        lo = [b.dt for b in books["M1"]]
        hi = [b.dt for b in books["M10"]]
        mapped = last_closed_indices(lo, hi)
        for i, j in enumerate(mapped):
            if j is None:
                continue
            self.assertLess(j + 1, len(hi))
            self.assertLessEqual(hi[j + 1], lo[i])


class ComboTests(unittest.TestCase):
    def test_buy_and_sell_setups(self):
        from analyzer.combo import setup_signal

        buy = {
            "small": {
                "vs0": "below_0",
                "vs_ema": "below_ema",
                "ema_vs0": "below_0",
                "ema_trend": "falling",
            },
            "middle": {
                "vs0": "below_0",
                "vs_ema": "below_ema",
                "ema_vs0": "below_0",
                "ema_trend": "falling",
            },
            "hist": {"hist_sign": "below_0", "hist_dir": "hist_growing"},
            "current": {"vs0": "below_0", "vs_ema": "below_ema", "ema_vs0": "below_0"},
        }
        sell = {
            "small": {
                "vs0": "above_0",
                "vs_ema": "above_ema",
                "ema_vs0": "above_0",
                "ema_trend": "rising",
            },
            "middle": {
                "vs0": "above_0",
                "vs_ema": "above_ema",
                "ema_vs0": "above_0",
                "ema_trend": "rising",
            },
            "hist": {"hist_sign": "above_0", "hist_dir": "hist_growing"},
            "current": {"vs0": "above_0", "vs_ema": "above_ema", "ema_vs0": "above_0"},
        }
        self.assertEqual(setup_signal(buy["small"], buy["middle"], buy["hist"], buy["current"]), "buy")
        self.assertEqual(setup_signal(sell["small"], sell["middle"], sell["hist"], sell["current"]), "sell")
        self.assertEqual(setup_signal(buy["small"], buy["middle"], buy["hist"]), "none")
        self.assertEqual(setup_signal(sell["small"], sell["middle"], sell["hist"]), "none")
        shrinking = {"hist_sign": "below_0", "hist_dir": "hist_shrinking"}
        self.assertEqual(setup_signal(buy["small"], buy["middle"], shrinking, buy["current"]), "none")
        self.assertEqual(
            setup_signal(
                dict(buy["small"], slope="rising_below_ema"),
                dict(buy["middle"], slope="rising_below_ema"),
                buy["hist"],
                buy["current"],
            ),
            "buy",
        )
        self.assertEqual(
            setup_signal(
                buy["small"],
                buy["middle"],
                buy["hist"],
                dict(buy["current"], vs_ema="above_ema"),
            ),
            "none",
        )
        ema_flat = dict(sell["small"], ema_trend="flat")
        self.assertEqual(setup_signal(ema_flat, sell["middle"], sell["hist"], sell["current"]), "none")

    def test_m10_cross_buy_and_mirror_sell(self):
        from analyzer.combo import setup_signal

        buy = {
            "current": {"vs0": "below_0", "vs_ema": "below_ema", "slope": "rising_below_ema"},
            "small": {
                "vs0": "above_0",
                "vs_ema": "below_ema",
                "slope": "falling_below_ema",
                "ema_vs0": "above_0",
                "ema_slope": "falling",
            },
            "middle": {
                "vs0": "above_0",
                "vs_ema": "above_ema",
                "slope": "falling_above_ema",
                "ema_vs0": "above_0",
                "ema_slope": "falling",
            },
            "hist": {"hist_sign": "above_0", "hist_dir": "hist_shrinking"},
        }
        sell = {
            "current": {"vs0": "above_0", "vs_ema": "above_ema", "slope": "falling_above_ema"},
            "small": {
                "vs0": "below_0",
                "vs_ema": "above_ema",
                "slope": "rising_above_ema",
                "ema_vs0": "below_0",
                "ema_slope": "rising",
            },
            "middle": {
                "vs0": "below_0",
                "vs_ema": "below_ema",
                "slope": "rising_below_ema",
                "ema_vs0": "below_0",
                "ema_slope": "rising",
            },
            "hist": {"hist_sign": "below_0", "hist_dir": "hist_shrinking"},
        }
        self.assertEqual(
            setup_signal(buy["small"], buy["middle"], buy["hist"], buy["current"]),
            "buy1",
        )
        self.assertEqual(
            setup_signal(sell["small"], sell["middle"], sell["hist"], sell["current"]),
            "sell1",
        )
        self.assertEqual(
            setup_signal(buy["small"], buy["middle"], buy["hist"]),
            "none",
        )
        self.assertEqual(
            setup_signal(
                buy["small"],
                dict(buy["middle"], slope="flat_above_ema", ema_slope="flat"),
                buy["hist"],
                buy["current"],
            ),
            "buy1",
        )
        self.assertEqual(
            setup_signal(
                sell["small"],
                dict(sell["middle"], slope="flat_below_ema", ema_slope="flat"),
                sell["hist"],
                sell["current"],
            ),
            "sell1",
        )
        self.assertEqual(
            setup_signal(
                buy["small"],
                dict(buy["middle"], slope="rising_above_ema", ema_slope="rising"),
                buy["hist"],
                buy["current"],
            ),
            "none",
        )

    def test_buy2_and_sell2_setups(self):
        from analyzer.combo import setup_signal

        buy = {
            "current": {
                "vs0": "below_0",
                "vs_ema": "below_ema",
                "ema_vs0": "above_0",
                "ema_trend": "falling",
            },
            "small": {
                "vs0": "above_0",
                "vs_ema": "above_ema",
                "ema_vs0": "above_0",
                "ema_trend": "rising",
                "slope": "rising_above_ema",
            },
            "middle": {
                "vs0": "above_0",
                "vs_ema": "below_ema",
                "ema_vs0": "above_0",
                "ema_trend": "falling",
            },
            "hist": {"hist_sign": "above_0", "hist_dir": "hist_shrinking"},
        }
        sell = {
            "current": {
                "vs0": "above_0",
                "vs_ema": "above_ema",
                "ema_vs0": "below_0",
                "ema_trend": "rising",
            },
            "small": {
                "vs0": "below_0",
                "vs_ema": "below_ema",
                "ema_vs0": "below_0",
                "ema_trend": "falling",
                "slope": "falling_below_ema",
            },
            "middle": {
                "vs0": "below_0",
                "vs_ema": "above_ema",
                "ema_vs0": "below_0",
                "ema_trend": "rising",
            },
            "hist": {"hist_sign": "below_0", "hist_dir": "hist_shrinking"},
        }
        self.assertEqual(setup_signal(buy["small"], buy["middle"], buy["hist"], buy["current"]), "buy2")
        self.assertEqual(setup_signal(sell["small"], sell["middle"], sell["hist"], sell["current"]), "sell2")
        self.assertEqual(setup_signal(buy["small"], buy["middle"], buy["hist"]), "none")
        self.assertEqual(
            setup_signal(
                dict(buy["small"], slope="flat_above_ema"),
                buy["middle"],
                buy["hist"],
                buy["current"],
            ),
            "none",
        )
        self.assertEqual(
            setup_signal(
                buy["small"],
                buy["middle"],
                buy["hist"],
                dict(buy["current"], ema_trend="flat"),
            ),
            "none",
        )
        self.assertEqual(
            setup_signal(
                buy["small"],
                dict(buy["middle"], vs_ema="near_ema"),
                buy["hist"],
                buy["current"],
            ),
            "none",
        )

    def test_parse_and_compact_key(self):
        from analyzer.combo import compact_state, parse_key

        key = (
            "sell|p=up|c=above_0|above_ema|rising_above_ema|"
            "s=above_0|above_ema|rising_above_ema|ema_above_0|ema_rising|"
            "m=above_0|above_ema|flat_above_ema|ema_above_0|ema_rising|"
            "h=above_0|hist_growing"
        )
        fields = parse_key(key)
        self.assertEqual(fields["setup"], "sell")
        self.assertEqual(fields["price"], "up")
        self.assertIn("above_0", fields["hist"])
        compact = compact_state(key)
        self.assertIn("sell", compact)
        self.assertIn("h=above_0/growing", compact)

    def test_zigzag_one_percent_up(self):
        from analyzer.combo import zigzag_moves

        t0 = datetime(2026, 1, 1, 10, 0)
        closes = [100.0] * 5 + [100.0 + i for i in range(1, 6)] + [105.0 - i for i in range(1, 6)]
        bars = [
            Bar(t0 + timedelta(minutes=i), c, c + 0.1, c - 0.1, c) for i, c in enumerate(closes)
        ]
        moves = zigzag_moves(bars, min_pct=1.0)
        self.assertTrue(any(m["side"] == "up" and m["pct"] >= 1.0 for m in moves))

    def test_find_setup_left_onset_and_drawdown(self):
        from analyzer.combo import find_setup_left, setup_drawdown

        setups = ["none"] * 10 + ["buy"] * 4 + ["none"] * 6
        found = find_setup_left(setups, end_i=19, max_bars=20, warm=0)
        self.assertIsNotNone(found)
        self.assertEqual(found["setup"], "buy")
        self.assertEqual(found["onset_i"], 10)
        self.assertEqual(found["hit_i"], 13)
        self.assertEqual(found["bars_ago"], 9)
        missing = find_setup_left(setups, end_i=19, max_bars=3, warm=0)
        self.assertIsNone(missing)

        t0 = datetime(2026, 1, 1, 10, 0)
        closes = [100.0, 99.0, 97.0, 102.0]
        lows = [99.5, 98.0, 95.0, 101.0]
        highs = [100.5, 99.5, 98.0, 103.0]
        bars = [
            Bar(t0 + timedelta(minutes=i), c, h, lo, c)
            for i, (c, h, lo) in enumerate(zip(closes, highs, lows))
        ]
        dd = setup_drawdown(bars, 0, 3, "buy")
        self.assertEqual(dd, 5.0)
        sell_dd = setup_drawdown(bars, 2, 3, "sell")
        self.assertEqual(sell_dd, round((103.0 - 97.0) / 97.0 * 100.0, 3))

    def test_m30_look_aggregates_m10_m1(self):
        from analyzer.combo import LOOK_TFS_M30, aggregate_start_end, format_m30_look

        fields = {
            "setup": "buy",
            "price": "down",
            "cur": "below_0|below_ema",
            "small": "below_0|below_ema",
            "middle": "below_0|below_ema",
            "hist": "below_0|hist_growing",
        }
        end_fields = dict(fields)
        end_fields["setup"] = "sell"
        end_fields["price"] = "up"
        moves = [
            {
                "side": "up",
                "pct": 3.4,
                "start": {
                    "M10": {"compact": "buy p=down", "fields": fields},
                    "M1": {"compact": "none p=down", "fields": fields},
                },
                "end": {
                    "M10": {"compact": "sell p=up", "fields": end_fields},
                    "M1": {"compact": "sell p=up", "fields": end_fields},
                },
            }
        ]
        agg = aggregate_start_end(moves, tfs=LOOK_TFS_M30)
        self.assertEqual(agg["tfs"], ["M10", "M1"])
        self.assertEqual(agg["by_tf"]["M10"][0]["start"], "buy p=down")
        self.assertEqual(agg["by_tf"]["M10"][0]["end"], "sell p=up")
        text = format_m30_look(
            {
                "sec": "GAZP",
                "class_code": "TQBR",
                "clock": "2026-09-18 23:48",
                "min_move_pct": 3.0,
                "move_count": 1,
                "moves": [
                    {
                        "side": "up",
                        "pct": 3.4,
                        "start_dt": "2026-01-01 10:00",
                        "end_dt": "2026-01-01 12:00",
                        "start_px": 100,
                        "end_px": 103.4,
                        "start_M10": "buy p=down",
                        "end_M10": "sell p=up",
                        "start_M1": "none p=down",
                        "end_M1": "sell p=up",
                        "start_M10_fields": fields,
                        "end_M10_fields": end_fields,
                        "start_M1_fields": fields,
                        "end_M1_fields": end_fields,
                        "start_M10_bar": "2026-01-01 09:50",
                        "end_M10_bar": "2026-01-01 11:50",
                        "start_M1_bar": "2026-01-01 09:59",
                        "end_M1_bar": "2026-01-01 11:59",
                    }
                ],
                "unique": {
                    "M10": {"start": [{"state": "buy p=down", "n": 1, "up": 1, "down": 0, "mean_pct": 3.4}], "end": []},
                    "M1": {"start": [], "end": []},
                },
                "agg": {"by_tf": agg["by_tf"], "by_field": agg["by_field"], "ladder": []},
            }
        )
        self.assertIn("M30 move>=3.0%", text)
        self.assertIn("setup=buy", text)
        self.assertIn("M10 start", text)
        self.assertIn("start_bar=2026-01-01 10:00", text)

    def test_mark_rows_onset_and_csv(self):
        from analyzer.marks import MARKS_TFS, mark_rows, write_marks_csv, format_mark_dt

        t0 = datetime(2026, 8, 25, 17, 20, 0)
        series = [
            {"dt": t0 + timedelta(minutes=10 * i), "setup": setup}
            for i, setup in enumerate(["none", "buy", "buy", "sell", "none", "buy1"])
        ]
        rows = mark_rows(series)
        self.assertEqual([r["onset"] for r in rows], [0, 1, 0, 1, 0, 1])
        self.assertEqual(rows[1]["code"], 1)
        self.assertEqual(rows[3]["code"], 2)
        self.assertEqual(rows[5]["code"], 3)
        self.assertEqual(MARKS_TFS, ("M1", "M10"))
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "GAZP_TQBR_M10.csv"
            write_marks_csv(path, rows)
            text = path.read_text(encoding="utf-8")
        self.assertIn("datetime;setup;onset;code", text)
        self.assertIn(format_mark_dt(t0 + timedelta(minutes=10)) + ";buy;1;1", text)
        self.assertIn(";buy;0;1", text)
        self.assertIn(";buy1;1;3", text)

    def test_watch_exports_when_bars_grow(self):
        import tempfile

        from analyzer.combo import CHART_TFS
        from analyzer.marks import bars_fingerprint, watch_marks

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            dest = data_dir / "marks"
            for tf in CHART_TFS:
                (data_dir / f"GAZP_TQBR_{tf}_.csv").write_text("hdr\n", encoding="utf-8")
            first = bars_fingerprint("GAZP", data_dir=data_dir)
            (data_dir / "GAZP_TQBR_M1_.csv").write_text("hdr\nrow\n", encoding="utf-8")
            second = bars_fingerprint("GAZP", data_dir=data_dir)
            self.assertNotEqual(first, second)

            calls: list[int] = []
            sleeps = {"n": 0}

            def exporter(*_a, **_k):
                calls.append(1)
                return {
                    "sec": "GAZP",
                    "class_code": "TQBR",
                    "dir": str(dest),
                    "files": {},
                    "counts": {},
                }

            def sleeper(_wait):
                sleeps["n"] += 1
                if sleeps["n"] == 1:
                    (data_dir / "GAZP_TQBR_M10_.csv").write_text("hdr\nnew\n", encoding="utf-8")

            def stop():
                return sleeps["n"] >= 3

            n = watch_marks(
                "GAZP",
                data_dir=data_dir,
                dest_dir=dest,
                poll=1.0,
                exporter=exporter,
                sleeper=sleeper,
                stop=stop,
                log=lambda _msg: None,
            )
            self.assertEqual(n, 3)
            self.assertEqual(len(calls), 3)

    def test_list_instruments_and_watch_all(self):
        import tempfile

        from analyzer.bars import list_instruments, parse_bars_filename
        from analyzer.combo import CHART_TFS
        from analyzer.marks import watch_marks

        self.assertEqual(parse_bars_filename("GAZP_TQBR_M10_.csv"), ("GAZP", "TQBR", "M10"))
        self.assertEqual(parse_bars_filename("X5_TQBR_M1_.csv"), ("X5", "TQBR", "M1"))
        self.assertEqual(parse_bars_filename("CNY12.26_SPBFUT_M1_.csv"), ("CNY12.26", "SPBFUT", "M1"))
        self.assertIsNone(parse_bars_filename("readme.csv"))
        from analyzer.bars import csv_path as bars_csv
        cr = bars_csv("CR", "SPBFUT", "M1")
        if cr.is_file():
            self.assertEqual(bars_csv("CNY12.26", "SPBFUT", "M1"), cr)
        from analyzer.marks import mark_sec_names
        if cr.is_file():
            names = mark_sec_names("CR", "SPBFUT")
            self.assertIn("CR", names)
            self.assertIn("CRZ6", names)

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            dest = data_dir / "marks"
            for sec in ("GAZP", "SBER"):
                for tf in CHART_TFS:
                    (data_dir / f"{sec}_TQBR_{tf}_.csv").write_text("hdr\n", encoding="utf-8")
            (data_dir / "SBER_TQBR_M1_.csv").write_text("hdr\n1\n", encoding="utf-8")
            names = list_instruments(data_dir)
            self.assertEqual(names, [("GAZP", "TQBR"), ("SBER", "TQBR")])

            calls: list[tuple[str, tuple | None]] = []
            sleeps = {"n": 0}

            def exporter(sec, class_code, **kw):
                calls.append((sec, kw.get("tfs")))
                return {
                    "sec": sec,
                    "class_code": class_code,
                    "dir": str(dest),
                    "files": {},
                    "counts": {},
                }

            def sleeper(_wait):
                sleeps["n"] += 1
                if sleeps["n"] == 1:
                    (data_dir / "SBER_TQBR_M10_.csv").write_text("hdr\nnew\n", encoding="utf-8")

            def stop():
                return sleeps["n"] >= 3

            n = watch_marks(
                None,
                data_dir=data_dir,
                dest_dir=dest,
                poll=1.0,
                exporter=exporter,
                sleeper=sleeper,
                stop=stop,
                log=lambda _msg: None,
            )
            self.assertEqual(
                calls,
                [
                    ("GAZP", ("M1",)),
                    ("SBER", ("M1",)),
                    ("GAZP", ("M10",)),
                    ("SBER", ("M10",)),
                    ("SBER", ("M10",)),
                ],
            )
            self.assertEqual(n, 5)

    def test_load_csv_tail(self):
        import tempfile

        from analyzer.bars import load_csv

        header = "sec_code;class_code;unix_time;date;time;date_time;index;Open;High;Low;Close\n"
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        rows = []
        for i in range(1200):
            t = t0 + timedelta(minutes=i)
            stamp = t.strftime("%d.%m.%Y %H:%M:%S")
            d, tm = stamp.split(" ")
            rows.append(
                f"GAZP;TQBR;0;{d};{tm};{stamp};{i};1;2;0;{i}.0\n"
            )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "GAZP_TQBR_M1_.csv"
            path.write_text(header + "".join(rows), encoding="utf-8")
            full = load_csv(path)
            tail = load_csv(path, max_bars=9)
        self.assertEqual(len(full), 1200)
        self.assertEqual(len(tail), 9)
        self.assertEqual(tail[-1].c, 1199.0)
        self.assertEqual(tail[0].c, 1191.0)
        self.assertEqual(tail[-1].dt, full[-1].dt)

    def test_watch_logs_every_poll(self):
        import tempfile

        from analyzer.combo import CHART_TFS
        from analyzer.marks import watch_marks

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            dest = data_dir / "marks"
            for tf in CHART_TFS:
                (data_dir / f"GAZP_TQBR_{tf}_.csv").write_text("hdr\n", encoding="utf-8")
            logs: list[str] = []
            sleeps = {"n": 0}

            def exporter(*_a, **_k):
                return {
                    "sec": "GAZP",
                    "class_code": "TQBR",
                    "dir": str(dest),
                    "files": {},
                    "counts": {},
                }

            def sleeper(_wait):
                sleeps["n"] += 1

            def stop():
                return sleeps["n"] >= 2

            watch_marks(
                "GAZP",
                data_dir=data_dir,
                dest_dir=dest,
                poll=1.0,
                exporter=exporter,
                sleeper=sleeper,
                stop=stop,
                log=logs.append,
            )
        polls = [line for line in logs if "poll#" in line]
        self.assertGreaterEqual(len(polls), 2)
        self.assertTrue(any("dirty=0" in line for line in polls))


if __name__ == "__main__":
    unittest.main()
