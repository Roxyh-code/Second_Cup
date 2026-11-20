"""Run switchable Lever 2, optionally integrated with Lever 1."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from secondcup.hq_financing import FinancingTerms
from secondcup.landlord_acquisition import LandlordTerms, run_landlord
from secondcup.inputs import Inputs, load_rollouts
from secondcup.scenarios import get_launches


def save(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description="Landlord-led corporate accounts")
    p.add_argument("--strategy", choices=load_rollouts(), default="B Only")
    p.add_argument("--with-financing", action="store_true")
    p.add_argument("--financing-uptake", type=float, default=2 / 3)
    p.add_argument("--partners", nargs=3, type=float, default=[12, 8, 20],
                   metavar=("DOWNTOWN", "UNIVERSITY", "SUBURBAN"))
    p.add_argument("--introductions", type=float, default=6)
    p.add_argument("--conversion", type=float, default=0.5)
    p.add_argument("--cac", type=float, default=500)
    p.add_argument("--extra-hq-setup", type=float, default=0,
                   help="Additional one-time landlord program cost, beyond Case $40k setup")
    p.add_argument("--extra-hq-annual", type=float, default=0,
                   help="Additional annual landlord management cost, beyond mandatory Case $90k/year")
    p.add_argument("--output", type=Path, default=None)
    args = p.parse_args()
    terms = LandlordTerms(
        partners_by_type=dict(zip(("Downtown", "University", "Suburban"), args.partners)),
        tenant_introductions_per_partner=args.introductions,
        signed_conversion_rate=args.conversion,
        acquisition_cost_per_signed_account=args.cac,
        additional_hq_setup_cost=args.extra_hq_setup,
        additional_hq_annual_cost=args.extra_hq_annual)
    result = run_landlord(args.strategy, get_launches(args.strategy),
                          Inputs.from_file(), terms,
                          financing=FinancingTerms(uptake=args.financing_uptake)
                          if args.with_financing else None)
    folder = args.output or ROOT / "outputs" / "landlord" / (
        "with_financing" if args.with_financing else "standalone")
    folder.mkdir(parents=True, exist_ok=True)
    save(folder / "hq_quarterly.csv", result.hq_quarters)
    save(folder / "acquisition_cohorts.csv", result.acquisition_cohorts)
    save(folder / "owner_cohorts.csv", result.owner_cohorts)
    save(folder / "loan_schedule.csv", result.loan_schedule)
    (folder / "summary.json").write_text(
        json.dumps(result.summary, indent=2), encoding="utf-8")
    (folder / "assumptions.json").write_text(json.dumps({
        "partner_counts": dict(terms.partners_by_type),
        "introductions": args.introductions, "conversion": args.conversion,
        "cac": args.cac,
        "extra_hq_setup": args.extra_hq_setup,
        "extra_hq_annual": args.extra_hq_annual,
        "financing_uptake": args.financing_uptake
        if args.with_financing else 0,
        "status": "Hypothetical planning inputs, not Case observations",
        "coordination_expense": "Full $90k every year, no portal setup"},
        indent=2), encoding="utf-8")
    for key, value in result.summary.items():
        print(f"{key}: {value}")
    print(f"Outputs: {folder}")


if __name__ == "__main__":
    main()
