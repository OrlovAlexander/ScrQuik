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


class DayAggTests(unittest.TestCase):
    def _days(self, n: int, start: datetime | None = None) -> list[Bar]:
        t0 = start or datetime(2026, 1, 1, 10, 0)
        return [Bar(t0 + timedelta(days=i), 1, 2, 0, 1.0 + i) for i in range(n)]

    def test_d1_one_bar_per_calendar_day(self):
        from analyzer.rpm_up import AggSeries

        series = AggSeries("D1")
        for bar in self._days(5):
            series.set_price(bar)
        self.assertEqual(len(series.bars), 5)

    def test_dn_uses_n_day_slots(self):
        from analyzer.rpm_up import AggSeries, DAY_SLOT, _day_slot

        start = datetime(2026, 1, 1, 10, 0)
        bars = self._days(12, start)
        for tf, n in DAY_SLOT.items():
            series = AggSeries(tf)
            for bar in bars:
                series.set_price(bar)
            slots = {_day_slot(bar.dt, tf) for bar in bars}
            self.assertEqual(len(series.bars), len(slots), tf)

    def test_d2_merges_intraday_bars(self):
        from analyzer.rpm_up import AggSeries, _day_slot

        bars = []
        for d in range(4):
            for hour in (4, 8, 12, 16):
                bars.append(Bar(datetime(2026, 1, 1 + d, hour, 0), 1, 2, 0, 1.0))
        series = AggSeries("D2")
        for bar in bars:
            series.set_price(bar)
        slots = {_day_slot(bar.dt, "D2") for bar in bars}
        self.assertEqual(len(series.bars), len(slots))
        self.assertLess(len(series.bars), 4)


class WeekAggTests(unittest.TestCase):
    def test_w1_new_bar_on_monday(self):
        from analyzer.rpm_up import AggSeries

        # 2026-01-01 is Thursday; first Monday is 2026-01-05.
        bars = [
            Bar(datetime(2026, 1, 1, 10, 0), 1, 2, 0, 1.0),
            Bar(datetime(2026, 1, 2, 10, 0), 1, 2, 0, 1.1),
            Bar(datetime(2026, 1, 5, 10, 0), 1, 2, 0, 1.2),
            Bar(datetime(2026, 1, 6, 10, 0), 1, 2, 0, 1.3),
            Bar(datetime(2026, 1, 12, 10, 0), 1, 2, 0, 1.4),
        ]
        series = AggSeries("W1")
        for bar in bars:
            series.set_price(bar)
        self.assertEqual(len(series.bars), 3)

    def test_wn_uses_n_week_slots(self):
        from analyzer.rpm_up import AggSeries, WEEK_SLOT, _week_slot

        start = datetime(2026, 1, 5, 10, 0)
        bars = [Bar(start + timedelta(days=i), 1, 2, 0, 1.0) for i in range(28)]
        for tf in ("W2", "W3", "W4", "W5"):
            series = AggSeries(tf)
            for bar in bars:
                series.set_price(bar)
            slots = {_week_slot(bar.dt, tf) for bar in bars}
            self.assertEqual(len(series.bars), len(slots), tf)
            self.assertLess(len(series.bars), 28, tf)

    def test_d5_w5_slots_match_lua_unix_epoch(self):
        from analyzer.rpm_up import _day_slot, _week_slot

        # Lua D5: 10–14 Aug 2026 one slot, 17–19 next, 20–24 next.
        self.assertEqual(_day_slot(datetime(2026, 8, 10), "D5"), _day_slot(datetime(2026, 8, 14), "D5"))
        self.assertNotEqual(_day_slot(datetime(2026, 8, 14), "D5"), _day_slot(datetime(2026, 8, 17), "D5"))
        self.assertEqual(_day_slot(datetime(2026, 8, 17), "D5"), _day_slot(datetime(2026, 8, 19), "D5"))
        self.assertNotEqual(_day_slot(datetime(2026, 8, 19), "D5"), _day_slot(datetime(2026, 8, 20), "D5"))
        # Lua W5: 10–21 Aug 2026 one slot, 24 Aug next.
        self.assertEqual(_week_slot(datetime(2026, 8, 10), "W5"), _week_slot(datetime(2026, 8, 21), "W5"))
        self.assertNotEqual(_week_slot(datetime(2026, 8, 21), "W5"), _week_slot(datetime(2026, 8, 24), "W5"))


class IniLayoutTests(unittest.TestCase):
    def test_up_sections_match_chart_tf(self):
        expect = {
            "M1": ("Mn5", "Mn10", "Mn20"),
            "M10": ("Mn20", "Mn30", "H2"),
            "M30": ("H1", "H2", "H4"),
            "H4": ("H12", "D1", "W1"),
            "D1": ("D5", "W2", "W5"),
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
        self.assertEqual(hist_layer_names(load_up_settings("D1")), ("up",))


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
        self.assertEqual(MARKS_TFS, ("M1", "M10", "M30", "H4", "D1"))
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
            self.assertEqual(n, 5)
            self.assertEqual(len(calls), 5)

    def test_list_instruments_and_watch_all(self):
        import tempfile

        from analyzer.bars import list_instruments, parse_bars_filename
        from analyzer.combo import CHART_TFS
        from analyzer.marks import watch_marks

        self.assertEqual(parse_bars_filename("GAZP_TQBR_M10_.csv"), ("GAZP", "TQBR", "M10"))
        self.assertEqual(parse_bars_filename("X5_TQBR_M1_.csv"), ("X5", "TQBR", "M1"))
        self.assertEqual(parse_bars_filename("CNY12.26_SPBFUT_M1_.csv"), ("CNY12.26", "SPBFUT", "M1"))
        self.assertEqual(parse_bars_filename("CR_SPBFUT_D1_.csv"), ("CR", "SPBFUT", "D1"))
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
                    ("GAZP", ("M30",)),
                    ("SBER", ("M30",)),
                    ("GAZP", ("H4",)),
                    ("SBER", ("H4",)),
                    ("SBER", ("M10",)),
                ],
            )
            self.assertEqual(n, 9)

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


def _pt(kind: str, i: int, price: float, confirmed: bool = True) -> dict:
    return {
        "kind": kind,
        "i": i,
        "dt": datetime(2026, 1, 1, 10, 0) + timedelta(minutes=i),
        "price": price,
        "confirmed": confirmed,
    }


def _path_bars(knots: list[tuple[int, float]], wick: float = 0.05) -> list[Bar]:
    t0 = datetime(2026, 1, 1, 10, 0)
    last_i = knots[-1][0]
    path = [knots[0][1]] * (last_i + 1)
    for (i0, p0), (i1, p1) in zip(knots, knots[1:]):
        span = i1 - i0
        for j in range(i0, i1 + 1):
            t = 0.0 if span == 0 else (j - i0) / span
            path[j] = p0 + t * (p1 - p0)
    bars = []
    for i, px in enumerate(path):
        bars.append(
            Bar(t0 + timedelta(minutes=i), px, px + wick, px - wick, px)
        )
    return bars


