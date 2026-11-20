"""Run standalone Lever 1 financing scenarios without changing baseline inputs.

From repository root:
    python lever1_hq_financing.py
    python lever1_hq_financing.py --strategy "Hybrid - Optimized" --rates 0 0.6666666667 1
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from secondcup.hq_financing import FinancingTerms, run_financing
from secondcup.inputs import Inputs, load_rollouts
from secondcup.scenarios import get_launches


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent HQ Financing lever")
    parser.add_argument("--strategy", default="B Only", choices=load_rollouts())
    parser.add_argument("--rates", nargs="+", type=float, default=[0.0, 2 / 3, 1.0],
                        help="Financing uptake among eligible corporate cafés")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "financing")
    args = parser.parse_args()

    data = Inputs.from_file()
    launches = get_launches(args.strategy)
    summaries, hq_rows, loan_rows, owner_rows = [], [], [], []
    for uptake in args.rates:
        result = run_financing(args.strategy, launches, data,
                               FinancingTerms(uptake=uptake))
        label = f"{uptake:.2%}"
        summaries.append({"scenario": label, **result.summary})
        hq_rows.extend({"scenario": label, **row} for row in result.hq_quarters)
        loan_rows.extend({"scenario": label, **row} for row in result.loan_schedule)
        owner_rows.extend({"scenario": label, **row} for row in result.owner_groups)
        s = result.summary
        print(f"{label:>8} | funded {s['financed_cafes']:>2}/{s['eligible_cafes']:<2}"
              f" | gross loans ${s['gross_loan_advances']:,.0f}"
              f" | HQ NPV ${s['financed_hq_npv_5y']:,.0f}"
              f" | delta ${s['hq_npv_change']:+,.0f}"
              f" | 3y gross spend ${s['hq_gross_spend_2027_2029']:,.0f}")

    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "summary.csv", summaries)
    write_csv(args.output / "hq_quarterly.csv", hq_rows)
    write_csv(args.output / "loan_schedule.csv", loan_rows)
    write_csv(args.output / "owner_cohorts.csv", owner_rows)
    (args.output / "assumptions.json").write_text(json.dumps({
        "strategy": args.strategy,
        "rates": args.rates,
        "loan_limits_cad": {"Downtown": 15000, "University": 12000, "Suburban": 15000},
        "min_signed_accounts": {"Downtown": 4, "University": 3, "Suburban": 4},
        "annual_simple_interest": 0.10,
        "quarterly_positive_contribution_sweep": 0.75,
        "first_operating_quarter_ramp": 0.50,
        "signed_account_eligibility": "Case midpoint proxy, not verified signed contracts",
        "hq_costs": "Original corporate HQ setup $40k and full $90k each year; unchanged",
        "cash_flow_treatment": "Principal is cash recovery, never sales or operating profit",
        "defaults": "No default assumption; arrears/outstanding balances tracked",
        "program_fee": "Off (Lever 3 separate)",
        "landlord_acquisition": "Off (Lever 2 separate)",
    }, indent=2), encoding="utf-8")
    print(f"Outputs: {args.output}")


if __name__ == "__main__":
    main()
