"""Incremental fixed-cost stress and break-even tests for Lever 2."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from secondcup.inputs import Inputs
from secondcup.scenarios import get_launches
from secondcup.hq_financing import FinancingTerms
from secondcup.landlord_acquisition import LandlordTerms, run_landlord
from landlord_cost_sensitivity import break_even_analysis, cost_scenarios


class LandlordCostsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Inputs.from_file()
        cls.launches = get_launches("B Only")

    def test_default_retains_existing_model(self):
        r = run_landlord("B Only", self.launches, self.data)
        self.assertEqual(r.summary["incremental_acquisition_cost"], 60000)
        self.assertEqual(r.summary["additional_hq_fixed_cost_5y_gross"], 0)
        self.assertAlmostEqual(r.summary["integrated_hq_npv_5y"], 216990.47, delta=1)

    def test_modest_fixed_cost_cash_and_budget(self):
        old = run_landlord("B Only", self.launches, self.data)
        terms = LandlordTerms(additional_hq_setup_cost=5000,
                              additional_hq_annual_cost=10000)
        new = run_landlord("B Only", self.launches, self.data, terms)
        self.assertEqual(new.summary["additional_hq_fixed_cost_5y_gross"], 55000)
        self.assertEqual(new.summary["total_incremental_hq_cost_5y_gross"], 115000)
        self.assertAlmostEqual(new.summary["hq_gross_spend_y1"] -
                               old.summary["hq_gross_spend_y1"], 15000)
        self.assertAlmostEqual(new.summary["hq_gross_spend_2027_2029"] -
                               old.summary["hq_gross_spend_2027_2029"], 35000)
        self.assertAlmostEqual(new.hq_quarters[0]["additional_partner_setup_cost"], 5000)
        self.assertAlmostEqual(new.hq_quarters[1]["additional_partner_annual_cost"], 2500)
        self.assertAlmostEqual(new.summary["integrated_hq_npv_5y"], 172688.83, delta=1)

    def test_cac_savings_are_not_reduction_of_case_ninety_k(self):
        r0 = run_landlord("B Only", self.launches, self.data)
        r1 = run_landlord("B Only", self.launches, self.data,
                          LandlordTerms(acquisition_cost_per_signed_account=250))
        self.assertAlmostEqual(r1.summary["hq_npv_change"] -
                               r0.summary["hq_npv_change"], 25767.47, delta=1)
        self.assertAlmostEqual(r1.summary["incremental_acquisition_cost"], 30000)
        self.assertEqual(self.data.rule("corp_hq_annual"), 90000)

    def test_partner_fixed_cost_is_real_even_if_no_signups(self):
        terms = LandlordTerms(signed_conversion_rate=0,
                              additional_hq_setup_cost=5000,
                              additional_hq_annual_cost=10000)
        r = run_landlord("B Only", self.launches, self.data, terms)
        self.assertEqual(r.summary["incremental_accounts"], 0)
        self.assertEqual(r.summary["additional_hq_fixed_cost_5y_gross"], 55000)
        empty = replace(terms, partners_by_type={
            "Downtown": 0, "University": 0, "Suburban": 0})
        r2 = run_landlord("B Only", self.launches, self.data, empty)
        self.assertEqual(r2.summary["total_incremental_hq_cost_5y_gross"], 0)

    def test_break_even_matches_linear_scenarios(self):
        t = LandlordTerms(additional_hq_setup_cost=5000,
                          additional_hq_annual_cost=10000)
        b = break_even_analysis("B Only", self.launches, self.data, t)
        self.assertAlmostEqual(b["max_annual_cost_for_nonnegative_incremental_npv"],
                               30412.39, delta=3)
        self.assertAlmostEqual(b["max_cac_for_nonnegative_incremental_npv"],
                               1278.36, delta=3)
        self.assertLess(b["binding_max_annual_with_case_budget_and_payback"], 31000)
        scenarios = cost_scenarios("B Only", self.launches, self.data, t)
        self.assertEqual(len(scenarios), 5)
        self.assertLess(scenarios[-1]["incremental_hq_npv_vs_no_l2"], 0)

    def test_financing_composes_and_cost_is_on_hq_only(self):
        finance = FinancingTerms(uptake=2 / 3)
        old = run_landlord("B Only", self.launches, self.data, financing=finance)
        new = run_landlord("B Only", self.launches, self.data,
                           LandlordTerms(additional_hq_setup_cost=5000,
                                         additional_hq_annual_cost=10000),
                           financing=finance)
        self.assertEqual(old.summary["financed_cafes"], new.summary["financed_cafes"])
        self.assertEqual(old.summary["principal_collected_by_2031"],
                         new.summary["principal_collected_by_2031"])
        self.assertAlmostEqual(old.summary["integrated_hq_npv_5y"] -
                               new.summary["integrated_hq_npv_5y"], 44301.19, delta=1)
        self.assertEqual(old.summary["owner_npv_financed_total"],
                         new.summary["owner_npv_financed_total"])

    def test_negative_additional_costs_rejected(self):
        for name in ("additional_hq_setup_cost", "additional_hq_annual_cost"):
            with self.assertRaises(ValueError):
                run_landlord("B Only", self.launches, self.data,
                             replace(LandlordTerms(), **{name: -1}))


if __name__ == "__main__":
    unittest.main()