class KrechetovWaveTests(unittest.TestCase):
    def test_swing_pivots_high_low_not_close(self):
        from analyzer.waves import swing_pivots

        knots = [(0, 100.0), (20, 108.0), (40, 96.0), (55, 101.0)]
        pivots = swing_pivots(_path_bars(knots), min_pct=1.0)
        kinds = [p["kind"] for p in pivots if p["confirmed"]]
        self.assertGreaterEqual(len(kinds), 2)
        self.assertEqual(kinds[0], "low")
        self.assertIn("high", kinds)

    def test_right_buy_passes_geometry(self):
        from analyzer.waves import _right_wave, find_waves

        pts = [
            _pt("low", 10, 100.0),
            _pt("high", 30, 107.0),
            _pt("low", 55, 96.0),
            _pt("high", 80, 105.0),
            _pt("low", 105, 99.0),
        ]
        raw, reason = _right_wave(pts, 1.0)
        self.assertIsNone(reason)
        self.assertEqual(raw["kind"], "right")
        self.assertEqual(raw["side"], "buy")

        bars = _path_bars(
            [(0, 100.0), (20, 107.0), (45, 96.0), (70, 105.0), (95, 99.0), (115, 102.0)]
        )
        pack = find_waves(bars, min_pct=1.0, window=40)
        sides = {(w["kind"], w["side"]) for w in pack["waves"]}
        self.assertIn(("right", "buy"), sides)

    def test_right_sell_is_mirror(self):
        from analyzer.waves import _right_wave

        pts = [
            _pt("high", 10, 100.0),
            _pt("low", 30, 93.0),
            _pt("high", 55, 104.0),
            _pt("low", 80, 91.0),
            _pt("high", 105, 101.0),
        ]
        raw, reason = _right_wave(pts, 1.0)
        self.assertIsNone(reason, reason)
        self.assertEqual(raw["side"], "sell")

    def test_left_sell_three_and_three(self):
        from analyzer.waves import _left_wave

        pts = [
            _pt("low", 10, 97.0),
            _pt("high", 30, 104.0),
            _pt("low", 55, 98.0),
            _pt("high", 80, 111.0),
            _pt("low", 105, 100.0),
            _pt("high", 130, 107.0),
        ]
        raw, reason = _left_wave(pts, 1.0)
        self.assertIsNone(reason, reason)
        self.assertEqual(raw["kind"], "left")
        self.assertEqual(raw["side"], "sell")

    def test_reject_when_5_beyond_head(self):
        from analyzer.waves import _right_wave

        pts = [
            _pt("low", 10, 100.0),
            _pt("high", 30, 107.0),
            _pt("low", 55, 96.0),
            _pt("high", 80, 105.0),
            _pt("low", 105, 92.0),
        ]
        raw, reason = _right_wave(pts, 1.0)
        self.assertIsNone(raw)
        self.assertIn(reason, {"5_beyond_3", "4to5_longer"})

    def test_sideways_has_no_wave(self):
        from analyzer.waves import find_waves

        knots = [(0, 100.0)]
        px = 100.0
        i = 0
        for _ in range(12):
            i += 8
            px = 100.4 if px <= 100.0 else 99.6
            knots.append((i, px))
        pack = find_waves(_path_bars(knots, wick=0.02), min_pct=1.0, window=40)
        self.assertEqual(pack["waves"], [])

    def test_format_waves_mentions_legs(self):
        from analyzer.waves import format_waves

        text = format_waves(
            {
                "sec": "GAZP",
                "class_code": "TQBR",
                "clock": datetime(2026, 1, 1, 12, 0),
                "align": {"side": None, "tfs": []},
                "tfs": {
                    "M1": {
                        "bars": 10,
                        "last_bar": datetime(2026, 1, 1, 12, 0),
                        "close": 100.0,
                        "min_pct": 0.15,
                        "pivots": [],
                        "legs": [],
                        "waves": [],
                        "current": None,
                        "reject_counts": {},
                    },
                    "M10": {
                        "bars": 10,
                        "last_bar": datetime(2026, 1, 1, 12, 0),
                        "close": 100.0,
                        "min_pct": 0.2,
                        "pivots": [],
                        "legs": [],
                        "waves": [],
                        "current": None,
                        "reject_counts": {},
                    },
                    "M30": {
                        "bars": 10,
                        "last_bar": datetime(2026, 1, 1, 12, 0),
                        "close": 100.0,
                        "min_pct": 0.25,
                        "pivots": [],
                        "legs": [],
                        "waves": [],
                        "current": None,
                        "reject_counts": {},
                    },
                },
            }
        )
        self.assertIn("GAZP", text)
        self.assertIn("current: none", text)

    def test_waves_csv_pivots(self):
        from analyzer.waves import format_pivot_dt, write_waves_csv

        t0 = datetime(2026, 9, 25, 10, 0)
        pivots = [
            {
                "kind": "low",
                "i": 0,
                "dt": t0,
                "price": 12.789,
                "confirmed": True,
            },
            {
                "kind": "high",
                "i": 30,
                "dt": t0 + timedelta(minutes=30),
                "price": 12.848,
                "confirmed": False,
            },
        ]
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "CR_SPBFUT_M30.csv"
            write_waves_csv(path, pivots)
            text = path.read_text(encoding="utf-8")
        self.assertIn("datetime;kind;price;confirmed", text)
        self.assertIn(format_pivot_dt(t0) + ";low;12.789000;1", text)
        self.assertIn(";high;12.848000;0", text)

    def test_waves_csv_target_14(self):
        from analyzer.waves import format_pivot_dt, write_targets_csv

        t0 = datetime(2026, 9, 6, 10, 0)
        waves = [
            {
                "kind": "right",
                "side": "sell",
                "status": "complete",
                "points": [
                    {"n": 1, "dt": t0, "price": 13.10},
                    {"n": 2, "dt": t0, "price": 12.90},
                    {"n": 3, "dt": t0, "price": 13.20},
                    {"n": 4, "dt": t0 + timedelta(hours=2), "price": 12.95},
                    {"n": 5, "dt": t0 + timedelta(hours=4), "price": 13.076},
                ],
            }
        ]
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "CR_SPBFUT_M30_14.csv"
            write_targets_csv(path, waves)
            text = path.read_text(encoding="utf-8")
        self.assertIn("dt1;px1;dt4;px4;dt5;px5;side;kind;status", text)
        self.assertIn(format_pivot_dt(t0) + ";13.100000;", text)
        self.assertIn(";sell;right;complete", text)

    def test_last_zigzag_14_uses_last_five_confirmed(self):
        from analyzer.waves import last_zigzag_14, target_rows

        t0 = datetime(2026, 9, 25, 13, 30)
        pivots = []
        seq = [
            ("low", 12.731),
            ("high", 12.764),
            ("low", 12.734),
            ("high", 12.767),
            ("low", 12.738),
        ]
        for i, (kind, px) in enumerate(seq):
            pivots.append(
                {
                    "kind": kind,
                    "i": i,
                    "dt": t0 + timedelta(minutes=10 * i),
                    "price": px,
                    "confirmed": True,
                }
            )
        pivots.append(
            {
                "kind": "high",
                "i": 5,
                "dt": t0 + timedelta(hours=4),
                "price": 12.764,
                "confirmed": False,
            }
        )
        rows = target_rows(last_zigzag_14(pivots))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["side"], "buy")
        self.assertEqual(rows[0]["kind"], "zz")
        self.assertAlmostEqual(rows[0]["px1"], 12.731)
        self.assertAlmostEqual(rows[0]["px4"], 12.767)
        self.assertAlmostEqual(rows[0]["px5"], 12.738)


