"""Evaluate the full 2^3 combination matrix for Second Cup L1/L2/L3."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
from pathlib import Path

from lever3_deferred_fee import ROOT, write_csv
from secondcup.deferred_program_fee import DeferredFeeTerms, run_deferred_fee
from secondcup.hq_financing import FinancingTerms
from secondcup.landlord_acquisition import LandlordTerms
from secondcup.inputs import Inputs, load_rollouts
from secondcup.scenarios import get_launches


def run_grid(strategy, data, launches, *,
             fee_rate=.05, fee_base="all_corporate",
             fee_start_mode="after_operating_payback",
             financing_uptake=2 / 3,
             landlord_setup=5000.0, landlord_annual=10000.0,
             landlord_cac=500.0, partners=(12, 8, 20),
             introductions=6.0, conversion=.5):
    rows, quarters, fees, owners = [], [], [], []
    for l1, l2, l3 in itertools.product((False, True), repeat=3):
        name = f"L1{int(l1)}_L2{int(l2)}_L3{int(l3)}"
        finance = FinancingTerms(uptake=financing_uptake) if l1 else None
        landlord = (LandlordTerms(
            partners_by_type=dict(zip(("Downtown", "University", "Suburban"), partners)),
            tenant_introductions_per_partner=introductions,
            signed_conversion_rate=conversion,
            acquisition_cost_per_signed_account=landlord_cac,
            additional_hq_setup_cost=landlord_setup,
            additional_hq_annual_cost=landlord_annual,
        ) if l2 else None)
        fee = DeferredFeeTerms(
            rate=fee_rate if l3 else 0.0,
            fee_base=fee_base, start_mode=fee_start_mode)
        r = run_deferred_fee(strategy, launches, data, fee,
                             financing=finance, landlord=landlord)
        rows.append({"scenario": name, "L1": l1, "L2": l2, "L3": l3, **r.summary})
        quarters.extend({"scenario": name, **x} for x in r.hq_quarters)
        fees.extend({"scenario": name, **x} for x in r.fee_schedule)
        owners.extend({"scenario": name, **x} for x in r.owner_cohorts)
    return rows, quarters, fees, owners


def main():
    p = argparse.ArgumentParser(description="All 8 HQ/landlord/deferred-fee combinations")
    p.add_argument("--strategy", choices=load_rollouts(), default="B Only")
    p.add_argument("--fee-rate", type=float, default=.05)
    p.add_argument("--fee-base", choices=("all_corporate", "landlord_incremental"),
                   default="all_corporate")
    p.add_argument("--fee-start-mode", choices=(
        "after_operating_payback", "after_operating_and_loan_payoff", "immediate"),
        default="after_operating_payback")
    p.add_argument("--financing-uptake", type=float, default=2 / 3)
    p.add_argument("--landlord-setup", type=float, default=5000)
    p.add_argument("--landlord-annual", type=float, default=10000)
    p.add_argument("--landlord-cac", type=float, default=500)
    p.add_argument("--partners", nargs=3, type=float, default=[12, 8, 20])
    p.add_argument("--introductions", type=float, default=6)
    p.add_argument("--conversion", type=float, default=.5)
    p.add_argument("--output", type=Path, default=ROOT / "outputs" / "integrated")
    args = p.parse_args()
    data = Inputs.from_file()
    inputs = vars(args).copy()
    strategy = inputs.pop("strategy")
    output = inputs.pop("output")
    fee_start_mode = inputs.pop("fee_start_mode")
    rows, quarters, fees, owners = run_grid(
        strategy, data, get_launches(strategy),
        fee_start_mode=fee_start_mode, **inputs)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "summary.csv", rows)
    write_csv(output / "hq_quarterly.csv", quarters)
    write_csv(output / "fee_schedule.csv", fees)
    write_csv(output / "owner_cohorts.csv", owners)
    (output / "assumptions.json").write_text(
        json.dumps({"strategy": strategy, "fee_start_mode": fee_start_mode,
                    **inputs, "status": "Hypothetical intervention inputs"},
                   indent=2), encoding="utf-8")
    print(f"{'Levers':16} {'HQ NPV':>13} {'Fee by 2031':>14} {'Owner NPV':>15}"
          f" {'Gross spend 3y':>17} {'HQ 4y':>7} {'Owner fail':>11}")
    for x in rows:
        print(f"{x['scenario']:16} ${x['hq_npv_5y']:12,.0f} "
              f"${x['hq_fee_received_by_2031']:13,.0f} "
              f"${x['owner_npv_after_fee_total']:14,.0f} "
              f"${x['hq_gross_spend_2027_2029']:16,.0f} "
              f"{str(x['hq_four_year_target_met']):>7} "
              f"{x['owner_failing_3yr_after_fee']:>11}")
    print(f"Outputs: {output}")


if __name__ == "__main__":
    main()
