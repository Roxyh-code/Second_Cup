"""Lever 2 cost-sensitivity tests, independent of original Case assumptions."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from landlord_cost_sensitivity import CostTerms, breakeven, cost_case
from secondcup.hq_financing import FinancingTerms
from secondcup.inputs import Inputs
from secondcup.landlord_acquisition import LandlordTerms, run_landlord
from secondcup.scenarios import get_launches


class LandlordCostSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Inputs.from_file()
        cls.launches = get_launches("B Only")
        cls.terms = LandlordTerms()

    def test_no_fixed_cost_matches_original_l2(self):
        old = run_landlord("B Only", self.launches, self.data).summary
        new = cost_case("B Only", self.launches, self.data,
                        self.terms, CostTerms(500, 0, 0))["summary"]
        self.assertAlmostEqual(new["fully_costed_hq_npv_5y"],
                               old["integrated_hq_npv_5y"], delta=0.10)
        self.assertEqual(new["incremental_acquisition_cost"], 60_000)
        self.assertEqual(new["five_year_total_new_hq_cost_undiscounted"], 60_000)

    def test_setup_and_support_added_once_and_correctly_to_budget(self):
        raw = run_landlord("B Only", self.launches, self.data).summary
        result = cost_case("B Only", self.launches, self.data, self.terms,
                           CostTerms(500, 100, 10_000))
        s = result["summary"]
        self.assertEqual(s["partner_setup_cost_total"], 4_000)
        self.assertEqual(s["five_year_total_new_hq_cost_undiscounted"], 114_000)
        self.assertEqual(s["hq_gross_spend_y1"], raw["hq_gross_spend_y1"] + 14_000)
        self.assertEqual(s["hq_gross_spend_2027_2029"], raw["hq_gross_spend_2027_2029"] + 34_000)
        self.assertAlmostEqual(result["quarters"][0]["partner_setup_cost"], 4_000)
        self.assertEqual(sum(r["incremental_support_cost"] for r in result["quarters"]), 50_000)
        self.assertEqual(sum(r["landlord_cac"] for r in result["quarters"]), 60_000)

    def test_cac_change_does_not_change_revenue_or_accounts(self):
        a = cost_case("B Only", self.launches, self.data, self.terms, CostTerms(250))
        b = cost_case("B Only", self.launches, self.data, self.terms, CostTerms(750))
        self.assertEqual(a["summary"]["incremental_accounts"], 120)
        self.assertEqual(a["summary"]["incremental_annual_sales_at_steady_state"],
                         b["summary"]["incremental_annual_sales_at_steady_state"])
        self.assertGreater(a["summary"]["fully_costed_hq_npv_5y"],
                           b["summary"]["fully_costed_hq_npv_5y"])

    def test_break_even_reproduces_zero_marginal_npv(self):
        fixed = CostTerms(0, 100, 10000)
        z = breakeven("B Only", self.launches, self.data, self.terms, fixed)
        self.assertGreater(z["npv_break_even_cac_per_account"], 1000)
        self.assertLess(z["npv_break_even_cac_per_account"], 1600)
        r = cost_case("B Only", self.launches, self.data, self.terms,
                      CostTerms(z["npv_break_even_cac_per_account"], 100, 10000))
        self.assertAlmostEqual(r["summary"]["fully_costed_hq_npv_5y"],
                               run_landlord("B Only", self.launches, self.data,
                                            LandlordTerms(partners_by_type={
                                                "Downtown": 0, "University": 0,
                                                "Suburban": 0})).summary[
                                   "integrated_hq_npv_5y"], delta=1)

    def test_same_financing_baseline_comparison(self):
        financing = FinancingTerms(uptake=2 / 3)
        z = breakeven("B Only", self.launches, self.data, self.terms,
                      CostTerms(0, 100, 10_000), financing)
        self.assertTrue(1000 < z["npv_break_even_cac_per_account"] < 1600)
        r = cost_case("B Only", self.launches, self.data, self.terms,
                      CostTerms(500, 100, 10_000), financing=financing)
        self.assertEqual(r["summary"]["financed_cafes"], 40)
        self.assertEqual(r["summary"]["gross_loan_advances"], 579_000)
        self.assertEqual(r["summary"]["hq_gross_spend_2027_2029"], 983_000)

    def test_no_corporate_shows_no_extra_cost(self):
        # The mock test fixture contains only B Only; the empty-launch case is
        # also a legitimate zero-commercial-footprint boundary condition.
        z = cost_case("Empty", [], self.data, self.terms, CostTerms(500,100,10000))
        self.assertEqual(z["summary"]["partner_setup_cost_total"], 0)
        self.assertEqual(z["summary"]["incremental_support_cost_per_year"], 0)

    def test_invalid_negative_and_nonfinite_cost_rejected(self):
        for bad in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                CostTerms(bad).validate()


if __name__ == "__main__":
    unittest.main()
