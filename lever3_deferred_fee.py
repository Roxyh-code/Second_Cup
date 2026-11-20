"""Run Lever 3 independently or with previously built L1/L2."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from secondcup.deferred_program_fee import DeferredFeeTerms, run_deferred_fee
from secondcup.hq_financing import FinancingTerms
from secondcup.landlord_acquisition import LandlordTerms
from secondcup.inputs import Inputs, load_rollouts
from secondcup.scenarios import get_launches


def write_csv(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Second Cup L3 deferred fee")
    parser.add_argument("--strategy", choices=load_rollouts(), default="B Only")
    parser.add_argument("--rates", nargs="+", type=float, default=[0, 0.025, 0.05])
    parser.add_argument("--start-mode", choices=(
        "after_operating_payback", "after_operating_and_loan_payoff", "immediate"),
        default="after_operating_payback")
    parser.add_argument("--fee-base", choices=("all_corporate", "landlord_incremental"),
                        default="all_corporate")
    parser.add_argument("--with-financing", action="store_true")
    parser.add_argument("--financing-uptake", type=float, default=2 / 3)
    parser.add_argument("--with-landlord", action="store_true")
    parser.add_argument("--partners", nargs=3, type=float, default=[12, 8, 20])
    parser.add_argument("--introductions", type=float, default=6)
    parser.add_argument("--conversion", type=float, default=.5)
    parser.add_argument("--cac", type=float, default=500)
    parser.add_argument("--landlord-setup", type=float, default=5000)
    parser.add_argument("--landlord-annual", type=float, default=10000)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    data = Inputs.from_file()
    launches = get_launches(args.strategy)
    finance = FinancingTerms(uptake=args.financing_uptake) if args.with_financing else None
    landlord = (LandlordTerms(
        partners_by_type=dict(zip(("Downtown", "University", "Suburban"), args.partners)),
        tenant_introductions_per_partner=args.introductions,
        signed_conversion_rate=args.conversion,
        acquisition_cost_per_signed_account=args.cac,
        additional_hq_setup_cost=args.landlord_setup,
        additional_hq_annual_cost=args.landlord_annual,
    ) if args.with_landlord else None)
    label = ("L1-" + ("on" if finance else "off")
             + "_L2-" + ("on" if landlord else "off"))
    output = args.output or ROOT / "outputs" / "deferred_fee" / label
    output.mkdir(parents=True, exist_ok=True)
    summaries, hq, fees, owners = [], [], [], []
    for rate in args.rates:
        result = run_deferred_fee(
            args.strategy, launches, data,
            DeferredFeeTerms(rate=rate, start_mode=args.start_mode,
                             fee_base=args.fee_base),
            financing=finance, landlord=landlord)
        tag = f"{rate:.2%}"
        summaries.append({"scenario": tag, **result.summary})
        hq.extend({"scenario": tag, **row} for row in result.hq_quarters)
        fees.extend({"scenario": tag, **row} for row in result.fee_schedule)
        owners.extend({"scenario": tag, **row} for row in result.owner_cohorts)
        s = result.summary
        print(f"{tag:>5} | HQ NPV ${s['hq_npv_5y']:,.0f}"
              f" | fee cash by 2031 ${s['hq_fee_received_by_2031']:,.0f}"
              f" | owner fee NPV ${s['owner_fee_pv_across_5y_cohorts']:,.0f}"
              f" | HQ 4y target {s['hq_four_year_target_met']}"
              f" | owner failures {s['owner_failing_3yr_after_fee']}")
    write_csv(output / "summary.csv", summaries)
    write_csv(output / "hq_quarterly.csv", hq)
    write_csv(output / "fee_schedule.csv", fees)
    write_csv(output / "owner_cohorts.csv", owners)
    (output / "assumptions.json").write_text(json.dumps({
        "strategy": args.strategy, "rates": args.rates,
        "start_mode": args.start_mode, "fee_base": args.fee_base,
        "finance_enabled": args.with_financing,
        "landlord_enabled": args.with_landlord,
        "landlord_setup": args.landlord_setup if landlord else 0,
        "landlord_annual": args.landlord_annual if landlord else 0,
        "case_corporate_hq_coordination": data.rule("corp_hq_annual"),
        "fee_status": "Hypothetical management policy, not a Case fee",
        "trigger": "No charge in the payback quarter; starts NEXT quarter",
    }, indent=2), encoding="utf-8")
    print(f"Outputs: {output}")


if __name__ == "__main__":
    main()
