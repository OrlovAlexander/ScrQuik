# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path

from analyzer.bars import Bar, BARS_DIR, csv_path, typical
from analyzer.rpm_current import compute_current, fir_typical
from analyzer.settings import load_up_settings
from analyzer.snapshot import CHART_TFS, analyze_instrument, assert_layout


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
        self.assertIsNotNone(rows[1]["rpm"])


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


if __name__ == "__main__":
    unittest.main()
