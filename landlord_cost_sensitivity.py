"""Lever 2: cost-side sensitivity, financing-compatible, without changing Case inputs.

Run: python landlord_cost_sensitivity.py
     python landlord_cost_sensitivity.py --with-financing
     python landlord_cost_sensitivity.py --annual-support 10000 --partner-onboarding 100

The default landlord funnel (40 partners * 6 introductions * 50% conversion)
is an illustrative management assumption, not a Case observation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from secondcup.hq_financing import FinancingTerms
from secondcup.inputs import Inputs, load_rollouts
from secondcup.landlord_acquisition import LandlordTerms, run_landlord
from secondcup.scenarios import get_launches


@dataclass(frozen=True)
class CostTerms:
    """Extra HQ costs only, on top of the Case's compulsory $90k/year.

    No reduction of the $90k is permitted. Comparison to traditional/direct CAC
    is an alternative-channel counterfactual, NOT booked Case cost savings.
    """
    signed_account_cac: float = 500.0
    partner_onboarding_per_partner: float = 0.0
    annual_incremental_support: float = 0.0

    def validate(self) -> None:
        for field in ("signed_account_cac", "partner_onboarding_per_partner",
                      "annual_incremental_support"):
            if not math.isfinite(getattr(self, field)) or getattr(self, field) < 0:
                raise ValueError(f"{field} must be a finite nonnegative number")


def discounted(flows: list[float], rate: float) -> float:
    return sum(v / (1 + rate) ** (q / 4) for q, v in enumerate(flows))


def _active_partners(launches, terms: LandlordTerms) -> float:
    active = {x.typ for x in launches if x.option == "Corporate Accounts" and x.count > 0}
    return sum(n for typ, n in terms.partners_by_type.items() if typ in active)


def cost_case(strategy, launches, data: Inputs, landlord_terms: LandlordTerms,
              cost: CostTerms, *, financing: FinancingTerms | None = None,
              comparison_npv: float | None = None) -> dict:
    """Compute quarterly incremental costs; HQ bears them, not franchisees.

    CAC is already deducted by run_landlord at each cohort's launch quarter.
    We ONLY subtract incremental fixed expenses here, avoiding double count.
    """
    cost.validate()
    t = LandlordTerms(
        partners_by_type=dict(landlord_terms.partners_by_type),
        tenant_introductions_per_partner=landlord_terms.tenant_introductions_per_partner,
        signed_conversion_rate=landlord_terms.signed_conversion_rate,
        acquisition_cost_per_signed_account=cost.signed_account_cac,
        first_quarter_ramp=landlord_terms.first_quarter_ramp,
    )
    r = run_landlord(strategy, launches, data, t, financing=financing)
    partners = _active_partners(launches, t)
    setup = partners * cost.partner_onboarding_per_partner
    annual = cost.annual_incremental_support if partners else 0.0
    rate = data.rule("discount")
    # The model convention is q0 setup, operating cost at q1..q20.
    rows = []
    cash = []
    for row in r.hq_quarters:
        q = int(row["q"])
        setup_q = setup if q == 0 else 0.0
        support_q = annual / 4 if q > 0 else 0.0
        combined = row["combined_hq_cash"] - setup_q - support_q
        rows.append({
            "q": q, "case_and_lever_hq_cash": row["combined_hq_cash"],
            "landlord_cac": row["acquisition_cost"],
            "partner_setup_cost": round(setup_q, 2),
            "incremental_support_cost": round(support_q, 2),
            "fully_costed_hq_cash": round(combined, 2),
        })
        cash.append(combined)
    hq_npv = discounted(cash, rate)
    y1 = r.summary["hq_gross_spend_y1"] + setup + annual
    y3 = r.summary["hq_gross_spend_2027_2029"] + setup + 3 * annual
    incr = None if comparison_npv is None else hq_npv - comparison_npv
    s = dict(r.summary)
    s.update({
        "signed_account_cac": cost.signed_account_cac,
        "active_landlord_partners": partners,
        "partner_onboarding_per_partner": cost.partner_onboarding_per_partner,
        "incremental_support_cost_per_year": annual,
        "partner_setup_cost_total": round(setup, 2),
        "five_year_incremental_fixed_expense_undiscounted": round(setup + 5 * annual, 2),
        "five_year_total_new_hq_cost_undiscounted": round(
            r.summary["incremental_acquisition_cost"] + setup + 5 * annual, 2),
        "fully_costed_hq_npv_5y": round(hq_npv, 2),
        "lever2_incremental_npv_vs_same_financing": (
            round(incr, 2) if incr is not None else None),
        "fully_costed_hq_4y_cash": round(sum(cash[:17]), 2),
        "hq_4y_target_met": sum(cash[:17]) >= -1e-8,
        "hq_gross_spend_y1": round(y1, 2),
        "hq_gross_spend_2027_2029": round(y3, 2),
        "remaining_3y_budget": round(data.rule("budget_total") - y3, 2),
        "budget_y1_met": y1 <= data.rule("year1_budget") + 1e-8,
        "budget_3y_met": y3 <= data.rule("budget_total") + 1e-8,
        "reserve_target_diagnostic_met": (
            data.rule("budget_total") - y3 >= data.rule("budget_reserve") - 1e-8),
    })
    return {"summary": s, "cashflows": cash, "quarters": rows,
            "acquisition_cohorts": r.acquisition_cohorts}


def breakeven(strategy, launches, data, landlord_terms, fixed: CostTerms,
              financing=None) -> dict:
    """Threshold for L2 marginal NPV > 0, holding the funnel and L1 constant.

    Because CAC is paid at cohort launch and cannot alter demand, incremental
    HQ NPV is affine in CAC. Gross-up using acquisition-cohort timing rather
    than an undiscounted 120-account denominator.
    """
    no_l2_terms = LandlordTerms(
        partners_by_type={t: 0.0 for t in landlord_terms.partners_by_type},
        tenant_introductions_per_partner=landlord_terms.tenant_introductions_per_partner,
        signed_conversion_rate=landlord_terms.signed_conversion_rate,
        first_quarter_ramp=landlord_terms.first_quarter_ramp)
    no_l2 = run_landlord(strategy, launches, data, no_l2_terms,
                         financing=financing)
    control_npv = no_l2.summary["integrated_hq_npv_5y"]
    control_y4 = no_l2.summary["hq_cash_at_year4"]
    zero = cost_case(strategy, launches, data, landlord_terms,
                     CostTerms(0.0, fixed.partner_onboarding_per_partner,
                               fixed.annual_incremental_support),
                     financing=financing, comparison_npv=control_npv)
    cohort_rows = zero["acquisition_cohorts"]
    discount = data.rule("discount")
    accounts_pv = sum(c["incremental_accounts"] / (1 + discount) ** (c["launch_q"] / 4)
                      for c in cohort_rows)
    accounts_y4 = sum(c["incremental_accounts"] for c in cohort_rows
                      if c["launch_q"] <= 16)
    incremental_npv_no_cac = zero["summary"]["fully_costed_hq_npv_5y"] - control_npv
    incremental_y4_no_cac = zero["summary"]["fully_costed_hq_4y_cash"] - control_y4
    # The 3y gross-spend and reserve constraints are a separate question
    # from discounted economic break-even.
    fixed_3y = zero["summary"]["hq_gross_spend_2027_2029"]
    accts_3y = sum(c["incremental_accounts"] for c in cohort_rows
                   if c["launch_q"] < 12)
    return {
        "comparison": "No landlord acquisition, same financing setting",
        "incremental_accounts": zero["summary"]["incremental_accounts"],
        "gross_incremental_annual_sales": zero["summary"]["incremental_annual_sales_at_steady_state"],
        "gross_incremental_hq_royalty_annual": zero["summary"]["incremental_annual_hq_royalty_at_steady_state"],
        "incremental_npv_at_zero_cac_after_fixed": round(incremental_npv_no_cac, 2),
        "discounted_signed_accounts": round(accounts_pv, 5),
        "npv_break_even_cac_per_account": (
            round(incremental_npv_no_cac / accounts_pv, 2) if accounts_pv else None),
        "4y_incremental_cash_break_even_cac": (
            round(incremental_y4_no_cac / accounts_y4, 2) if accounts_y4 else None),
        "max_cac_under_1_2m_budget": (
            round((data.rule("budget_total") - fixed_3y) / accts_3y, 2)
            if accts_3y else None),
        "max_cac_if_500k_reserve_binding": (
            round((data.rule("budget_total") - data.rule("budget_reserve")
                   - fixed_3y) / accts_3y, 2) if accts_3y else None),
        "budget_3y_at_cac_zero": round(fixed_3y, 2),
        "accounts_acquired_in_first_3y": round(accts_3y, 4),
        "note": "Break-evens are marginal to the SAME loan setting; negative thresholds mean already infeasible at CAC=0.",
    }


def _csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Lever 2 landlord acquisition cost sensitivity")
    p.add_argument("--strategy", default="B Only", choices=load_rollouts())
    p.add_argument("--with-financing", action="store_true")
    p.add_argument("--financing-uptake", type=float, default=2 / 3)
    p.add_argument("--partners", nargs=3, type=float, default=[12, 8, 20],
                   metavar=("DOWNTOWN", "UNIVERSITY", "SUBURBAN"))
    p.add_argument("--introductions", type=float, default=6)
    p.add_argument("--conversion", type=float, default=0.50)
    p.add_argument("--cac-values", nargs="+", type=float,
                   default=[0, 250, 500, 750, 1000, 1500, 2000])
    p.add_argument("--partner-onboarding", type=float, default=100,
                   help="One-time HQ activation cost per landlord partner")
    p.add_argument("--annual-support", type=float, default=10000,
                   help="ADDITIONAL annual HQ cost, ON TOP of mandatory 90k")
    p.add_argument("--direct-cac", type=float, default=750,
                   help="Illustrative direct-channel CAC to compare, not Case spending")
    p.add_argument("--output", type=Path, default=None)
    args = p.parse_args()
    if args.direct_cac < 0 or not math.isfinite(args.direct_cac):
        p.error("--direct-cac must be nonnegative and finite")
    data = Inputs.from_file()
    launches = get_launches(args.strategy)
    terms = LandlordTerms(
        partners_by_type=dict(zip(("Downtown", "University", "Suburban"), args.partners)),
        tenant_introductions_per_partner=args.introductions,
        signed_conversion_rate=args.conversion,
        acquisition_cost_per_signed_account=0)
    terms.validate()
    finance = FinancingTerms(uptake=args.financing_uptake) if args.with_financing else None
    fixed = CostTerms(0, args.partner_onboarding, args.annual_support)
    benchmark = breakeven(args.strategy, launches, data, terms, fixed, finance)
    no_l2 = run_landlord(args.strategy, launches, data,
                         LandlordTerms(partners_by_type={t: 0 for t in terms.partners_by_type},
                                       first_quarter_ramp=terms.first_quarter_ramp),
                         financing=finance)
    control_npv = no_l2.summary["integrated_hq_npv_5y"]
    results = []
    for cac in args.cac_values:
        result = cost_case(args.strategy, launches, data, terms,
                           CostTerms(cac, args.partner_onboarding, args.annual_support),
                           financing=finance, comparison_npv=control_npv)
        row = result["summary"]
        results.append(row)
        print(f"CAC ${cac:>7,.0f} | HQ 5Y NPV ${row['fully_costed_hq_npv_5y']:>11,.0f}"
              f" | L2 marginal NPV ${row['lever2_incremental_npv_vs_same_financing']:>+11,.0f}"
              f" | 3y gross spend ${row['hq_gross_spend_2027_2029']:>10,.0f}"
              f" | 4y target {row['hq_4y_target_met']}")
    # A direct CAC alternative does not represent savings from the Case $90k.
    comparison = {
        "direct_cac_counterfactual_per_account": args.direct_cac,
        "landlord_cac_example_per_account": 250,
        "same_account_count": benchmark["incremental_accounts"],
        "illustrative_nominal_cac_avoidance": (
            args.direct_cac - 250) * benchmark["incremental_accounts"],
        "new_sales_due_to_cost_savings_alone": 0,
        "interpretation": "Relative savings vs hypothetical direct acquisition for identical accounts, NOT a deduction from Case base $90k coordination.",
    }
    output = args.output or ROOT / "outputs" / "landlord" / (
        "cost_with_financing" if args.with_financing else "cost_standalone")
    output.mkdir(parents=True, exist_ok=True)
    _csv(output / "cost_scenarios.csv", results)
    with (output / "breakeven.json").open("w", encoding="utf-8") as f:
        json.dump(benchmark, f, indent=2)
    with (output / "channel_comparison.json").open("w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)
    with (output / "assumptions.json").open("w", encoding="utf-8") as f:
        json.dump({"strategy": args.strategy, "finance_enabled": args.with_financing,
                   "finance_uptake": args.financing_uptake,
                   "landlord_terms": asdict(terms), "cost_terms": asdict(fixed),
                   "mandatory_case_coordination_annual": data.global_rules.get("corp_hq_annual", 90000),
                   "cost_savings_not_booked_against_case_baseline": True,
                   "status": "All incremental funnel and cost assumptions are hypothetical"}, f, indent=2)
    print("Break-even CAC (marginal HQ NPV):", benchmark["npv_break_even_cac_per_account"])
    print("Break-even CAC (4-year incremental HQ cash):", benchmark["4y_incremental_cash_break_even_cac"])
    print("Outputs:", output)


if __name__ == "__main__":
    main()
