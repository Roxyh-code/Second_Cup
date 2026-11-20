"""Landlord (Lever 2) cost scenarios and analytical break-even thresholds.

Does NOT change mandated Case $90k Corporate Coordination Cost or $40k setup.
Cost savings mean *lower hypothetical incremental CAC*, not savings from Case HQ
fixed expenses. All scenarios share the same partner funnel and rollout.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from secondcup.hq_financing import FinancingTerms
from secondcup.inputs import Inputs, load_rollouts
from secondcup.landlord_acquisition import LandlordTerms, run_landlord
from secondcup.scenarios import get_launches

TYPES = ("Downtown", "University", "Suburban")
COST_CASES = (
    ("CAC saving (referral efficiencies)", 250.0, 0.0, 0.0),
    ("Current model", 500.0, 0.0, 0.0),
    ("Modest added overhead", 500.0, 5000.0, 10000.0),
    ("Higher added overhead", 500.0, 5000.0, 20000.0),
    ("Combined cost pressure", 1000.0, 5000.0, 20000.0),
)


def pv_factor(data: Inputs, q: int) -> float:
    return (1.0 + data.rule("discount")) ** (-q / 4.0)


def break_even_analysis(strategy, launches, data, terms, financing=None):
    """Calculate analytical upper bounds for HQ incremental value vs no L2.

    The partner funnel and financing assumptions are held fixed. Variable CAC
    occurs at store launch; new HQ fixed management cost accrues for all five
    operating years. L1 is re-run in both comparators (not NPV-added).
    """
    terms.validate()
    zero_partners = replace(
        terms, partners_by_type={t: 0 for t in TYPES},
        acquisition_cost_per_signed_account=0,
        additional_hq_setup_cost=0, additional_hq_annual_cost=0)
    free_terms = replace(terms, acquisition_cost_per_signed_account=0,
                         additional_hq_setup_cost=0, additional_hq_annual_cost=0)
    no_l2 = run_landlord(strategy, launches, data, zero_partners,
                         financing=financing)
    no_cost_l2 = run_landlord(strategy, launches, data, free_terms,
                              financing=financing)
    # Includes any L1 loan-interest change caused by incremental accounts.
    zero_cost_incremental_npv = (
        no_cost_l2.summary["integrated_hq_npv_5y"]
        - no_l2.summary["integrated_hq_npv_5y"])
    pv_new_accounts = sum(
        row["incremental_accounts"] * pv_factor(data, row["launch_q"])
        for row in no_cost_l2.acquisition_cohorts)
    gross_accounts = sum(r["incremental_accounts"]
                         for r in no_cost_l2.acquisition_cohorts)
    gross_accounts_y1 = sum(r["incremental_accounts"]
                            for r in no_cost_l2.acquisition_cohorts
                            if r["launch_q"] < 4)
    gross_accounts_3y = sum(r["incremental_accounts"]
                            for r in no_cost_l2.acquisition_cohorts
                            if r["launch_q"] < 12)
    gross_accounts_4y = sum(r["incremental_accounts"]
                            for r in no_cost_l2.acquisition_cohorts
                            if r["launch_q"] <= 16)
    annuity_pv = sum(pv_factor(data, q) for q in range(1, 21)) / 4.0
    cac = terms.acquisition_cost_per_signed_account
    setup = terms.additional_hq_setup_cost
    annual = terms.additional_hq_annual_cost
    active = no_cost_l2.summary["partner_program_active"]
    if not active:
        return {"incremental_accounts": 0,
                "note": "No landlord program is active: thresholds undefined."}
    if pv_new_accounts <= 0:
        return {"incremental_accounts": 0,
                "note": "No expected new accounts: fixed spending destroys NPV; CAC break-even undefined."}
    # NPV neutrality means L2 delivers no additional value relative to the
    # same baseline, not merely that total HQ NPV remains above zero.
    max_cac_npv = (zero_cost_incremental_npv - setup - annual * annuity_pv) / pv_new_accounts
    max_annual_npv = (zero_cost_incremental_npv - setup - cac * pv_new_accounts) / annuity_pv
    max_setup_npv = zero_cost_incremental_npv - cac * pv_new_accounts - annual * annuity_pv
    # Other independent HQ ceilings: case spending and four-year cash payback.
    s0, s1 = no_l2.summary, no_cost_l2.summary
    max_annual_budget = min(
        data.rule("year1_budget") - s0["hq_gross_spend_y1"]
        - cac * gross_accounts_y1 - setup,
        (data.rule("budget_total") - s0["hq_gross_spend_2027_2029"]
         - cac * gross_accounts_3y - setup) / 3.0)
    max_annual_4y = (s1["hq_cash_at_year4"]
                     - cac * gross_accounts_4y - setup) / 4.0
    max_annual_reserve_diagnostic = (
        data.rule("budget_total") - data.rule("budget_reserve")
        - s0["hq_gross_spend_2027_2029"]
        - cac * gross_accounts_3y - setup) / 3.0
    return {
        "incremental_accounts": round(gross_accounts, 4),
        "discounted_accounts_at_launch": round(pv_new_accounts, 6),
        "pv_of_1_dollar_annual_cost_5y": round(annuity_pv, 6),
        "incremental_pv_before_new_cost": round(zero_cost_incremental_npv, 2),
        "selected_cac": cac, "selected_setup": setup, "selected_annual": annual,
        "max_cac_for_nonnegative_incremental_npv": round(max_cac_npv, 2),
        "max_annual_cost_for_nonnegative_incremental_npv": round(max_annual_npv, 2),
        "max_setup_for_nonnegative_incremental_npv": round(max_setup_npv, 2),
        "max_annual_cost_for_hq_4y_cash_payback": round(max_annual_4y, 2),
        "max_annual_cost_for_case_budget": round(max_annual_budget, 2),
        "max_annual_cost_for_500k_reserve_diagnostic": round(
            max_annual_reserve_diagnostic, 2),
        "binding_max_annual_with_case_budget_and_payback": round(min(
            max_annual_npv, max_annual_4y, max_annual_budget), 2),
        "warning": "Case $500k reserve shown separately; not treated as an additional hard rule.",
    }


def cost_scenarios(strategy, launches, data, base_terms, financing=None):
    baseline_terms = replace(base_terms,
                             partners_by_type={t: 0.0 for t in TYPES},
                             acquisition_cost_per_signed_account=0,
                             additional_hq_setup_cost=0,
                             additional_hq_annual_cost=0)
    baseline = run_landlord(strategy, launches, data, baseline_terms, financing=financing)
    base_npv = baseline.summary["integrated_hq_npv_5y"]
    rows = []
    for label, cac, setup, annual in COST_CASES:
        terms = replace(base_terms, acquisition_cost_per_signed_account=cac,
                        additional_hq_setup_cost=setup,
                        additional_hq_annual_cost=annual)
        summary = run_landlord(strategy, launches, data, terms, financing=financing).summary
        rows.append({
            "scenario": label, "cost_per_signed_account": cac,
            "additional_one_time_hq": setup,
            "additional_annual_hq": annual,
            "incremental_accounts": summary["incremental_accounts"],
            "incremental_annual_sales": summary["incremental_annual_sales_at_steady_state"],
            "cac_gross": summary["incremental_acquisition_cost"],
            "gross_incremental_hq_cost_5y": summary["total_incremental_hq_cost_5y_gross"],
            "hq_npv_5y": summary["integrated_hq_npv_5y"],
            "incremental_hq_npv_vs_no_l2": round(summary["integrated_hq_npv_5y"] - base_npv, 2),
            "hq_cash_year4": summary["hq_cash_at_year4"],
            "hq_4y_met": summary["hq_four_year_target_met"],
            "hq_spend_year1": summary["hq_gross_spend_y1"],
            "hq_spend_2027_2029": summary["hq_gross_spend_2027_2029"],
            "budget_y1_met": summary["budget_y1_met"],
            "budget_3y_met": summary["budget_3y_met"],
            "reserve_diagnostic_met": summary["reserve_target_diagnostic_met"],
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Landlord L2 CAC + fixed-cost sensitivity")
    parser.add_argument("--strategy", default="B Only", choices=load_rollouts())
    parser.add_argument("--with-financing", action="store_true")
    parser.add_argument("--financing-uptake", type=float, default=2 / 3)
    parser.add_argument("--partners", nargs=3, type=float, default=[12, 8, 20])
    parser.add_argument("--introductions", type=float, default=6)
    parser.add_argument("--conversion", type=float, default=0.5)
    parser.add_argument("--cac", type=float, default=500, help="CAC used for threshold calculations")
    parser.add_argument("--setup", type=float, default=5000, help="Extra HQ setup for break-even")
    parser.add_argument("--annual", type=float, default=10000, help="Extra annual HQ cost for break-even")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    data = Inputs.from_file()
    launches = get_launches(args.strategy)
    terms = LandlordTerms(
        partners_by_type=dict(zip(TYPES, args.partners)),
        tenant_introductions_per_partner=args.introductions,
        signed_conversion_rate=args.conversion,
        acquisition_cost_per_signed_account=args.cac,
        additional_hq_setup_cost=args.setup,
        additional_hq_annual_cost=args.annual)
    finance = FinancingTerms(uptake=args.financing_uptake) if args.with_financing else None
    rows = cost_scenarios(args.strategy, launches, data, terms, finance)
    threshold = break_even_analysis(args.strategy, launches, data, terms, finance)
    output = args.output or ROOT / "outputs" / "landlord" / "cost_sensitivity"
    output.mkdir(parents=True, exist_ok=True)
    with (output / "cost_scenarios.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "break_even.json").write_text(json.dumps(threshold, indent=2), encoding="utf-8")
    (output / "assumptions.json").write_text(json.dumps({
        "strategy": args.strategy, "with_financing": args.with_financing,
        "financing_uptake": args.financing_uptake if args.with_financing else 0,
        "partners_by_type": dict(terms.partners_by_type),
        "introductions": args.introductions, "conversion": args.conversion,
        "costs_are_hypothetical": True,
        "mandatory_case_corporate_hq_annual_cost": data.rule("corp_hq_annual"),
        "mandatory_cost_reduction": 0,
        "cost_savings_definition": "lower modeled incremental CAC only"}, indent=2), encoding="utf-8")
    print(f"{'Cost scenario':34} {'HQ NPV':>12} {'Delta vs no L2':>16} {'3y spend':>12}")
    for row in rows:
        print(f"{row['scenario'][:34]:34} "
              f"{row['hq_npv_5y']:12,.0f} "
              f"{row['incremental_hq_npv_vs_no_l2']:16,.0f} "
              f"{row['hq_spend_2027_2029']:12,.0f}")
    print("\nBreak-even ceilings (CAD):")
    for k, v in threshold.items():
        print(f"  {k}: {v}")
    print(f"Outputs: {output}")


if __name__ == "__main__":
    main()
