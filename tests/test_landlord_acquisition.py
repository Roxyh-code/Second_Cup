"""Regression tests for optional L2 and integrated L1+L2."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from secondcup.hq_financing import FinancingTerms, run_financing
from secondcup.landlord_acquisition import LandlordTerms, run_landlord
from secondcup.inputs import Inputs
from secondcup.scenarios import get_launches


class LandlordTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Inputs.from_file()
        cls.launches = get_launches("B Only")

    def test_incremental_vs_319_baseline(self):
        s = run_landlord("B Only", self.launches, self.data).summary
        self.assertEqual(s["existing_accounts_planning_basis"], 319)
        self.assertEqual(s["incremental_accounts"], 120)
        self.assertEqual(s["incremental_annual_sales_at_steady_state"], 993600)
        self.assertEqual(s["incremental_acquisition_cost"], 60000)

    def test_switch_off_restores_original(self):
        r = run_landlord("B Only", self.launches, self.data,
                         LandlordTerms(signed_conversion_rate=0))
        self.assertEqual(r.summary["incremental_accounts"], 0)
        self.assertAlmostEqual(r.summary["hq_npv_change"], 0, places=2)

    def test_no_duplicate_acquisition_spend(self):
        r = run_landlord("B Only", self.launches, self.data)
        self.assertAlmostEqual(sum(q["acquisition_cost"] for q in r.hq_quarters), 60000)
        self.assertEqual(r.summary["hq_gross_spend_2027_2029"], 370000)
        for q in r.hq_quarters:
            self.assertAlmostEqual(q["combined_hq_cash"],
                                   q["cash_before_acquisition_cost"] - q["acquisition_cost"], places=2)

    def test_financing_composition(self):
        r = run_landlord("B Only", self.launches, self.data,
                         financing=FinancingTerms(uptake=2 / 3))
        self.assertEqual(r.summary["financed_cafes"], 40)
        self.assertEqual(r.summary["gross_loan_advances"], 579000)
        self.assertEqual(r.summary["hq_gross_spend_2027_2029"], 949000)
        self.assertTrue(r.summary["budget_y1_met"] and r.summary["budget_3y_met"])
        self.assertFalse(r.summary["reserve_target_diagnostic_met"])
        self.assertAlmostEqual(sum(q["loan_principal_received"] for q in r.hq_quarters),
                               r.summary["principal_collected_by_2031"], delta=0.02)

    def test_zero_l2_plus_l1_is_l1(self):
        orig = run_financing("B Only", self.launches, self.data,
                             FinancingTerms(uptake=2 / 3))
        r = run_landlord("B Only", self.launches, self.data,
                         LandlordTerms(signed_conversion_rate=0),
                         financing=FinancingTerms(uptake=2 / 3))
        self.assertAlmostEqual(orig.summary["financed_hq_npv_5y"],
                               r.summary["integrated_hq_npv_5y"], places=2)

    def test_case_inputs_unchanged(self):
        before = self.data.get("Downtown", "accounts_min")
        run_landlord("B Only", self.launches, self.data)
        self.assertEqual(before, self.data.get("Downtown", "accounts_min"))

    def test_no_corporate_store_does_nothing(self):
        r = run_landlord("A Only", get_launches("A Only"), self.data)
        self.assertEqual(r.summary["incremental_accounts"], 0)
        self.assertEqual(r.summary["incremental_acquisition_cost"], 0)

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            run_landlord("B Only", self.launches, self.data,
                         LandlordTerms(signed_conversion_rate=1.2))
        with self.assertRaises(ValueError):
            run_landlord("B Only", self.launches, self.data,
                         financing=FinancingTerms(first_quarter_ramp=1))


if __name__ == "__main__":
    unittest.main()
