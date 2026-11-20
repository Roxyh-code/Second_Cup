"""Tests for the UTCC team's actual cash advance / landlord / slots framing."""
import unittest
from dataclasses import replace
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from secondcup.inputs import Inputs
from secondcup.scenarios import validate_launches
from secondcup.team_aligned import (
    TeamAssumptions, deck_launches, allocate_team_advances,
    evaluate_team_case, run_team_matrix, team_slots_operational_metrics)


class TeamDeckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=Inputs.from_file()
        cls.base=TeamAssumptions()

    def test_team_rollout_exact(self):
        l=deck_launches(self.data)
        self.assertEqual(sum(c.count for c in l),60)
        self.assertEqual(sum(c.count for c in l if c.typ=="Suburban"),32)
        self.assertEqual(sum(c.count for c in l if c.typ=="Downtown"),18)
        self.assertEqual(sum(c.count for c in l if c.typ=="University"),10)
        self.assertEqual(sum(c.count for c in l if c.quarter==0),6)
        self.assertEqual(sum(c.count for c in l if c.quarter==1),0)
        self.assertEqual(max(c.quarter for c in l),10)
        self.assertEqual(validate_launches(l,self.data),[])

    def test_40_loans_579k_and_team_budget_reconciliation(self):
        r=evaluate_team_case(self.data,switches=(True,False,False))
        s=r["summary"]
        self.assertEqual(s["participating_cafes"],60)
        self.assertEqual(s["financed_cafes"],40)
        self.assertEqual(s["gross_hq_loan_advances"],579000)
        self.assertEqual(s["hq_gross_spending_2027"],335000)
        self.assertEqual(s["hq_gross_spending_2027_2029"],914000)
        self.assertTrue(s["hq_spending_budget_3y_met"])
        self.assertEqual(s["hq_coordination_cost_per_year_common"],90000)
        self.assertEqual(s["hq_program_setup_common"],40000)
        self.assertEqual(s["hq_portal_setup_common"],25000)

    def test_60_but_only_20_baseline_are_explicit_assumption(self):
        base=evaluate_team_case(self.data,switches=(False,False,False))["summary"]
        advanced=evaluate_team_case(self.data,switches=(True,False,False))["summary"]
        self.assertEqual(base["participating_cafes"],20)
        self.assertEqual(advanced["new_cafes_enabled_by_L1"],40)
        self.assertEqual(base["case_confirmed_franchisee_consents"],"UNKNOWN")

    def test_5pct_fee_and_store_portal_are_shared_not_l3(self):
        base=evaluate_team_case(self.data,switches=(True,True,False))
        slots=evaluate_team_case(self.data,switches=(True,True,True))
        self.assertEqual(base["summary"]["shared_program_fee_rate"],.05)
        self.assertEqual(slots["summary"]["shared_program_fee_rate"],.05)
        self.assertEqual(base["summary"]["owner_portal_cost_per_store_per_year_common"],1800)
        self.assertEqual(base["summary"]["hq_common_program_fee_through_2031"],
                         slots["summary"]["hq_common_program_fee_through_2031"])

    def test_no_fake_l3_uplift_without_leakage_evidence(self):
        a=evaluate_team_case(self.data,switches=(True,True,False))["summary"]
        b=evaluate_team_case(self.data,switches=(True,True,True))["summary"]
        self.assertEqual(b["hq_5y_npv"],a["hq_5y_npv"])
        self.assertEqual(b["annual_store_sales_steady_state"],
                         a["annual_store_sales_steady_state"])

    def test_l3_conditional_revenue_protection_and_positive_change(self):
        t=replace(self.base,no_slots_sales_leakage=.05)
        a=evaluate_team_case(self.data,switches=(True,True,False),terms=t)
        b=evaluate_team_case(self.data,switches=(True,True,True),terms=t)
        self.assertGreater(b["summary"]["hq_5y_npv"],a["summary"]["hq_5y_npv"])
        self.assertGreater(b["summary"]["annual_store_sales_steady_state"],
                           a["summary"]["annual_store_sales_steady_state"])

    def test_landlord_accounts_and_cac_with_no_phantom_signed_baseline(self):
        a=evaluate_team_case(self.data,switches=(True,True,False))["summary"]
        b=evaluate_team_case(self.data,switches=(False,True,False))["summary"]
        self.assertEqual(a["total_landlord_new_accounts"],120)
        self.assertLess(b["total_landlord_new_accounts"],120)
        self.assertAlmostEqual(a["hq_extra_landlord_cost_5yr"],60000,delta=.02)

    def test_five_year_hq_cash_and_loan_ledgers_reconcile(self):
        x=evaluate_team_case(self.data,switches=(True,True,True))
        q=x["hq_quarters"]
        self.assertEqual(len(q),21)
        self.assertAlmostEqual(sum(p["hq_net_cash"] for p in q),
                               x["summary"]["hq_net_cash_end_2031"],delta=.3)
        self.assertGreater(x["summary"]["principal_recovered_by_2031"],0)
        self.assertLessEqual(x["summary"]["principal_recovered_by_2031"],
                             x["summary"]["gross_hq_loan_advances"]+1e-6)
        self.assertEqual(x["summary"]["owner_negative_cash_quarters"],0)

    def test_suburban_two_slots_math_is_demand_not_capacity(self):
        metrics=team_slots_operational_metrics(self.data,self.base)
        sub=[x for x in metrics if x["cafe_type"]=="Suburban"]
        self.assertEqual(len(sub),2)
        self.assertAlmostEqual(sub[0]["orders_per_week_per_cafe"],16.5)
        self.assertAlmostEqual(sub[0]["average_cups_per_slot"],19.8)
        self.assertAlmostEqual(sub[1]["average_cups_per_slot"],26.55)
        self.assertFalse(sub[0]["capacity_verified"])

    def test_matrix_has_all_eight_and_waterfall_correct(self):
        m=run_team_matrix(self.data,self.base)
        self.assertEqual(len(m["scenarios"]),8)
        self.assertEqual(len(m["waterfall"]),4)
        self.assertAlmostEqual(
            sum(x["step_npv_increase"] for x in m["waterfall"]),
            m["waterfall"][-1]["total_npv_increase_vs_B"],delta=.03)
        self.assertEqual(m["waterfall"][-1]["scenario"],"L11_L21_L31")

    def test_team_order_and_isolated_effects_bridge_reconcile(self):
        m=run_team_matrix(self.data,self.base)
        self.assertEqual(len(m["team_order_waterfall"]),4)
        self.assertEqual(len(m["standalone_effects"]),3)
        self.assertEqual(m["team_order_waterfall"][1]["stage"],
                         "Add Landlord Channel")
        b=m["scenarios"][0]["hq_5y_npv"]
        full=m["scenarios"][-1]["hq_5y_npv"]
        isolated=sum(r["npv_uplift_vs_strategy_B"] for r in m["standalone_effects"])
        synergy=m["value_bridge"][-2]["npv_amount"]
        self.assertAlmostEqual(b+isolated+synergy,full,delta=.03)
        self.assertEqual(m["standalone_effects"][2]["npv_uplift_vs_strategy_B"],0)

    def test_pilot_q1_q2_observed_q3_scale_first_legal(self):
        from secondcup.scenarios import Launch
        pilot=Launch("Suburban","Corporate Accounts",0,6)
        early=Launch("Suburban","Corporate Accounts",1,1)
        permitted=Launch("Suburban","Corporate Accounts",2,1)
        self.assertTrue(validate_launches([pilot,early],self.data))
        self.assertEqual(validate_launches([pilot,permitted],self.data),[])

    def test_extra_landlord_costs_and_fee_off_is_configurable(self):
        t=replace(self.base,landlord_extra_setup=5000,
                  landlord_extra_annual=10000,team_supporting_fee=0)
        a=evaluate_team_case(self.data,switches=(True,False,False),terms=t)
        b=evaluate_team_case(self.data,switches=(True,True,False),terms=t)
        self.assertGreater(b["summary"]["hq_gross_spending_2027_2029"],
                           a["summary"]["hq_gross_spending_2027_2029"])
        self.assertEqual(b["summary"]["hq_common_program_fee_through_2031"],0)

    def test_owner_profit_lifts_match_team_slide_midpoint_figures(self):
        from secondcup.team_aligned import owner_profit_lifts
        rows=owner_profit_lifts(self.data,self.base)
        pre={r["type"]:r for r in rows if not r["landlord_accounts_included"]}
        post={r["type"]:r for r in rows if r["landlord_accounts_included"]}
        self.assertAlmostEqual(pre["Downtown"]["steady_owner_profit_lift_pct"],20,delta=.1)
        self.assertAlmostEqual(pre["University"]["steady_owner_profit_lift_pct"],18,delta=.3)
        self.assertAlmostEqual(pre["Suburban"]["steady_owner_profit_lift_pct"],24,delta=.3)
        for name in pre:
            self.assertGreater(post[name]["steady_owner_profit_lift_pct"],
                               pre[name]["steady_owner_profit_lift_pct"])

    def test_invalid_assumptions_fail(self):
        for t in (replace(self.base,no_slots_sales_leakage=-.1),
                  replace(self.base,conversion_of_intros=1.1),
                  replace(self.base,portal_owner_annual=-3)):
            with self.assertRaises(ValueError):
                evaluate_team_case(self.data,switches=(True,True,True),terms=t)


if __name__=="__main__":
    unittest.main()