class OddsTests(unittest.TestCase):
    def test_chain_window_is_three_on_every_tf(self):
        from analyzer.odds import CHAIN_BARS, CHAIN_WINDOW

        self.assertEqual(CHAIN_BARS, 3)
        for tf in ("M1", "M10", "M30", "H4", "D1"):
            self.assertEqual(CHAIN_WINDOW[tf], 3)

    def test_forming_d1_appends_unfinished_day(self):
        from analyzer.odds import forming_d1

        d1 = [Bar(datetime(2026, 9, 29), 12.0, 12.2, 11.9, 12.1)]
        m1 = [
            Bar(datetime(2026, 9, 30, 10, 0), 12.1, 12.3, 12.0, 12.2),
            Bar(datetime(2026, 9, 30, 10, 1), 12.2, 12.4, 12.1, 12.25),
        ]
        out = forming_d1(d1, m1)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[-1].dt, datetime(2026, 9, 30))
        self.assertAlmostEqual(out[-1].o, 12.1)
        self.assertAlmostEqual(out[-1].h, 12.4)
        self.assertAlmostEqual(out[-1].l, 12.0)
        self.assertAlmostEqual(out[-1].c, 12.25)

    def test_forming_d1_refreshes_today_from_m1(self):
        from analyzer.odds import forming_d1

        d1 = [Bar(datetime(2026, 9, 30), 12.0, 12.2, 11.9, 12.1)]
        m1 = [
            Bar(datetime(2026, 9, 30, 10, 0), 12.05, 12.3, 12.0, 12.2),
            Bar(datetime(2026, 9, 30, 18, 0), 12.2, 12.5, 12.1, 12.4),
        ]
        out = forming_d1(d1, m1)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[-1].o, 12.05)
        self.assertAlmostEqual(out[-1].h, 12.5)
        self.assertAlmostEqual(out[-1].l, 12.0)
        self.assertAlmostEqual(out[-1].c, 12.4)

    def test_slot_open_midnight_aligned(self):
        from analyzer.odds import slot_open

        self.assertEqual(slot_open(datetime(2026, 10, 1, 11, 55), 10), datetime(2026, 10, 1, 11, 50))
        self.assertEqual(slot_open(datetime(2026, 10, 1, 11, 55), 30), datetime(2026, 10, 1, 11, 30))
        self.assertEqual(slot_open(datetime(2026, 10, 1, 11, 55), 240), datetime(2026, 10, 1, 8, 0))
        self.assertEqual(slot_open(datetime(2026, 10, 1, 11, 55), 1440), datetime(2026, 10, 1))

    def test_append_forming_from_m1(self):
        from analyzer.odds import append_forming

        m10 = [Bar(datetime(2026, 10, 1, 11, 40), 12.0, 12.1, 11.9, 12.05)]
        m1 = [
            Bar(datetime(2026, 10, 1, 11, 50), 12.05, 12.2, 12.0, 12.1),
            Bar(datetime(2026, 10, 1, 11, 55), 12.1, 12.3, 12.05, 12.25),
        ]
        out = append_forming(m10, "M10", m1, datetime(2026, 10, 1, 11, 55))
        self.assertEqual(len(out), 2)
        self.assertEqual(out[-1].dt, datetime(2026, 10, 1, 11, 50))
        self.assertAlmostEqual(out[-1].o, 12.05)
        self.assertAlmostEqual(out[-1].h, 12.3)
        self.assertAlmostEqual(out[-1].c, 12.25)

    def test_append_forming_refreshes_current_slot(self):
        from analyzer.odds import append_forming

        m10 = [Bar(datetime(2026, 10, 1, 11, 50), 12.0, 12.1, 11.9, 12.05)]
        m1 = [Bar(datetime(2026, 10, 1, 11, 55), 12.1, 12.4, 12.0, 12.3)]
        out = append_forming(m10, "M10", m1, datetime(2026, 10, 1, 11, 55))
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[-1].c, 12.3)
        self.assertAlmostEqual(out[-1].h, 12.4)

    def test_build_books_forming_chain_lead_to_m1(self):
        from analyzer.odds import _build_books

        m1 = [Bar(datetime(2026, 10, 1, 11, minute), 12.0, 12.1, 11.9, 12.05) for minute in range(50, 56)]
        raw = {
            "M1": m1,
            "M10": [Bar(datetime(2026, 10, 1, 11, 40), 12.0, 12.1, 11.9, 12.0)],
            "M30": [Bar(datetime(2026, 10, 1, 11, 0), 12.0, 12.2, 11.8, 12.0)],
            "D1": [Bar(datetime(2026, 9, 30), 12.0, 12.2, 11.9, 12.1)],
        }
        books = _build_books(raw, "M30")
        self.assertEqual(books["M30"]["packs"][-1]["dt"], datetime(2026, 10, 1, 11, 30))
        self.assertEqual(books["M10"]["packs"][-1]["dt"], datetime(2026, 10, 1, 11, 50))
        self.assertEqual(books["M1"]["packs"][-1]["dt"], datetime(2026, 10, 1, 11, 55))
        self.assertEqual(books["D1"]["packs"][-1]["dt"], datetime(2026, 10, 1))

    def test_odds_rows_writes_forming_zero_without_hold(self):
        from analyzer.odds import odds_rows

        m1 = [Bar(datetime(2026, 10, 1, 11, minute), 12.0, 12.1, 11.9, 12.05) for minute in range(50, 56)]
        raw = {
            "M1": m1,
            "M10": [Bar(datetime(2026, 10, 1, 11, 40), 12.0, 12.1, 11.9, 12.0)],
            "M30": [Bar(datetime(2026, 10, 1, 11, 0), 12.0, 12.2, 11.8, 12.0)],
            "D1": [],
        }
        rows = odds_rows(raw, "M30")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[-1]["dt"], datetime(2026, 10, 1, 11, 30))
        self.assertEqual(rows[-1]["forming"], 1)
        self.assertEqual(rows[-1]["n"], 0)
        self.assertAlmostEqual(rows[-1]["up"], rows[-1]["down"])
        self.assertAlmostEqual(rows[-1]["up"], rows[-1]["flat"])
        self.assertGreater(rows[-1]["up"], 20.0)
        self.assertLess(rows[-1]["up"], 45.0)

    def test_paint_shares_dampens_single_hit(self):
        from analyzer.odds import blend_lines, paint_shares

        one = paint_shares(["up"])
        self.assertEqual(one["n"], 1)
        self.assertLess(one["up"], 60.0)
        self.assertGreater(one["down"], 20.0)
        self.assertGreater(one["flat"], 20.0)
        empty = paint_shares([])
        self.assertEqual(empty["n"], 0)
        self.assertAlmostEqual(empty["up"], empty["down"])
        self.assertAlmostEqual(empty["up"], 100.0 / 3.0, places=4)
        mixed = blend_lines({"up": 50.0, "down": 25.0, "flat": 25.0}, {"up": 100.0, "down": 0.0, "flat": 0.0})
        self.assertLess(mixed["up"], 80.0)
        self.assertGreater(mixed["down"], 10.0)

    def test_at_or_before_can_return_last_bar(self):
        from analyzer.odds import at_or_before_indices

        times = [datetime(2026, 9, 29), datetime(2026, 9, 30)]
        idx = at_or_before_indices([datetime(2026, 9, 30, 18, 0)], times)[0]
        self.assertEqual(idx, 1)

    def test_sim_field_and_shares(self):
        from analyzer.odds import classify_outcome, clip_line, flat_threshold, sample_shares, sim_field

        self.assertAlmostEqual(sim_field(-0.227, -0.385), 0.842, places=3)
        self.assertEqual(classify_outcome(100.0, 100.2, 0.3), "flat")
        self.assertEqual(classify_outcome(100.0, 100.4, 0.3), "up")
        self.assertEqual(classify_outcome(100.0, 99.6, 0.3), "down")
        self.assertEqual(clip_line(90.0), 90.0)
        self.assertEqual(clip_line(40.0), 40.0)
        self.assertEqual(clip_line(-10.0), 0.0)
        self.assertAlmostEqual(flat_threshold([100.0, 100.1, 100.0, 100.2]), 0.025, places=3)
        share = sample_shares(["up", "up", "down", "flat"])
        self.assertEqual(share["n"], 4)
        self.assertAlmostEqual(share["up"], 50.0)
        self.assertAlmostEqual(share["down"], 25.0)

    def _chain_item(
        self,
        small_rpm,
        small_ema,
        middle_rpm,
        middle_ema,
        d_rpm=0.2,
        d_ema=0.05,
        d_hist=0.03,
        cur_rpm=0.5,
        cur_ema=0.4,
        prev_cur_rpm=None,
        prev_cur_ema=None,
        key=("a", "b", "c", "d", "e"),
    ):
        from analyzer.odds import pack_events, pack_layer_order, pack_mag_z, pack_order_z, pack_pos_z

        scales = {
            "current.rpm": 1.0,
            "current.ema": 1.0,
            "small.rpm": 1.0,
            "small.ema": 1.0,
            "middle.rpm": 1.0,
            "middle.ema": 1.0,
            "hist.hist": 1.0,
        }
        if prev_cur_rpm is None:
            prev_cur_rpm = cur_rpm
        if prev_cur_ema is None:
            prev_cur_ema = cur_ema
        layer = {
            "rpm": small_rpm,
            "ema": small_ema,
            "hist": 0.1,
            "d_rpm": d_rpm,
            "d_ema": d_ema,
            "d_hist": d_hist,
        }
        middle = {
            "rpm": middle_rpm,
            "ema": middle_ema,
            "hist": 0.15,
            "d_rpm": d_rpm,
            "d_ema": d_ema,
            "d_hist": d_hist,
        }
        pack = {
            "current": {"rpm": cur_rpm, "ema": cur_ema, "d_rpm": d_rpm, "d_ema": d_ema, "d_hist": None},
            "small": layer,
            "middle": middle,
            "hist": {"hist": 0.1, "d_rpm": None, "d_ema": None, "d_hist": d_hist},
        }
        prev = {
            "current": {"rpm": prev_cur_rpm, "ema": prev_cur_ema, "d_rpm": d_rpm, "d_ema": d_ema, "d_hist": None},
            "small": layer,
            "middle": middle,
            "hist": {"hist": 0.1, "d_rpm": None, "d_ema": None, "d_hist": d_hist},
        }
        events = pack_events(pack, prev, scales, "M30")
        return {
            "pos": pack_order_z(pack, scales, "M30"),
            "layers": pack_layer_order(pack, scales, "M30"),
            "geom": pack_pos_z(pack, scales, "M30"),
            "mag": pack_mag_z(pack, scales, "M30"),
            "current": events["current"],
            "other": events["other"],
            "key": key,
        }

    def test_chain_sim_positions_outrank_magnitudes(self):
        from analyzer.odds import chain_characteristics_sim, chain_sim

        live = self._chain_item(1.0, 0.2, 0.8, 0.3)
        same = self._chain_item(1.0, 0.2, 0.8, 0.3)
        flipped = self._chain_item(0.2, 1.0, 0.8, 0.3)
        quiet = self._chain_item(1.0, 0.2, 0.8, 0.3, d_rpm=-2.0, d_ema=-2.0, d_hist=-2.0)
        live_chain = [live, live]
        self.assertGreaterEqual(chain_sim(live_chain, [same, same]), 0.60)
        chars_flip = chain_characteristics_sim(live_chain, [flipped, flipped])
        self.assertGreaterEqual(chars_flip["pos"], 0.60)
        self.assertLess(chars_flip["layers"], 0.60)
        self.assertGreaterEqual(chars_flip["mag"], 0.60)
        self.assertEqual(chain_sim(live_chain, [flipped, flipped]), 0.0)
        chars_mag = chain_characteristics_sim(live_chain, [quiet, quiet])
        self.assertGreaterEqual(chars_mag["pos"], 0.60)
        self.assertLess(chars_mag["mag"], 0.60)
        self.assertEqual(chain_sim(live_chain, [quiet, quiet]), 0.0)

    def test_chain_sim_pack_delta_threshold(self):
        from analyzer.odds import chain_sim

        a = ("a", "b", "c", "d", "e")
        b = ("x", "b", "c", "d", "e")
        c = ("y", "z", "p", "q", "r")
        first = self._chain_item(1.0, 0.2, 0.8, 0.3, key=a)
        second = self._chain_item(1.0, 0.2, 0.8, 0.3, key=b)
        other = self._chain_item(1.0, 0.2, 0.8, 0.3, key=c)
        self.assertGreaterEqual(chain_sim([first, second], [first, second]), 0.60)
        self.assertEqual(chain_sim([first, second], [first, other]), 0.0)

    def test_chain_sim_current_cross_and_dir(self):
        from analyzer.odds import chain_characteristics_sim, chain_sim

        crossed = self._chain_item(1.0, 0.2, 0.8, 0.3, cur_rpm=1.0, prev_cur_rpm=-1.0, cur_ema=0.2)
        held = self._chain_item(1.0, 0.2, 0.8, 0.3, cur_rpm=1.0, prev_cur_rpm=0.9, cur_ema=0.2)
        falling = self._chain_item(1.0, 0.2, 0.8, 0.3, cur_rpm=1.0, prev_cur_rpm=1.8, cur_ema=0.2)
        live_chain = [crossed, crossed]
        self.assertGreaterEqual(chain_sim(live_chain, [crossed, crossed]), 0.60)
        chars_hold = chain_characteristics_sim(live_chain, [held, held])
        self.assertGreaterEqual(chars_hold["pos"], 0.60)
        self.assertLess(chars_hold["current"], 0.60)
        self.assertEqual(chain_sim(live_chain, [held, held]), 0.0)
        chars_dir = chain_characteristics_sim(live_chain, [falling, falling])
        self.assertLess(chars_dir["current"], 0.60)
        self.assertEqual(chain_sim(live_chain, [falling, falling]), 0.0)
        same_cross = chain_characteristics_sim([held, held], [falling, falling])
        self.assertGreaterEqual(same_cross["current"], 0.60)
        self.assertIn("other", same_cross)

    def _pack_feat(
        self,
        cur_rpm,
        cur_ema,
        prev_cur_rpm=None,
        tf="D1",
        ema_gap=None,
        small_rpm=1.0,
        small_ema=0.2,
        middle_rpm=0.8,
        middle_ema=0.3,
        d_rpm=0.2,
        d_ema=0.05,
        d_hist=0.03,
        close=12.0,
        dt=None,
    ):
        from analyzer.odds import pack_feat

        scales = {
            "current.rpm": 1.0,
            "current.ema": 1.0,
            "small.rpm": 1.0,
            "small.ema": 1.0,
            "middle.rpm": 1.0,
            "middle.ema": 1.0,
            "hist.hist": 1.0,
        }
        if prev_cur_rpm is None:
            prev_cur_rpm = cur_rpm
        if ema_gap is not None:
            cur_ema = cur_rpm - ema_gap
        layer = {
            "rpm": small_rpm,
            "ema": small_ema,
            "hist": 0.1,
            "d_rpm": d_rpm,
            "d_ema": d_ema,
            "d_hist": d_hist,
        }
        middle = {
            "rpm": middle_rpm,
            "ema": middle_ema,
            "hist": 0.15,
            "d_rpm": d_rpm,
            "d_ema": d_ema,
            "d_hist": d_hist,
        }
        pack = {
            "dt": dt or datetime(2026, 10, 1),
            "c": close,
            "current": {"rpm": cur_rpm, "ema": cur_ema, "d_rpm": d_rpm, "d_ema": d_ema, "d_hist": None},
            "small": layer,
            "middle": middle,
            "hist": {"hist": 0.1, "d_rpm": None, "d_ema": None, "d_hist": d_hist},
        }
        prev = {
            "current": {"rpm": prev_cur_rpm, "ema": cur_ema, "d_rpm": d_rpm, "d_ema": d_ema, "d_hist": None},
            "small": layer,
            "middle": middle,
            "hist": {"hist": 0.1, "d_rpm": None, "d_ema": None, "d_hist": d_hist},
        }
        return pack_feat(pack, prev, scales, tf)

    def test_pack_sim_trio_order_not_ema_gap(self):
        from analyzer.odds import pack_sim

        live = self._pack_feat(-0.8, -1.2)
        near = self._pack_feat(-0.8, -2.4)
        flipped = self._pack_feat(-0.8, -0.2)
        self.assertGreaterEqual(pack_sim(near, live), 0.60)
        self.assertEqual(pack_sim(flipped, live), 0.0)

    def test_pack_sim_dir_is_mean_not_min(self):
        from analyzer.odds import pack_sim

        flat = self._pack_feat(-0.8, -1.2, prev_cur_rpm=-0.8)
        rising = self._pack_feat(-0.8, -1.2, prev_cur_rpm=-1.0)
        self.assertGreaterEqual(pack_sim(rising, flat), 0.60)

    def test_pack_sim_strips_tf_for_h4_vs_d1(self):
        from analyzer.odds import pack_sim

        d1 = self._pack_feat(-0.8, -1.2, tf="D1")
        h4 = self._pack_feat(-0.8, -1.2, tf="H4")
        self.assertGreaterEqual(pack_sim(h4, d1), 0.60)

    def test_next_d1_is_first_close_to_the_right(self):
        from analyzer.pack_ahead import _next_d1

        packs = [
            {"dt": datetime(2026, 9, 1), "c": 13.0},
            {"dt": datetime(2026, 9, 2), "c": 12.5},
            {"dt": datetime(2026, 9, 3), "c": 12.0},
        ]
        nxt = _next_d1(packs, datetime(2026, 9, 1, 8, 0))
        self.assertEqual(nxt["c"], 12.5)
        self.assertIsNone(_next_d1(packs, datetime(2026, 9, 3, 20, 0)))

    def test_pack_key_follows_rpm_sign(self):
        from analyzer.odds import pack_key

        scales = {
            "current.rpm": 1.0,
            "current.ema": 1.0,
            "small.rpm": 1.0,
            "small.ema": 1.0,
            "middle.rpm": 1.0,
            "middle.ema": 1.0,
            "hist.hist": 1.0,
        }

        def pack(rpm: float) -> dict:
            layer = {"rpm": rpm, "ema": rpm * 0.5, "hist": rpm, "d_rpm": 0.1, "d_ema": 0.0, "d_hist": 0.05}
            return {
                "current": layer,
                "small": layer,
                "middle": layer,
                "hist": layer,
                "hist_raw": {"hist": rpm, "hist_up": rpm if rpm > 0 else None, "hist_dw": None if rpm > 0 else rpm},
            }

        up_key = pack_key(pack(1.0), scales)
        down_key = pack_key(pack(-1.0), scales)
        self.assertNotEqual(up_key, down_key)
        self.assertEqual(up_key, pack_key(pack(1.0), scales))

    def test_odds_lead_tf_rejects_m1(self):
        from analyzer.odds import BUNDLE_NAMES, BUNDLE_PAIRS, ODDS_DEAD_END, ODDS_LEAD_TFS, odds_rows

        self.assertTrue(ODDS_DEAD_END)
        self.assertEqual(ODDS_LEAD_TFS, ("M10", "M30", "H4"))
        self.assertEqual(BUNDLE_PAIRS, (("D1", "H4"), ("H4", "M30"), ("M30", "M10")))
        self.assertEqual(set(BUNDLE_NAMES.values()), {"связкаД1Н4", "связкаН4М30", "связкаМ30М10"})
        self.assertNotIn(("M10", "M1"), BUNDLE_PAIRS)
        self.assertNotIn(("D1", "M30"), BUNDLE_PAIRS)
        with self.assertRaises(ValueError):
            odds_rows({"M1": []}, "M1")

    def test_write_odds_csv(self):
        import tempfile

        from analyzer.odds import format_odds_dt, write_odds_csv

        t0 = datetime(2026, 9, 30, 10, 0)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "CR_SPBFUT_M30.csv"
            write_odds_csv(
                path,
                [{"dt": t0, "up": 42.0, "down": 35.0, "flat": 23.0, "n": 12}],
            )
            text = path.read_text(encoding="utf-8")
        self.assertIn("datetime;up;down;flat;n", text)
        self.assertIn(format_odds_dt(t0) + ";42.00;35.00;23.00;12", text)

    def test_watch_odds_on_m30_close(self):
        import tempfile

        from analyzer.odds import watch_odds

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            dest = data_dir / "odds"
            (data_dir / "GAZP_TQBR_M30_.csv").write_text("hdr\n", encoding="utf-8")
            (data_dir / "GAZP_TQBR_H4_.csv").write_text("hdr\n", encoding="utf-8")
            calls: list[tuple] = []
            sleeps = {"n": 0}

            def exporter(sec, class_code, dest_dir=None, data_dir=None, tfs=None):
                calls.append(tfs)
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
                    (data_dir / "GAZP_TQBR_M30_.csv").write_text("hdr\nrow\n", encoding="utf-8")

            def stop():
                return sleeps["n"] >= 2

            n = watch_odds(
                "GAZP",
                "TQBR",
                dest_dir=dest,
                data_dir=data_dir,
                poll=1.0,
                exporter=exporter,
                sleeper=sleeper,
                stop=stop,
                log=lambda _m: None,
            )
            self.assertGreaterEqual(n, 1)
            self.assertTrue(any("M30" in (tf or ()) for tf in calls))

    def test_watch_odds_on_m1_tick(self):
        import tempfile

        from analyzer.odds import watch_odds

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            dest = data_dir / "odds"
            (data_dir / "GAZP_TQBR_M1_.csv").write_text("hdr\n", encoding="utf-8")
            calls: list[tuple] = []
            sleeps = {"n": 0}

            def exporter(sec, class_code, dest_dir=None, data_dir=None, tfs=None):
                calls.append(tfs)
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
                    (data_dir / "GAZP_TQBR_M1_.csv").write_text("hdr\nrow\n", encoding="utf-8")

            def stop():
                return sleeps["n"] >= 2

            n = watch_odds(
                "GAZP",
                "TQBR",
                dest_dir=dest,
                data_dir=data_dir,
                poll=1.0,
                exporter=exporter,
                sleeper=sleeper,
                stop=stop,
                log=lambda _m: None,
            )
            self.assertGreaterEqual(n, 1)
            self.assertTrue(any(set(tf or ()) >= {"M10", "M30", "H4"} for tf in calls))

    def test_export_odds_m1_maps_to_lead_tfs(self):
        import tempfile

        from analyzer.odds import export_odds

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            dest = Path(tmpdir) / "odds"
            report = export_odds("GAZP", "TQBR", dest_dir=dest, data_dir=data_dir, tfs=("M1",))
            self.assertEqual(set(report["files"]), {"M10", "M30", "H4"})

    def test_watch_odds_one_compute_per_instrument(self):
        import tempfile

        from analyzer.odds import watch_odds

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            dest = data_dir / "odds"
            for tf in ("M1", "M10", "M30", "H4"):
                (data_dir / f"GAZP_TQBR_{tf}_.csv").write_text("hdr\n1\n", encoding="utf-8")
            calls: list[tuple] = []
            sleeps = {"n": 0}

            def exporter(sec, class_code, dest_dir=None, data_dir=None, tfs=None):
                calls.append(tfs)
                return {
                    "sec": sec,
                    "class_code": class_code,
                    "dir": str(dest),
                    "files": {},
                    "counts": {},
                }

            def sleeper(_wait):
                sleeps["n"] += 1

            def stop():
                return sleeps["n"] >= 1

            n = watch_odds(
                "GAZP",
                "TQBR",
                dest_dir=dest,
                data_dir=data_dir,
                poll=1.0,
                exporter=exporter,
                sleeper=sleeper,
                stop=stop,
                log=lambda _m: None,
            )
            self.assertEqual(n, 1)
            self.assertEqual(calls, [("M10", "M30", "H4")])


