"""Strategy B finance attribution: baseline, independent levers, waterfall, Shapley.

Run from repository root:
    python strategy_b_attribution.py
    python strategy_b_attribution.py --interest-conversion .5
    python strategy_b_attribution.py --financing-conversion .25
This analysis does not overwrite the legacy fixed-60 model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from integrated_levers import run_grid
from lever3_deferred_fee import ROOT, write_csv
from secondcup.inputs import Inputs
from secondcup.lever_attribution import attribute_levers
from secondcup.scenarios import get_launches


def generate(data, launches, *, interest_conversion=1.0,
             financing_conversion=2 / 3, incremental_loan_uptake=1.0,
             landlord_setup=5000.0, landlord_annual=10000.0,
             landlord_cac=500.0, fee_rate=.05):
    rows, quarters, fees, owners = run_grid(
        "B Only", data, launches,
        participation_uplift=True,
        interest_conversion=interest_conversion,
        financing_conversion=financing_conversion,
        incremental_loan_uptake=incremental_loan_uptake,
        landlord_setup=landlord_setup,
        landlord_annual=landlord_annual,
        landlord_cac=landlord_cac,
        fee_rate=fee_rate)
    result = attribute_levers(rows, launches, data)
    return result, quarters, fees, owners


def main():
    p = argparse.ArgumentParser(description="Strategy B vs L1/L2/L3 incremental NPV")
    p.add_argument("--interest-conversion", type=float, default=1.0)
    p.add_argument("--financing-conversion", type=float, default=2 / 3)
    p.add_argument("--incremental-loan-uptake", type=float, default=1.0)
    p.add_argument("--landlord-setup", type=float, default=5000)
    p.add_argument("--landlord-annual", type=float, default=10000)
    p.add_argument("--landlord-cac", type=float, default=500)
    p.add_argument("--fee-rate", type=float, default=.05)
    p.add_argument("--output", type=Path,
                   default=ROOT / "outputs" / "strategy_b_attribution")
    args = p.parse_args()
    data = Inputs.from_file()
    result, quarters, fees, owners = generate(
        data, get_launches("B Only"),
        interest_conversion=args.interest_conversion,
        financing_conversion=args.financing_conversion,
        incremental_loan_uptake=args.incremental_loan_uptake,
        landlord_setup=args.landlord_setup,
        landlord_annual=args.landlord_annual,
        landlord_cac=args.landlord_cac,
        fee_rate=args.fee_rate)

    args.output.mkdir(parents=True, exist_ok=True)
    for key, file in (("scenarios", "scenario_matrix.csv"),
                      ("isolated", "isolated_lever_effects.csv"),
                      ("waterfall", "cumulative_waterfall.csv"),
                      ("shapley", "shapley_attribution.csv"),
                      ("interactions", "lever_interactions.csv")):
        write_csv(args.output / file, result[key])
    write_csv(args.output / "hq_quarters.csv", quarters)
    write_csv(args.output / "owner_cohorts.csv", owners)
    write_csv(args.output / "fee_schedule.csv", fees)
    (args.output / "summary.json").write_text(
        json.dumps(result["summary"], indent=2), encoding="utf-8")
    (args.output / "assumptions.json").write_text(
        json.dumps({
            "strategy": "B Only",
            "interest_conversion": args.interest_conversion,
            "financing_conversion": args.financing_conversion,
            "incremental_loan_uptake": args.incremental_loan_uptake,
            "landlord_setup": args.landlord_setup,
            "landlord_annual": args.landlord_annual,
            "landlord_cac": args.landlord_cac,
            "fee_rate": args.fee_rate,
            "case_consent": "NOT CONFIRMED: 20 informal pilot interests",
            "common_strategy_b_costs": (
                "Setup and full coordination cost included in every case;"
                " cancels from incremental effects"),
            "reserve": "500k reserve is external to 1.2M authorized budget",
        }, indent=2), encoding="utf-8")
    s = result["summary"]
    print("Strategy B only HQ NPV: "
          f"${s['strategy_b_only_npv']:,.0f}, "
          f"{s['baseline_assumed_participating_cafes']} assumed participants")
    print(f"Common B setup ${s['strategy_b_setup_cost']:,.0f}; "
          f"coordination ${s['strategy_b_coordination_cost_per_year']:,.0f}/year.")
    print("\nStandalone incremental HQ NPVs vs Strategy B ONLY:")
    for x in result["isolated"]:
        print(f"  {x['lever']}: ${x['isolated_incremental_npv']:+,.0f}")
    print("\nIncremental cumulative bridge (B -> L1 -> L2 -> L3):")
    for x in result["waterfall"]:
        print(f"  {x['stage']}: NPV ${x['hq_npv']:,.0f}"
              f" | step ${x['marginal_incremental_npv']:+,.0f}"
              f" | total ${x['cumulative_increase_vs_strategy_b']:+,.0f}")
    print("\nOrder-neutral Shapley attribution:")
    for x in result["shapley"]:
        print(f"  {x['lever']}: ${x['shapley_npv_contribution']:+,.0f}")
    print(f"  Total HQ NPV uplift: ${s['all_three_incremental_npv']:+,.0f}")
    print(f"Outputs: {args.output}")


if __name__ == "__main__":
    main()
