"""Strategy B common-cost treatment and lever NPV attribution."""
import sys
import unittest
from itertools import permutations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from secondcup.inputs import Inputs
from secondcup.scenarios import get_launches
from secondcup.lever_attribution import attribute_levers
from integrated_levers import run_grid
from strategy_b_attribution import generate


class AttributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Inputs.from_file()
        cls.launches = get_launches("B Only")
        cls.bridge, _, _, _ = generate(cls.data, cls.launches)

    def test_common_case_B_cost_in_all_eight_scenarios(self):
        s = self.bridge["summary"]
        self.assertEqual(s["strategy_b_setup_cost"], 40000)
        self.assertEqual(s["strategy_b_coordination_cost_per_year"], 90000)
        self.assertLess(s["pv_common_strategy_b_cost"], -393000)
        self.assertEqual(s["case_fixed_cost_added_by_each_lever"], 0)
        for scenario in self.bridge["scenarios"]:
            self.assertEqual(scenario["hq_case_setup_cost"], 40000)
            self.assertEqual(scenario["hq_case_annual_coordination_cost"], 90000)
            self.assertAlmostEqual(
                scenario["hq_npv_5y"],
                scenario["hq_npv_before_common_B_fixed_cost"] +
                scenario["pv_common_strategy_b_fixed_cost"], delta=.02)

    def test_B_baseline_and_L1_are_distinct_total_vs_increment(self):
        s = self.bridge["summary"]
        self.assertAlmostEqual(s["strategy_b_only_npv"], -220292.14, delta=1)
        a = next(x for x in self.bridge["isolated"]
                 if x["lever"] == "L1 Financing")
        self.assertGreater(a["isolated_incremental_npv"], 200000)
        self.assertAlmostEqual(a["isolated_incremental_npv"],
                               219532.09, delta=2)
        self.assertEqual(a["extra_participating_cafes_vs_base"], 27)
        self.assertEqual(a["case_setup_cost_increment"], 0)
        self.assertEqual(a["case_coordination_cost_increment"], 0)

    def test_isolated_L2_and_L3_delta_vs_same_B_baseline(self):
        by_lever = {x["lever"]: x for x in self.bridge["isolated"]}
        self.assertGreater(by_lever["L2 Landlord"]["isolated_incremental_npv"], 0)
        self.assertGreater(by_lever["L3 Deferred Fee"]["isolated_incremental_npv"], 0)
        baseline = self.bridge["summary"]["strategy_b_only_npv"]
        for row in by_lever.values():
            self.assertAlmostEqual(
                baseline + row["isolated_incremental_npv"],
                row["strategy_b_plus_lever_npv"], delta=.02)

    def test_waterfall_reconciles_and_step_order_matters(self):
        x = self.bridge["waterfall"]
        self.assertEqual([a["step"] for a in x], [0, 1, 2, 3])
        self.assertAlmostEqual(
            sum(a["marginal_incremental_npv"] for a in x),
            self.bridge["summary"]["all_three_incremental_npv"], delta=.03)
        self.assertEqual(x[0]["active_cafes"], 20)
        self.assertEqual(x[1]["active_cafes"], 47)
        self.assertEqual(x[3]["active_cafes"], 47)
        self.assertGreater(x[2]["marginal_incremental_npv"],
                           self.bridge["isolated"][1]["isolated_incremental_npv"])

    def test_shapley_reconciles_with_interactions(self):
        shapley_sum = sum(x["shapley_npv_contribution"]
                          for x in self.bridge["shapley"])
        self.assertAlmostEqual(
            shapley_sum, self.bridge["summary"]["all_three_incremental_npv"], delta=.03)
        synergy = sum(x["two_lever_synergy_npv"]
                      for x in self.bridge["interactions"])
        self.assertAlmostEqual(
            synergy, self.bridge["summary"]["interaction_gain_total"], delta=.03)

    def test_ledger_attribution_not_driver_sum(self):
        # Baseline should be B-only, and standalone benefits are NOT additive
        # when L2 accounts or L3 fees are conditional on L1 participation.
        s = self.bridge["summary"]
        self.assertNotAlmostEqual(
            s["isolated_lever_gain_sum"], s["all_three_incremental_npv"], delta=1)
        self.assertGreater(s["interaction_gain_total"], 0)

    def test_reject_incomplete_and_non_participation_grid(self):
        rows, *_ = run_grid("B Only", self.data, self.launches,
                            participation_uplift=True)
        with self.assertRaises(ValueError):
            attribute_levers(rows[:7], self.launches, self.data)
        fixed, *_ = run_grid("B Only", self.data, self.launches,
                             participation_uplift=False)
        with self.assertRaises(ValueError):
            attribute_levers(fixed, self.launches, self.data)

    def test_robust_scenario_higher_interest_or_lower_financing(self):
        bridge, *_ = generate(self.data, self.launches,
                              interest_conversion=.5,
                              financing_conversion=.25)
        self.assertEqual(bridge["summary"]["baseline_assumed_participating_cafes"], 10)
        self.assertTrue(
            bridge["summary"]["full_combo_participating_cafes"] > 10)
        self.assertEqual(
            len(bridge["isolated"]), 3)
        self.assertAlmostEqual(
            sum(x["shapley_npv_contribution"] for x in bridge["shapley"]),
            bridge["summary"]["all_three_incremental_npv"], delta=.03)


if __name__ == "__main__":
    unittest.main()
