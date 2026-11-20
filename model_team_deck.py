"""Run team-aligned financial model and publish slide-ready CSV outputs.

NOTE: The shared 5% fee is a supporting team assumption, NOT Lever 3.
L3 is Fixed Production Slots. Without a stated service/revenue leakage
counterfactual it has ZERO incremental cash return (operational guardrail).
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from secondcup.inputs import Inputs
from secondcup.team_aligned import TeamAssumptions, run_team_matrix


def csv_save(path, records):
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)


def main():
    p = argparse.ArgumentParser(description="UTCC team-slide aligned Strategy B model")
    p.add_argument("--leakage-without-slots", type=float, default=0,
                   help="HYPOTHETICAL fractional corporate-order leakage without fixed slots")
    p.add_argument("--landlord-cac", type=float, default=500)
    p.add_argument("--landlord-setup", type=float, default=0)
    p.add_argument("--landlord-annual", type=float, default=0)
    p.add_argument("--landlord-conversion", type=float, default=.30)
    p.add_argument("--loan-uptake", type=float, default=2 / 3)
    p.add_argument("--supporting-fee", type=float, default=.05)
    p.add_argument("--interested-consent", type=float, default=1.0)
    p.add_argument("--slot-setup-per-cafe", type=float, default=0)
    p.add_argument("--slot-annual-per-cafe", type=float, default=0)
    p.add_argument("--output", type=Path, default=ROOT/"outputs"/"team_deck")
    args = p.parse_args()
    t = TeamAssumptions(
        no_slots_sales_leakage=args.leakage_without_slots,
        acquisition_cost_per_account=args.landlord_cac,
        landlord_extra_setup=args.landlord_setup,
        landlord_extra_annual=args.landlord_annual,
        conversion_of_intros=args.landlord_conversion,
        loan_uptake=args.loan_uptake,
        team_supporting_fee=args.supporting_fee,
        base_interest_consent=args.interested_consent,
        slot_setup_per_cafe=args.slot_setup_per_cafe,
        slot_annual_per_cafe=args.slot_annual_per_cafe)
    data = Inputs.from_file()
    matrix = run_team_matrix(data, t)
    for field, filename in (
        ("scenarios", "scenario_matrix.csv"),
        ("waterfall", "waterfall_for_slide.csv"),
        ("hq_quarters", "hq_quarterly.csv"),
        ("owners", "owner_cohorts.csv"),
        ("loans", "loan_schedule.csv"),
        ("slot_metrics", "fixed_slots_capacity.csv"),
    ):
        csv_save(args.output/filename, matrix[field])
    (args.output/"assumptions.json").write_text(
        json.dumps({**vars(t), "status": "Team-slide aligned plus explicitly labeled hypothetical CAC and slot risk",
                    "case_consent": "None confirmed; 20 early interests"},
                   indent=2), encoding="utf-8")
    print("Strategy B Team-deck model")
    print("Common HQ cost: $40k case + $25k portal setup, $90k/year coordination")
    print("Common store policy: $1.8k/year portal, 5% post-CAPEX-payback fee")
    print(f"Slot leakage assumption without slots: {t.no_slots_sales_leakage:.1%}")
    print("Scenario       Cafés    HQ NPV      Δ vs B       HQ payback  2027 spend   3y spend")
    for s in matrix["scenarios"]:
        print(f"{s['scenario']:15} {s['participating_cafes']:3} "
              f"\${s['hq_5y_npv']:10,.0f} "
              f"\${s['hq_incremental_npv_vs_B_only']:+10,.0f} "
              f"{str(s['hq_payback_years']):>10} "
              f"\${s['hq_gross_spending_2027']:9,.0f} "
              f"\${s['hq_gross_spending_2027_2029']:9,.0f}")
    print("Slide waterfall:")
    for x in matrix["waterfall"]:
        print(x["stage"], x["hq_5y_npv"], x["step_npv_increase"])
    print("Outputs:",args.output)


if __name__ == "__main__":
    main()
