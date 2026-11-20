"""Financing participation attribution: Case A8 interest is not consent."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from secondcup.inputs import Inputs
from secondcup.scenarios import get_launches, validate_launches
from secondcup.hq_financing import FinancingTerms, run_financing
from secondcup.participation_uplift import (
    ParticipationTerms, build_participation_plans,
    financing_terms_for_participation, run_participation_uplift)
from integrated_levers import run_grid


class ParticipationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Inputs.from_file()
        cls.full = get_launches("B Only")

    def test_twenty_interested_are_not_confirmed(self):
        r = run_participation_uplift("B Only", self.full, self.data)
        s = r["summary"]
        self.assertIsNone(s["confirmed_participants_case"])
        self.assertIn("NOT CONFIRMED", s["consent_status_case"])
        self.assertEqual(s["informally_interested_cafes"], 20)
        self.assertEqual(s["candidate_cafes"], 60)
        self.assertEqual(s["baseline_assumed_participants"], 20)
        self.assertEqual(s["financing_unlocked_cafes"], 27)
        self.assertEqual(s["assumed_participants_with_financing"], 47)
        self.assertEqual(sum(x["financing_unlocked_assumption"] for x in r["by_type"]), 27)

    def test_incremental_loans_exclude_baseline_stores(self):
        result = run_participation_uplift("B Only", self.full, self.data)
        s = result["summary"]
        p = result["planning"]
        self.assertEqual(s["loans_issued_to_incremental_cafes"], 27)
        expected = (p["incremental_counts"]["Downtown"] * 15000
                    + p["incremental_counts"]["University"] * 12000
                    + p["incremental_counts"]["Suburban"] * 15000)
        self.assertEqual(s["gross_loan_advances"], expected)
        self.assertTrue(all(row["funded_cafes"] >= 0 for row in result["loans"]))

    def test_incremental_hq_revenue_and_loan_npv_are_separate(self):
        s = run_participation_uplift("B Only", self.full, self.data)["summary"]
        self.assertGreater(s["incremental_store_annual_sales_at_steady_state"], 0)
        self.assertGreater(s["incremental_hq_annual_royalty_at_steady_state"], 0)
        self.assertGreater(s["incremental_hq_royalty_npv_from_new_participants"], 0)
        self.assertAlmostEqual(
            s["total_hq_npv_gain_vs_baseline"],
            s["incremental_hq_royalty_npv_from_new_participants"]
            + s["financing_net_cash_npv"], delta=.02)
        self.assertAlmostEqual(
            s["incremental_hq_annual_royalty_at_steady_state"],
            s["incremental_store_annual_sales_at_steady_state"] * .075, delta=.01)

    def test_zero_financing_conversion_matches_no_financing_baseline(self):
        t = ParticipationTerms(additional_conversion_with_finance=0)
        s = run_participation_uplift("B Only", self.full, self.data, t)["summary"]
        self.assertEqual(s["financing_unlocked_cafes"], 0)
        self.assertEqual(s["loans_issued_to_incremental_cafes"], 0)
        self.assertAlmostEqual(s["total_hq_npv_gain_vs_baseline"], 0, delta=.02)

    def test_full_conversion_capped_at_sixty_existing_slots(self):
        p = build_participation_plans(self.full, self.data,
                                      ParticipationTerms(1, 1, 1))
        self.assertEqual(sum(p["with_finance_counts"].values()), 60)
        self.assertEqual(sum(p["incremental_counts"].values()), 40)
        self.assertEqual(sum(c.count for c in p["with_finance"]), 60)
        self.assertEqual(validate_launches(p["with_finance"], self.data), [])

    def test_changing_interest_conversion_changes_comparator(self):
        t = ParticipationTerms(interested_conversion=.5,
                               additional_conversion_with_finance=.5)
        s = run_participation_uplift("B Only", self.full, self.data, t)["summary"]
        self.assertEqual(s["baseline_assumed_participants"], 10)
        self.assertEqual(s["financing_unlocked_cafes"], 25)
        self.assertEqual(s["assumed_participants_with_financing"], 35)

    def test_rollout_constraints_and_source_candidate_caps(self):
        r = run_participation_uplift("B Only", self.full, self.data)
        for key in ("baseline_launches", "assisted_launches"):
            self.assertEqual(validate_launches(r[key], self.data), [])
        for t in ("Downtown", "University", "Suburban"):
            self.assertLessEqual(r["planning"]["with_finance_counts"][t],
                                 self.data.get(t, "candidates"))

    def test_original_fixed_sixty_loan_engine_remains_backward_compatible(self):
        x = run_financing("B Only", self.full, self.data,
                          FinancingTerms(uptake=2/3))
        self.assertEqual(x.summary["financed_cafes"], 40)
        self.assertEqual(x.summary["gross_loan_advances"], 579000)

    def test_integrated_financing_switch_changes_participant_count(self):
        rows, qs, fees, owners = run_grid("B Only", self.data, self.full,
                                         participation_uplift=True)
        self.assertEqual(len(rows), 8)
        for row in rows:
            self.assertEqual(row["corporate_cafes"], 47 if row["L1"] else 20)
            self.assertEqual(row["financing_attributed_new_participants"],
                             27 if row["L1"] else 0)
            self.assertEqual(row["case_confirmed_consent"], "UNKNOWN")
        self.assertTrue(any(x["hq_npv_5y"] >
                            rows[0]["hq_npv_5y"] for x in rows if x["L1"]))

    def test_landlord_accounts_scale_to_participation(self):
        rows, _, _, _ = run_grid("B Only", self.data, self.full,
                                 participation_uplift=True)
        alone = next(r for r in rows if not r["L1"] and r["L2"] and not r["L3"])
        combined = next(r for r in rows if r["L1"] and r["L2"] and not r["L3"])
        self.assertGreater(combined["landlord_incremental_accounts"],
                           alone["landlord_incremental_accounts"])
        self.assertLess(combined["landlord_incremental_accounts"], 120)

    def test_bad_rates_rejected(self):
        for val in (-.01, 1.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                build_participation_plans(
                    self.full, self.data,
                    ParticipationTerms(additional_conversion_with_finance=val))

    def test_self_funded_exclusion_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            FinancingTerms(unfunded_priority_by_type={"Downtown": -2}).validate()


if __name__ == "__main__":
    unittest.main()
