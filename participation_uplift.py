"""Franchise participation sensitivity for HQ Financing, with Case A8 guardrails."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from secondcup.inputs import Inputs
from secondcup.scenarios import get_launches
from secondcup.participation_uplift import ParticipationTerms, run_participation_uplift


def save(path, records):
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def main():
    p = argparse.ArgumentParser(description="Financing-led franchisee participation uplift")
    p.add_argument("--interest-conversion", type=float, default=1.0,
                   help="Share of 20 informally interested cafés assumed to consent")
    p.add_argument("--financing-conversion", type=float, default=2 / 3,
                   help="Share of remaining candidate cafes who join because of financing")
    p.add_argument("--loan-uptake", type=float, default=1.0,
                   help="Share of incremental converts using HQ loan")
    p.add_argument("--output", type=Path, default=ROOT / "outputs" / "participation")
    args = p.parse_args()
    data = Inputs.from_file()
    terms = ParticipationTerms(args.interest_conversion, args.financing_conversion,
                               args.loan_uptake)
    result = run_participation_uplift("B Only", get_launches("B Only"), data, terms)
    s = result["summary"]
    print(f"Informally interested: {s['informally_interested_cafes']} (NOT CONSENT)")
    print(f"Assumed no-financing consent: {s['baseline_assumed_participants']}")
    print(f"Financing-unlocked stores: {s['financing_unlocked_cafes']}")
    print(f"Total with financing: {s['assumed_participants_with_financing']}")
    for key in ("incremental_store_annual_sales_at_steady_state",
                "incremental_hq_annual_royalty_at_steady_state",
                "hq_npv_without_financing_or_uplift",
                "hq_npv_with_financing_and_uplift",
                "incremental_hq_royalty_npv_from_new_participants",
                "financing_net_cash_npv", "total_hq_npv_gain_vs_baseline",
                "gross_loan_advances", "hq_gross_spend_2027_2029"):
        print(f"{key}: ${s[key]:,.2f}")
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    save(out / "by_type.csv", result["by_type"])
    save(out / "hq_quarterly.csv", result["hq_quarters"])
    save(out / "loan_schedule.csv", result["loans"])
    for name, key in (("baseline", "baseline_launches"),
                      ("financing", "assisted_launches")):
        save(out / f"{name}_rollout.csv", [
            {"type": x.typ, "option": x.option, "quarter": x.quarter,
             "cafes": x.count} for x in result[key]])
    sensitivity = []
    for interested in (0.0, 0.5, 1.0):
        for conversion in (0.0, 0.25, 0.50, 2 / 3, 1.0):
            r = run_participation_uplift(
                "B Only", get_launches("B Only"), data,
                ParticipationTerms(interested, conversion, args.loan_uptake))
            sensitivity.append({"interest_to_consent": interested,
                                "additional_financing_conversion": conversion,
                                **r["summary"]})
    save(out / "conversion_sensitivity.csv", sensitivity)
    print(f"Outputs: {out}")


if __name__ == "__main__":
    main()
