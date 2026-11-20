"""Lever 3 regression tests: fee waterfall, start dates, and all L1/L2 combinations."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from secondcup.deferred_program_fee import DeferredFeeTerms, run_deferred_fee
from secondcup.hq_financing import FinancingTerms, run_financing
from secondcup.landlord_acquisition import LandlordTerms, run_landlord
from secondcup.inputs import Inputs
from secondcup.scenarios import get_launches
from integrated_levers import run_grid


class FeeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Inputs.from_file()
        cls.launches = get_launches("B Only")

    def run_case(self, rate=.05, *, financing=None, landlord=None,
                 start_mode="after_operating_payback", fee_base="all_corporate"):
        return run_deferred_fee(
            "B Only", self.launches, self.data,
            DeferredFeeTerms(rate=rate, start_mode=start_mode, fee_base=fee_base),
            financing=financing, landlord=landlord)

    def test_zero_fee_matches_prior_engines(self):
        for f, l in ((None, None), (FinancingTerms(), None),
                     (None, LandlordTerms()),
                     (FinancingTerms(), LandlordTerms())):
            x = self.run_case(0, financing=f, landlord=l)
            self.assertEqual(x.summary["hq_fee_received_by_2031"], 0)
            self.assertEqual(x.summary["owner_fee_pv_across_5y_cohorts"], 0)
            self.assertAlmostEqual(x.summary["hq_npv_5y"],
                                   x.summary["hq_npv_before_fee"], delta=.12)
            self.assertAlmostEqual(x.summary["owner_npv_after_fee_total"],
                                   x.summary["owner_npv_before_fee_total"], delta=.02)

    def test_fees_reconcile_between_hq_and_owners(self):
        x = self.run_case()
        self.assertGreater(x.summary["hq_fee_received_by_2031"], 0)
        self.assertAlmostEqual(sum(q["fee_receipts"] for q in x.hq_quarters),
                               x.summary["hq_fee_received_by_2031"], delta=.15)
        for q in x.hq_quarters:
            self.assertAlmostEqual(q["post_fee_hq_cash"],
                                   q["pre_fee_hq_cash"] + q["fee_receipts"],
                                   delta=.02)
        self.assertAlmostEqual(x.summary["owner_npv_before_fee_total"] -
                               x.summary["owner_npv_after_fee_total"],
                               x.summary["owner_fee_pv_across_5y_cohorts"], delta=.02)

    def test_fee_starts_quarter_after_original_capex_recovered(self):
        x = self.run_case()
        groups = {(row["type"], row["launch_q"]): row for row in x.owner_cohorts}
        for row in x.fee_schedule:
            g = groups[(row["type"], row["launch_q"])]
            if row["fee_active"]:
                self.assertGreaterEqual(row["cumulative_operating_before_quarter"] + 1e-5,
                                        row["original_capex_per_cafe"])
                self.assertGreaterEqual(row["operating_q"], 2)
        self.assertTrue(any(x["first_fee_operating_q"] is not None for x in groups.values()))

    def test_full_financing_does_not_immediately_trigger_fee(self):
        x = self.run_case(financing=FinancingTerms(uptake=1.0))
        funded = [g for g in x.owner_cohorts if g["financed"]]
        self.assertTrue(funded)
        self.assertTrue(all(g["first_fee_operating_q"] is None
                            or g["first_fee_operating_q"] > 1 for g in funded))

    def test_waiting_for_loan_payoff_never_charges_earlier(self):
        normal = self.run_case(financing=FinancingTerms(uptake=1.0))
        cautious = self.run_case(financing=FinancingTerms(uptake=1.0),
                                 start_mode="after_operating_and_loan_payoff")
        self.assertLessEqual(cautious.summary["hq_fee_received_by_2031"],
                             normal.summary["hq_fee_received_by_2031"])
        a = {(g["type"],g["launch_q"],g["financed"]):g for g in normal.owner_cohorts}
        for b in cautious.owner_cohorts:
            x = a[(b["type"],b["launch_q"],b["financed"])]
            if b["first_fee_operating_q"] is not None:
                self.assertGreaterEqual(b["first_fee_operating_q"],
                                        x["first_fee_operating_q"])

    def test_fee_rate_linear_for_fixed_payback_policy(self):
        half = self.run_case(rate=.025)
        full = self.run_case(rate=.05)
        self.assertAlmostEqual(full.summary["hq_fee_received_by_2031"],
                               half.summary["hq_fee_received_by_2031"] * 2, delta=.02)
        self.assertAlmostEqual(full.summary["owner_fee_pv_across_5y_cohorts"],
                               half.summary["owner_fee_pv_across_5y_cohorts"] * 2, delta=.02)

    def test_only_corporate_gets_a_fee(self):
        x = run_deferred_fee("A Only", get_launches("A Only"), self.data)
        self.assertEqual(x.summary["hq_fee_received_by_2031"], 0)
        self.assertTrue(all(row["first_fee_operating_q"] is None
                            for row in x.owner_cohorts))

    def test_incremental_only_requires_landlord_accounts(self):
        baseline = self.run_case(fee_base="landlord_incremental")
        self.assertEqual(baseline.summary["hq_fee_received_by_2031"], 0)
        x = self.run_case(landlord=LandlordTerms(),
                          fee_base="landlord_incremental")
        self.assertGreater(x.summary["hq_fee_received_by_2031"], 0)
        self.assertLess(x.summary["hq_fee_received_by_2031"],
                        self.run_case(landlord=LandlordTerms()).summary[
                            "hq_fee_received_by_2031"])

    def test_fee_does_not_change_gross_spend_or_loan_ledger(self):
        f, l = FinancingTerms(), LandlordTerms(
            additional_hq_setup_cost=5000, additional_hq_annual_cost=10000)
        no_fee = self.run_case(0, financing=f, landlord=l)
        with_fee = self.run_case(.05, financing=f, landlord=l)
        for key in ("hq_gross_spend_y1", "hq_gross_spend_2027_2029",
                    "principal_collected_by_2031", "interest_collected_by_2031",
                    "financed_cafes", "gross_loan_advances"):
            self.assertEqual(no_fee.summary[key], with_fee.summary[key])
        self.assertEqual(with_fee.summary["financed_cafes"], 40)
        self.assertEqual(with_fee.summary["hq_gross_spend_2027_2029"], 984000)

    def test_eight_combinations_are_present_and_reconcile(self):
        rows, quarters, fees, owners = run_grid(
            "B Only", self.data, self.launches)
        self.assertEqual(len(rows), 8)
        self.assertEqual(len({r["scenario"] for r in rows}), 8)
        self.assertEqual(len(quarters), 8 * 21)
        self.assertTrue(all(r["hq_fee_received_by_2031"] == 0
                            for r in rows if not r["L3"]))
        self.assertTrue(any(r["hq_fee_received_by_2031"] > 0
                            for r in rows if r["L3"]))
        self.assertEqual(
            next(r for r in rows if r["scenario"] == "L10_L21_L30")[
                "hq_gross_spend_2027_2029"], 405000)

    def test_invalid_terms_rejected(self):
        for rate in (-.01, 1.01, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.run_case(rate)
        for mode in ("nonsense",):
            with self.assertRaises(ValueError):
                self.run_case(start_mode=mode)
        with self.assertRaises(ValueError):
            self.run_case(financing=FinancingTerms(first_quarter_ramp=1.0))


if __name__ == "__main__":
    unittest.main()