class NetTests(unittest.TestCase):
    def test_dims_and_empty_pack(self):
        from analyzer.net import BUNDLE_PAIRS, CHAIN_BARS, FRAME_DIM, IN_DIM, TF_DIM, pack_vec

        self.assertEqual(TF_DIM, 34)
        self.assertEqual(CHAIN_BARS, 3)
        self.assertEqual(BUNDLE_PAIRS, (("D1", "H4"), ("H4", "M30"), ("M30", "M10")))
        self.assertEqual(FRAME_DIM, TF_DIM * CHAIN_BARS * 2)
        self.assertEqual(IN_DIM, FRAME_DIM)
        self.assertEqual(IN_DIM, 204)
        zeros = pack_vec(None, None, [], 0, {})
        self.assertEqual(len(zeros), TF_DIM)
        self.assertTrue(all(v == 0.0 for v in zeros))

    def test_chain_pack_vecs_three_bars(self):
        from analyzer.net import TF_DIM, _chain_pack_vecs

        ok = [0.0] * (TF_DIM - 1) + [1.0]
        miss = [0.0] * TF_DIM
        a = [float(i) for i in range(TF_DIM - 1)] + [1.0]
        b = [float(i + 10) for i in range(TF_DIM - 1)] + [1.0]
        c = [float(i + 20) for i in range(TF_DIM - 1)] + [1.0]
        chained = _chain_pack_vecs([a, b, c], 2)
        self.assertEqual(len(chained), TF_DIM * 3)
        self.assertEqual(chained[:TF_DIM], a)
        self.assertEqual(chained[TF_DIM : 2 * TF_DIM], b)
        self.assertEqual(chained[2 * TF_DIM :], c)
        padded = _chain_pack_vecs([ok], 0)
        self.assertEqual(padded[:TF_DIM], miss)
        self.assertEqual(padded[TF_DIM : 2 * TF_DIM], miss)
        self.assertEqual(padded[2 * TF_DIM :], ok)
        self.assertIsNone(_chain_pack_vecs([miss], 0))

    def test_frame_at_three_bundle_chains(self):
        from analyzer.net import FRAME_DIM, IN_DIM, TF_DIM, _bundles_at

        def pack(n: float, ok: float = 1.0) -> list[float]:
            return [n] * (TF_DIM - 1) + [ok]

        vecs = {
            "D1": [pack(1), pack(2), pack(3)],
            "H4": [pack(4), pack(5), pack(6)],
            "M30": [pack(7), pack(8), pack(9)],
            "M10": [pack(10), pack(11), pack(12)],
        }
        align = {"D1": [2], "H4": [2], "M30": [2], "M10": [2]}
        bundles = _bundles_at(vecs, align, 0)
        self.assertEqual(len(bundles), 3)
        self.assertTrue(all(len(part) == IN_DIM == FRAME_DIM for part in bundles))
        d1h4 = [bundles[0][i * TF_DIM] for i in range(6)]
        h4m30 = [bundles[1][i * TF_DIM] for i in range(6)]
        m30m10 = [bundles[2][i * TF_DIM] for i in range(6)]
        self.assertEqual(d1h4, [1, 2, 3, 4, 5, 6])
        self.assertEqual(h4m30, [4, 5, 6, 7, 8, 9])
        self.assertEqual(m30m10, [7, 8, 9, 10, 11, 12])
        bad = dict(vecs)
        bad["D1"] = [pack(1, ok=0.0)]
        left = _bundles_at(bad, {"D1": [0], "H4": [2], "M30": [2], "M10": [2]}, 0)
        self.assertEqual(len(left), 2)

    def test_bundle_ahead_clocks_and_m5(self):
        from datetime import datetime

        from analyzer.bars import Bar
        from analyzer.net import BUNDLE_AHEAD, ahead_horizon_m1, bars_from_m1

        self.assertEqual(BUNDLE_AHEAD[("M30", "M10")], {"clock": "M1", "period": 1, "bars": 10})
        self.assertEqual(BUNDLE_AHEAD[("H4", "M30")], {"clock": "M5", "period": 5, "bars": 6})
        self.assertEqual(BUNDLE_AHEAD[("D1", "H4")], {"clock": "M30", "period": 30, "bars": 8})
        self.assertEqual(ahead_horizon_m1(("M30", "M10")), 10)
        self.assertEqual(ahead_horizon_m1(("H4", "M30")), 30)
        self.assertEqual(ahead_horizon_m1(("D1", "H4")), 240)
        t0 = datetime(2026, 10, 2, 10, 0)
        m1 = [
            Bar(dt=t0.replace(minute=t0.minute + i), o=1.0 + i, h=2.0 + i, l=0.5, c=1.5 + i)
            for i in range(12)
        ]
        m5 = bars_from_m1(m1, 5)
        self.assertEqual(len(m5), 3)
        self.assertEqual(m5[0].dt, t0)
        self.assertEqual(m5[0].o, 1.0)
        self.assertEqual(m5[0].c, 1.5 + 4)
        self.assertEqual(m5[0].h, 2.0 + 4)

    def test_ahead_pair_for_chart_tf(self):
        from analyzer.net import BUNDLE_PAIRS, N_AHEAD_HEADS, ahead_head_index, ahead_pair_for_tf

        self.assertEqual(N_AHEAD_HEADS, 3)
        self.assertEqual(ahead_head_index(("D1", "H4")), 0)
        self.assertEqual(ahead_head_index(("H4", "M30")), 1)
        self.assertEqual(ahead_head_index(("M30", "M10")), 2)
        self.assertEqual(ahead_pair_for_tf("M1"), ("M30", "M10"))
        self.assertEqual(ahead_pair_for_tf("M10"), ("M30", "M10"))
        self.assertEqual(ahead_pair_for_tf("M30"), ("H4", "M30"))
        self.assertEqual(ahead_pair_for_tf("H4"), ("D1", "H4"))
        self.assertEqual(ahead_pair_for_tf("D1"), ("D1", "H4"))
        self.assertEqual(BUNDLE_PAIRS[ahead_head_index(ahead_pair_for_tf("M10"))], ("M30", "M10"))

    def test_replay_h4_forming_does_not_see_later_slot_high(self):
        from analyzer.net import TF_DIM, _chain_forming, build_books
        from analyzer.tf_from_m1 import closed_bars_from_m1, replay_tf_book, verify_closed_csv

        t0 = datetime(2026, 10, 1, 4, 0)
        m1 = []
        for i in range(240):
            m1.append(Bar(t0 + timedelta(minutes=i), 10.0, 10.2, 9.9, 10.0))
        slot2 = datetime(2026, 10, 1, 8, 0)
        for i in range(240):
            high = 10.2 if i < 120 else 20.0
            close = 10.0 if i < 120 else 19.5
            m1.append(Bar(slot2 + timedelta(minutes=i), 10.0, high, 9.9, close))
        csv_h4 = [
            Bar(t0, 10.0, 10.2, 9.9, 10.0),
            Bar(slot2, 10.0, 20.0, 9.9, 19.5),
        ]
        closed = closed_bars_from_m1(m1, 240)
        self.assertEqual(len(closed), 2)
        self.assertAlmostEqual(closed[1].h, 20.0)
        self.assertEqual(verify_closed_csv(closed, csv_h4, 240)["mismatch"], 0)
        book = replay_tf_book(m1, "H4", csv=csv_h4)
        self.assertIsNotNone(book)
        mid = datetime(2026, 10, 1, 9, 30)
        idx = next(i for i, b in enumerate(m1) if b.dt == mid)
        forming = book["m1_bars"][idx]
        self.assertEqual(forming.dt, slot2)
        self.assertAlmostEqual(forming.h, 10.2)
        self.assertAlmostEqual(forming.c, 10.0)
        self.assertLess(forming.h, closed[1].h)
        self.assertEqual(book["m1_slot"][idx], 1)
        self.assertAlmostEqual(book["m1_packs"][idx]["h"], 10.2)
        late = datetime(2026, 10, 1, 10, 30)
        late_i = next(i for i, b in enumerate(m1) if b.dt == late)
        self.assertAlmostEqual(book["m1_bars"][late_i].h, 20.0)
        raw = {
            "M1": m1,
            "M10": [],
            "M30": [],
            "H4": csv_h4,
            "D1": [],
        }
        books = build_books(raw)
        h4 = books["H4"]
        self.assertAlmostEqual(h4["m1_bars"][idx].h, 10.2)
        self.assertEqual(len(h4["m1_vecs"][idx]), TF_DIM)
        self.assertNotEqual(h4["m1_bars"][idx].h, csv_h4[1].h)
        zeros = [0.0] * TF_DIM
        closed_ok = [0.0] * (TF_DIM - 1) + [1.0]
        forming_ok = [3.0] * (TF_DIM - 1) + [1.0]
        chained = _chain_forming([closed_ok], forming_ok, 1)
        self.assertEqual(chained[:TF_DIM], zeros)
        self.assertEqual(chained[TF_DIM : 2 * TF_DIM], closed_ok)
        self.assertEqual(chained[2 * TF_DIM :], forming_ok)

    def test_pack_vec_marks_and_z(self):
        from analyzer.net import SETUP_NAMES, pack_vec

        scales = {
            "current.rpm": 1.0,
            "current.ema": 1.0,
            "small.rpm": 1.0,
            "small.ema": 1.0,
            "middle.rpm": 1.0,
            "middle.ema": 1.0,
            "hist.hist": 1.0,
        }
        layer = {"rpm": -1.0, "ema": -0.5, "hist": -0.4, "d_rpm": 0.1, "d_ema": 0.0, "d_hist": 0.05}
        pack = {
            "current": layer,
            "small": layer,
            "middle": layer,
            "hist": layer,
            "hist_raw": {"hist": -0.4, "hist_up": None, "hist_dw": -0.4},
        }
        vec = pack_vec(pack, None, [pack], 0, scales)
        self.assertEqual(len(vec), 34)
        self.assertEqual(vec[0], -1.0)
        self.assertEqual(vec[-1], 1.0)
        none_i = 13 + 8 + SETUP_NAMES.index("none")
        self.assertEqual(vec[none_i], 1.0)

    def test_label_bar_pullback_and_entries(self):
        from analyzer.net import ACTION_NAMES, REGIME_NAMES, label_bar

        up = {"side": "up", "start": 10, "end": 20}
        r, a = label_bar(up, 10, senior_dir=-1)
        self.assertEqual(REGIME_NAMES[r], "pullback")
        self.assertEqual(ACTION_NAMES[a], "buy_in")
        r, a = label_bar(up, 20, senior_dir=1)
        self.assertEqual(REGIME_NAMES[r], "impulse")
        self.assertEqual(ACTION_NAMES[a], "buy_out")
        r, a = label_bar(None, 5, senior_dir=1)
        self.assertEqual(REGIME_NAMES[r], "flat")
        self.assertEqual(ACTION_NAMES[a], "none")
        down = {"side": "down", "start": 0, "end": 8}
        r, a = label_bar(down, 0, senior_dir=1)
        self.assertEqual(REGIME_NAMES[r], "pullback")
        self.assertEqual(ACTION_NAMES[a], "sell_in")
        r, a = label_bar(up, 12, senior_dir=0)
        self.assertEqual(REGIME_NAMES[r], "flat")
        self.assertEqual(ACTION_NAMES[a], "none")

    def test_trade_hit_target_before_stop(self):
        from analyzer.net import trade_hit

        closes = [100.0 + i for i in range(50)]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]
        self.assertEqual(trade_hit(1, 10, highs, lows, closes), "win")
        self.assertNotEqual(trade_hit(-1, 10, highs, lows, closes), "win")
        down = [150.0 - i for i in range(50)]
        dh = [c + 0.2 for c in down]
        dl = [c - 0.2 for c in down]
        self.assertEqual(trade_hit(-1, 10, dh, dl, down), "win")
        self.assertNotEqual(trade_hit(1, 10, dh, dl, down), "win")
        trap = [100.0] * 8 + [101.0, 102.0, 90.0] + [89.0] * 20
        th = [c + 0.2 for c in trap]
        tl = [c - 0.2 for c in trap]
        self.assertEqual(trade_hit(1, 8, th, tl, trap, stop_bars=8, horizon=15), "loss")

    def test_label_trades_pullback_in_impulse(self):
        from analyzer.net import label_trades, pullback_in_impulse, regime_from_dirs

        self.assertEqual(pullback_in_impulse(-1, -1, 1, 1), 1)
        self.assertEqual(pullback_in_impulse(1, 1, 1, 1), 0)
        self.assertEqual(regime_from_dirs(1, 1), 1)
        self.assertEqual(regime_from_dirs(1, -1), 2)
        n = 50
        closes = [100.0 + i for i in range(n)]
        highs = [c + 0.2 for c in closes]
        lows = [c - 0.2 for c in closes]
        one = [1] * n
        dip = [-1] * n
        y_r, y_a = label_trades(highs, lows, closes, one, dip, dip, one)
        self.assertEqual(set(y_r), {2})
        self.assertIn(1, y_a)
        self.assertIn(3, y_a)
        self.assertNotIn(2, y_a)
        _yr, no_dip = label_trades(highs, lows, closes, one, one, one, one)
        self.assertEqual(set(no_dip), {0})
        self.assertEqual(set(_yr), {1})
        refuse = [0] * n
        refuse[12] = 1
        _yr, y_refuse = label_trades(highs, lows, closes, one, one, one, one, refuse=refuse)
        self.assertIn(1, y_refuse)
        self.assertIn(3, y_refuse)

    def test_hist_refuse_and_pack_bias(self):
        from analyzer.combo import buy_body, buy_hist, setup_signal
        from analyzer.net import (
            hist_refuse_side,
            miss_hist_buy,
            miss_hist_sell,
            pack_bias,
            pack_dir_from_bias,
        )

        down = {
            "vs0": "below_0",
            "vs_ema": "below_ema",
            "ema_vs0": "below_0",
            "ema_trend": "falling",
        }
        up = {
            "vs0": "above_0",
            "vs_ema": "above_ema",
            "ema_vs0": "above_0",
            "ema_trend": "rising",
        }
        cur_down = {
            "vs0": "below_0",
            "vs_ema": "below_ema",
            "ema_vs0": "below_0",
            "slope": "rising_below_ema",
        }
        cur_up = {
            "vs0": "above_0",
            "vs_ema": "above_ema",
            "ema_vs0": "above_0",
            "slope": "rising_above_ema",
        }
        hist_red = {"hist_sign": "below_0", "hist_dir": "hist_growing"}
        hist_red_shrink = {"hist_sign": "below_0", "hist_dir": "hist_shrinking"}
        hist_green = {"hist_sign": "above_0", "hist_dir": "hist_growing"}
        hist_green_shrink = {"hist_sign": "above_0", "hist_dir": "hist_shrinking"}
        self.assertTrue(buy_body(down, down, cur_down))
        self.assertTrue(buy_hist(hist_red))
        self.assertFalse(buy_hist(hist_red_shrink))
        self.assertEqual(setup_signal(down, down, hist_red_shrink, cur_down), "none")
        self.assertTrue(miss_hist_buy(down, down, hist_red_shrink, cur_down))
        self.assertFalse(miss_hist_buy(down, down, hist_red, cur_down))
        leftover = {
            "current": cur_up,
            "small": down,
            "middle": down,
            "hist": hist_red_shrink,
        }
        self.assertEqual(hist_refuse_side(1, leftover, 0), 1)
        self.assertEqual(hist_refuse_side(1, leftover, -1), 0)
        printed = {"current": cur_down, "small": down, "middle": down, "hist": hist_red}
        self.assertEqual(hist_refuse_side(1, printed, 1), 0)
        almost = {"current": cur_down, "small": down, "middle": down, "hist": hist_red_shrink}
        self.assertEqual(hist_refuse_side(1, almost, 1), 1)
        waiting = {
            "current": dict(cur_down, slope="falling_below_ema"),
            "small": down,
            "middle": down,
            "hist": {"hist_sign": "below_0", "hist_dir": "na"},
        }
        self.assertEqual(hist_refuse_side(1, waiting, 1), 0)
        sell_left = {
            "current": cur_down,
            "small": up,
            "middle": up,
            "hist": hist_green_shrink,
        }
        self.assertEqual(hist_refuse_side(-1, sell_left, 0), -1)
        self.assertTrue(miss_hist_sell(up, up, hist_green_shrink, cur_down))
        d1_cur = {
            "vs0": "below_0",
            "vs_ema": "below_ema",
            "ema_vs0": "above_0",
            "slope": "rising_below_ema",
        }
        bias = pack_bias(d1_cur, down, down, hist_green)
        self.assertGreater(bias, 0.05)
        self.assertEqual(pack_dir_from_bias(bias, True), 1)
        self.assertEqual(pack_dir_from_bias(bias, False), 0)

    def test_layer_div_buy_and_sell_mirror(self):
        from analyzer.net import layer_div_side

        small_dn = {
            "vs0": "above_0",
            "vs_ema": "below_ema",
            "slope": "falling_below_ema",
            "ema_trend": "falling",
        }
        middle_up = {
            "vs0": "above_0",
            "vs_ema": "above_ema",
            "slope": "flat_above_ema",
            "ema_trend": "flat",
            "ema_vs0": "above_0",
        }
        middle_flat = dict(middle_up, vs_ema="near_ema")
        cur_approach = {
            "vs0": "above_0",
            "vs_ema": "below_ema",
            "slope": "falling_below_ema",
            "ema_vs0": "above_0",
            "ema_slope": "flat",
        }
        cur_below = {
            "vs0": "below_0",
            "vs_ema": "below_ema",
            "slope": "rising_below_ema",
            "ema_vs0": "above_0",
            "ema_slope": "flat",
        }
        hist_red_plus = {"hist_sign": "above_0", "hist_dir": "hist_shrinking"}
        buy = {"current": cur_approach, "small": small_dn, "middle": middle_up, "hist": hist_red_plus}
        self.assertEqual(layer_div_side([buy]), 0)
        self.assertEqual(layer_div_side([buy, buy, buy]), 1)
        self.assertEqual(layer_div_side([dict(buy, current=cur_below)] * 3), 1)
        self.assertEqual(layer_div_side([dict(buy, middle=middle_flat)] * 3), 1)
        small_up = {
            "vs0": "below_0",
            "vs_ema": "above_ema",
            "slope": "rising_above_ema",
            "ema_trend": "rising",
        }
        middle_dn = {
            "vs0": "below_0",
            "vs_ema": "below_ema",
            "slope": "flat_below_ema",
            "ema_trend": "falling",
            "ema_vs0": "below_0",
        }
        middle_flat_dn = dict(middle_dn, vs_ema="near_ema", ema_trend="flat")
        cur_from_below = {
            "vs0": "near_0",
            "vs_ema": "above_ema",
            "slope": "rising_above_ema",
            "ema_vs0": "below_0",
        }
        cur_above = {
            "vs0": "above_0",
            "vs_ema": "above_ema",
            "slope": "falling_above_ema",
            "ema_vs0": "below_0",
        }
        hist_green_minus = {"hist_sign": "below_0", "hist_dir": "hist_shrinking"}
        sell = {
            "current": cur_from_below,
            "small": small_up,
            "middle": middle_dn,
            "hist": hist_green_minus,
        }
        self.assertEqual(layer_div_side([sell, sell, sell]), -1)
        self.assertEqual(layer_div_side([dict(sell, current=cur_above)] * 3), -1)
        self.assertEqual(layer_div_side([dict(sell, middle=middle_flat_dn)] * 3), -1)
        growing = dict(sell, hist={"hist_sign": "below_0", "hist_dir": "hist_growing"})
        self.assertEqual(layer_div_side([growing] * 3), 0)

    def test_decide_action_threshold(self):
        import numpy as np

        from analyzer.net import (
            action_from_ph_mean,
            mix_ahead_probs,
            pa_from_ahead_mix,
            strip_action_points,
        )

        up = np.array([0.1, 0.8, 0.1], dtype=np.float32)
        self.assertEqual(action_from_ph_mean(up), "buy_in")
        self.assertEqual(action_from_ph_mean(np.array([0.8, 0.1, 0.1])), "none")
        self.assertEqual(action_from_ph_mean(np.array([0.1, 0.42, 0.40])), "none")
        self.assertEqual(action_from_ph_mean(None), "none")
        ph_by = {
            ("M30", "M10"): np.array([0.1, 0.8, 0.1], dtype=np.float32),
            ("H4", "M30"): np.array([0.1, 0.7, 0.2], dtype=np.float32),
            ("D1", "H4"): np.array([0.2, 0.6, 0.2], dtype=np.float32),
        }
        mixed = mix_ahead_probs(ph_by)
        self.assertIsNotNone(mixed)
        self.assertEqual(action_from_ph_mean(mixed), "buy_in")
        pa = pa_from_ahead_mix(mixed)
        self.assertEqual(float(pa[3]), 0.0)
        self.assertEqual(float(pa[4]), 0.0)
        self.assertIsNone(mix_ahead_probs({("M30", "M10"): up}))
        row = {"action": "buy_in", "buy_in": 80.0}
        self.assertEqual(strip_action_points(row)["action"], "none")
        self.assertEqual(row["action"], "buy_in")

    def test_pred_row_ahead_is_three_head_mean(self):
        import numpy as np

        from analyzer.net import _pred_row

        dt = datetime(2026, 10, 2, 10, 0)
        pr = np.array([0.1, 0.7, 0.2], dtype=np.float32)
        pa = np.array([0.15, 0.60, 0.25, 0.0, 0.0], dtype=np.float32)
        row = _pred_row(dt, pr, pa)
        self.assertAlmostEqual(row["ahead_flat"], 15.0, places=1)
        self.assertAlmostEqual(row["ahead_up"], 60.0, places=1)
        self.assertAlmostEqual(row["ahead_down"], 25.0, places=1)
        self.assertAlmostEqual(row["buy_in"], 60.0, places=1)
        self.assertAlmostEqual(row["sell_in"], 25.0, places=1)
        self.assertEqual(row["ahead"], "ahead_up")
        self.assertEqual(row["buy_out"], 0.0)
        self.assertEqual(row["sell_out"], 0.0)

    def test_window_indices_stride(self):
        from analyzer.net import STRIDE, _sample_indices, window_indices

        self.assertEqual(STRIDE, 1)
        self.assertEqual(_sample_indices(10, 16), [10, 11, 12, 13, 14, 15])
        self.assertEqual(window_indices(5), [0, 1, 2, 3, 4, 5])
        self.assertEqual(window_indices(10, window=3, step=5), [0, 5, 10])

    def test_ahead_label_ten_bars(self):
        from analyzer.net import AHEAD_BARS, ahead_label

        self.assertEqual(AHEAD_BARS, 10)
        n = 12
        closes = [10.0] * n
        highs = [10.0] * n
        lows = [10.0] * n
        highs[5] = 11.0
        self.assertEqual(ahead_label(0, highs, lows, closes, 0.5), 1)
        highs = [10.0] * n
        lows = [10.0] * n
        lows[8] = 9.0
        self.assertEqual(ahead_label(0, highs, lows, closes, 0.5), 2)
        self.assertEqual(ahead_label(0, [10.01] * n, [9.99] * n, closes, 1.0), 0)
        self.assertEqual(ahead_label(11, highs, lows, closes, 0.5), 0)
        long_h = [10.0] * 32
        long_l = [10.0] * 32
        long_c = [10.0] * 32
        long_h[25] = 11.0
        self.assertEqual(ahead_label(0, long_h, long_l, long_c, 0.5, bars=30), 1)

    def test_horizon_flat_threshold_uses_window_excursion(self):
        from analyzer.odds import FLAT_FRAC, flat_threshold
        from analyzer.net import ahead_flat_by_pair, ahead_label, horizon_flat_threshold

        n = 400
        closes = [100.0] * n
        highs = [100.5] * n
        lows = [99.8] * n
        t10 = horizon_flat_threshold(highs, lows, closes, 10)
        t240 = horizon_flat_threshold(highs, lows, closes, 240)
        self.assertAlmostEqual(t10, 0.5 * FLAT_FRAC, places=4)
        self.assertAlmostEqual(t240, 0.5 * FLAT_FRAC, places=4)
        one = flat_threshold(closes)
        self.assertGreater(one, t10)

        saw_h = [100.0 + (i % 80) * 0.05 for i in range(n)]
        saw_l = [100.0] * n
        wide = horizon_flat_threshold(saw_h, saw_l, closes, 240)
        short = horizon_flat_threshold(saw_h, saw_l, closes, 10)
        self.assertGreater(wide, short)

        mild_h = [100.3] * 50
        mild_l = [100.0] * 50
        mild_c = [100.0] * 50
        self.assertEqual(ahead_label(0, mild_h, mild_l, mild_c, 0.5, bars=30), 0)
        self.assertEqual(ahead_label(0, mild_h, mild_l, mild_c, 0.1, bars=30), 1)
        by_pair = ahead_flat_by_pair(saw_h, saw_l, closes)
        self.assertGreater(by_pair[("D1", "H4")], by_pair[("M30", "M10")])

    def test_action_from_three_aheads_and_right_edge(self):
        from analyzer.net import (
            action_from_aheads,
            action_probs_from_aheads,
            max_ahead_m1,
            pair_ahead_labels,
            train_label_stop,
        )

        self.assertEqual(max_ahead_m1(), 240)
        self.assertEqual(train_label_stop(1000, overlay=False), 760)
        self.assertEqual(train_label_stop(1000, overlay=True), 1000)
        up = {("M30", "M10"): 1, ("H4", "M30"): 1, ("D1", "H4"): 1}
        self.assertEqual(action_from_aheads(up), 1)
        self.assertEqual(action_probs_from_aheads(up), (0.0, 1.0, 0.0))
        down2 = {("M30", "M10"): 2, ("H4", "M30"): 2, ("D1", "H4"): 0}
        self.assertEqual(action_from_aheads(down2), 2)
        p = action_probs_from_aheads(down2)
        self.assertAlmostEqual(p[0], 1.0 / 3.0)
        self.assertAlmostEqual(p[2], 2.0 / 3.0)
        mixed = {("M30", "M10"): 1, ("H4", "M30"): 2, ("D1", "H4"): 0}
        self.assertEqual(action_from_aheads(mixed), 0)
        n = 300
        closes = [100.0] * n
        highs = [100.5] * n
        lows = [99.5] * n
        flats = {("M30", "M10"): 0.1, ("H4", "M30"): 0.1, ("D1", "H4"): 0.1}
        self.assertIsNone(pair_ahead_labels(n - 240, highs, lows, closes, flats, 0.3))
        self.assertIsNotNone(pair_ahead_labels(n - 241, highs, lows, closes, flats, 0.3))

    def test_softmax_and_mlp_roundtrip(self):
        import tempfile

        import numpy as np

        from analyzer.net import MLP, fit_mlp, load_net, predict_vec, save_net, softmax

        s = softmax(np.array([[1.0, 1.0, 1.0]], dtype=np.float32))
        self.assertAlmostEqual(float(s.sum()), 1.0, places=5)
        rng = np.random.default_rng(0)
        X = rng.normal(size=(240, 12)).astype(np.float32)
        y_r = np.zeros(240, dtype=np.int64)
        y_a = np.zeros(240, dtype=np.int64)
        y_h = np.zeros(240, dtype=np.int64)
        X[:80, 0] += 4
        y_r[:80] = 0
        X[80:160, 1] += 4
        y_r[80:160] = 1
        y_a[80:160] = 1
        y_h[80:160] = 1
        X[160:, 2] += 4
        y_r[160:] = 2
        y_a[160:] = 2
        y_h[160:] = 2
        cut = 192
        model, last, mean, std = fit_mlp(
            X[:cut],
            y_r[:cut],
            y_a[:cut],
            y_h[:cut],
            X[cut:],
            y_r[cut:],
            y_a[cut:],
            y_h[cut:],
            epochs=14,
            batch=32,
            rng=1,
        )
        self.assertGreater(last["acc_regime"], 0.70)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "net.npz"
            save_net(path, model, mean, std, {"n": 240})
            loaded, m2, s2 = load_net(path)
            pred = predict_vec(loaded, m2, s2, X[-1])
            self.assertIn(pred["regime"], ("flat", "impulse", "pullback"))
            self.assertIn(pred["action"], ("none", "buy_in", "sell_in"))
            self.assertIn(pred["ahead"], ("ahead_flat", "ahead_up", "ahead_down"))
            self.assertIn("Wh0", np.load(path).files)
            pr, pa, phs = loaded.predict_proba(((X[-1] - m2) / s2).astype(np.float32)[None, :])
            self.assertEqual(phs.shape, (1, 3, 3))

    def test_ph_for_tf_not_mixed(self):
        import numpy as np

        from analyzer.net import _ph_for_tf

        m10 = np.array([0.1, 0.8, 0.1], dtype=np.float32)
        m30 = np.array([0.1, 0.1, 0.8], dtype=np.float32)
        h4 = np.array([0.9, 0.05, 0.05], dtype=np.float32)
        ph_by = {("M30", "M10"): m10, ("H4", "M30"): m30, ("D1", "H4"): h4}
        self.assertIs(_ph_for_tf(ph_by, "M10"), m10)
        self.assertIs(_ph_for_tf(ph_by, "M1"), m10)
        self.assertIs(_ph_for_tf(ph_by, "M30"), m30)
        self.assertIs(_ph_for_tf(ph_by, "H4"), h4)
        self.assertIs(_ph_for_tf(ph_by, "D1"), h4)

    def test_align_net_rows_and_csv(self):
        import tempfile

        from analyzer.net import align_net_rows, write_net_csv

        t0 = datetime(2026, 10, 2, 10, 0)
        t1 = datetime(2026, 10, 2, 10, 5)
        rows = [
            {
                "dt": t0,
                "impulse": 40.0,
                "pullback": 10.0,
                "flat": 50.0,
                "buy_in": 5.0,
                "sell_in": 2.0,
                "buy_out": 1.0,
                "sell_out": 0.0,
                "action": "none",
                "regime": "flat",
            },
            {
                "dt": t1,
                "impulse": 70.0,
                "pullback": 5.0,
                "flat": 25.0,
                "buy_in": 60.0,
                "sell_in": 3.0,
                "buy_out": 2.0,
                "sell_out": 1.0,
                "action": "buy_in",
                "regime": "impulse",
            },
        ]
        aligned = align_net_rows(rows, [datetime(2026, 10, 2, 10, 3), datetime(2026, 10, 2, 10, 6)])
        self.assertEqual(aligned[0]["dt"], datetime(2026, 10, 2, 10, 3))
        self.assertEqual(aligned[0]["action"], "none")
        self.assertEqual(aligned[1]["action"], "buy_in")
        mixed = [
            dict(rows[0], impulse=100.0, pullback=0.0, flat=0.0),
            dict(rows[1], dt=datetime(2026, 10, 2, 10, 4), impulse=0.0, pullback=100.0, flat=0.0, action="none"),
        ]
        bucket = align_net_rows(mixed, [datetime(2026, 10, 2, 10, 6)])
        self.assertAlmostEqual(bucket[0]["impulse"], 50.0, places=0)
        self.assertAlmostEqual(bucket[0]["pullback"], 50.0, places=0)
        from analyzer.net import smooth_regime_rows

        sm = smooth_regime_rows(
            [
                dict(rows[0], impulse=100.0, pullback=0.0, flat=0.0),
                dict(rows[1], impulse=0.0, pullback=100.0, flat=0.0),
            ],
            span=3,
        )
        self.assertGreater(sm[1]["impulse"], 5.0)
        self.assertLess(sm[1]["impulse"], 95.0)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "CR_SPBFUT_M1.csv"
            write_net_csv(path, rows)
            text = path.read_text(encoding="utf-8")
        self.assertIn("datetime;impulse;pullback;flat;buy_in;sell_in;buy_out;sell_out;action;ahead_flat;ahead_up;ahead_down", text)
        self.assertIn("buy_in", text)

    def test_freeze_closed_bars_keep_old_values(self):
        from analyzer.net import freeze_closed_rows

        t0 = datetime(2026, 10, 2, 10, 0)
        t1 = datetime(2026, 10, 2, 10, 30)
        old = [
            {
                "dt": t0,
                "impulse": 40.0,
                "pullback": 10.0,
                "flat": 50.0,
                "buy_in": 0.0,
                "sell_in": 0.0,
                "buy_out": 0.0,
                "sell_out": 0.0,
                "action": "none",
                "regime": "flat",
            }
        ]
        new = [
            dict(old[0], impulse=10.0, pullback=80.0, flat=10.0, regime="pullback"),
            {
                "dt": t1,
                "impulse": 70.0,
                "pullback": 5.0,
                "flat": 25.0,
                "buy_in": 60.0,
                "sell_in": 3.0,
                "buy_out": 2.0,
                "sell_out": 1.0,
                "action": "buy_in",
                "regime": "impulse",
            },
        ]
        clock = datetime(2026, 10, 2, 10, 40)
        out = freeze_closed_rows(old, new, "M30", clock)
        self.assertEqual(out[0]["impulse"], 40.0)
        self.assertEqual(out[0]["regime"], "flat")
        self.assertEqual(out[1]["impulse"], 70.0)
        old_forming = [old[0], dict(new[1], impulse=1.0, action="none", regime="flat")]
        live = freeze_closed_rows(old_forming, new, "M30", clock)
        self.assertEqual(live[0]["impulse"], 40.0)
        self.assertEqual(live[1]["impulse"], 70.0)
        self.assertEqual(live[1]["action"], "buy_in")


if __name__ == "__main__":
    unittest.main()
