"""Standalone Lever 1 regression tests against the existing Case model."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from secondcup.hq_financing import FinancingTerms, run_financing
from secondcup.inputs import Inputs, Overrides
from secondcup.scenarios import get_launches


class FinancingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Inputs.from_file()
        cls.launches = get_launches("B Only")

    def test_adoption_off_does_not_change_baseline(self):
        result = run_financing("B Only", self.launches, self.data,
                               FinancingTerms(uptake=0))
        s = result.summary
        self.assertEqual(s["financed_cafes"], 0)
        self.assertEqual(s["gross_loan_advances"], 0)
        self.assertAlmostEqual(s["hq_npv_change"], 0, places=2)
        self.assertTrue(all(q["net_loan_cash"] == 0 for q in result.hq_quarters))

    def test_two_thirds_finances_forty_stores_and_579k(self):
        result = run_financing("B Only", self.launches, self.data)
        s = result.summary
        self.assertEqual(s["eligible_cafes"], 60)
        self.assertEqual(s["financed_cafes"], 40)
        self.assertEqual(s["gross_loan_advances"], 579_000)
        self.assertEqual(s["hq_gross_spend_2027_2029"], 889_000)
        self.assertEqual(s["hq_gross_spend_y1"], 310_000)
        self.assertTrue(s["budget_y1_met"] and s["budget_3y_met"])
        self.assertEqual(s["account_eligibility_basis"], "Case_midpoints_proxy_NOT_signed")

    def test_full_uptake_loan_capital_is_870k(self):
        result = run_financing("B Only", self.launches, self.data,
                               FinancingTerms(uptake=1))
        self.assertEqual(result.summary["financed_cafes"], 60)
        self.assertEqual(result.summary["gross_loan_advances"], 870_000)

    def test_interest_waterfall_and_cash_reconciliation(self):
        result = run_financing("B Only", self.launches, self.data)
        first = next(row for row in result.loan_schedule if row["operating_q"] == 1)
        self.assertAlmostEqual(first["interest_accrued_per_cafe"],
                               first["opening_principal_per_cafe"] * 0.10 / 4, places=5)
        self.assertLessEqual(first["total_debt_service_per_cafe"],
                             first["contribution_per_cafe"] * 0.75 + 1e-5)
        self.assertGreaterEqual(first["owner_retained_per_cafe"],
                                first["contribution_per_cafe"] * 0.25 - 1e-5)
        for q in result.hq_quarters:
            self.assertAlmostEqual(q["combined_hq_cash"],
                                   q["baseline_hq_cash"] + q["net_loan_cash"], places=2)
        self.assertAlmostEqual(result.summary["gross_loan_advances"],
                               sum(q["loan_advances"] for q in result.hq_quarters), places=2)

    def test_first_quarter_ramp_is_half(self):
        result = run_financing("B Only", self.launches, self.data)
        first = next(row for row in result.loan_schedule if row["operating_q"] == 1)
        second = next(row for row in result.loan_schedule
                      if row["operating_q"] == 2 and row["launch_q"] == first["launch_q"]
                      and row["type"] == first["type"])
        self.assertAlmostEqual(first["contribution_per_cafe"] * 2,
                               second["contribution_per_cafe"], places=5)

    def test_signed_account_gate_overrides_case_proxy(self):
        terms = FinancingTerms(uptake=1, signed_accounts_by_type={
            "Downtown": 0, "University": 0, "Suburban": 0})
        result = run_financing("B Only", self.launches, self.data, terms)
        self.assertEqual(result.summary["financed_cafes"], 0)
        self.assertEqual(result.summary["eligible_cafes"], 0)

    def test_unpaid_interest_is_carried_without_fictional_receipts(self):
        o = Overrides(type_parameters={
            "Downtown": {"corp_contrib": 0},
            "University": {"corp_contrib": 0},
            "Suburban": {"corp_contrib": 0},
        })
        result = run_financing("B Only", self.launches, self.data,
                               FinancingTerms(uptake=1), o)
        first = next(row for row in result.loan_schedule if row["operating_q"] == 1)
        self.assertGreater(first["unpaid_interest_per_cafe"], 0)
        self.assertEqual(first["interest_paid_per_cafe"], 0)
        self.assertEqual(result.summary["principal_collected_by_2031"], 0)
        self.assertEqual(result.summary["interest_collected_by_2031"], 0)
        self.assertGreater(result.summary["interest_in_arrears_at_2031"], 0)

    def test_financing_only_acts_on_corporate_cohorts(self):
        hybrid = get_launches("Hybrid - Optimized")
        result = run_financing("Hybrid - Optimized", hybrid, self.data,
                               FinancingTerms(uptake=1))
        self.assertEqual(result.summary["financed_cafes"], 32)
        self.assertTrue(all(row["option"] == "Corporate Accounts" or
                            row["financed_cafes"] == 0 for row in result.owner_groups))

    def test_invalid_terms_rejected(self):
        with self.assertRaises(ValueError):
            run_financing("B Only", self.launches, self.data,
                          FinancingTerms(contribution_sweep=1.2))


if __name__ == "__main__":
    unittest.main()
