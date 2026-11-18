
"""Cost Structure Sensitivity Analysis for Second Cup.

Compare:
1. Strategy A: additional annual HQ management cost.
2. Strategy B: phased HQ sales coordination spending.

Original Case revenue, store economics, and rollout timing
remain unchanged.

Run from project root:
    python risk_scenarios.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from secondcup.inputs import Inputs
from secondcup.scenarios import get_launches
from secondcup.financial_engine import run_hq


# --------------------------------------------------
# 1. Scenario assumptions
# --------------------------------------------------

# Additional HQ management cost for Strategy A.
# These are NEW assumptions, not Case data.

A_ANNUAL_HQ_OVERHEAD = (
    0,
    10_000,
    20_000,
    30_000,
)


# Strategy B HQ annual sales coordination costs.
# Five numbers correspond to 2027-2031.
# The staged schedules REPLACE the Case's $90k/year.

B_HQ_COST_SCHEDULES = {
    "Case B - Flat 90k": (
        90_000, 90_000, 90_000, 90_000, 90_000
    ),
    "B - First Year Half": (
        45_000, 90_000, 90_000, 90_000, 90_000
    ),
    "B - Two Year Phasing": (
        45_000, 60_000, 90_000, 90_000, 90_000
    ),
}


# --------------------------------------------------
# 2. Calculate adjusted HQ cash flows
# --------------------------------------------------

def cost_scenario(
    data: Inputs,
    strategy: str,
    *,
    extra_a_hq_annual: float = 0,
    b_annual_costs: tuple[float, ...] | None = None,
    label: str,
) -> dict:

    if extra_a_hq_annual < 0:
        raise ValueError("A HQ overhead must be nonnegative")

    if b_annual_costs is not None:
        if len(b_annual_costs) != 5:
            raise ValueError("B requires five annual costs")
        if any(value < 0 for value in b_annual_costs):
            raise ValueError("B costs must be nonnegative")

    launches = get_launches(strategy)

    # Original financial result
    result = run_hq(
        strategy,
        launches,
        data,
    )

    options = {
        launch.option
        for launch in launches
        if launch.count > 0
    }

    has_a = bool(
        options & {
            "Paid Reservations",
            "Memberships",
            "Operator Partnership",
        }
    )

    has_b = "Corporate Accounts" in options

    if extra_a_hq_annual and not has_a:
        raise ValueError("This strategy has no A business")

    if b_annual_costs is not None and not has_b:
        raise ValueError("This strategy has no B business")

    case_b_cost = (
        data.rule("corp_hq_annual") if has_b else 0.0
    )

    b_costs = (
        b_annual_costs
        if b_annual_costs is not None
        else (case_b_cost,) * 5
    )

    # Copy original quarterly cash flows.
    # Do not overwrite the original model.

    adjusted = result.cashflows.copy()

    for q in range(1, 21):

        year_index = (q - 1) // 4

        # A: subtract extra HQ management cost
        if has_a:
            adjusted[q] -= extra_a_hq_annual / 4.0

        # B: replace original $90k annual cost
        # with the selected phased cost.

        if has_b:
            cost_difference = (
                case_b_cost - b_costs[year_index]
            )

            adjusted[q] += cost_difference / 4.0

    # --------------------------------------------------
    # 3. Recalculate HQ NPV
    # --------------------------------------------------

    discount = data.rule("discount")

    npv = sum(
        cash / (1 + discount) ** (q / 4)
        for q, cash in enumerate(adjusted)
    )

    # --------------------------------------------------
    # 4. Recalculate simple payback
    # --------------------------------------------------

    cumulative = 0.0
    payback = None
    cash_at_year4 = 0.0

    for q, cash in enumerate(adjusted):

        cumulative += cash

        if q == 16:
            cash_at_year4 = cumulative

        if payback is None and cumulative >= 0:
            payback = q / 4.0

    # --------------------------------------------------
    # 5. Recalculate HQ budget utilization
    # --------------------------------------------------

    year1_spend = result.hq_spend_year1
    first3_spend = result.hq_spend_first_3y

    if has_a:
        year1_spend += extra_a_hq_annual
        first3_spend += 3 * extra_a_hq_annual

    if has_b:
        year1_spend += b_costs[0] - case_b_cost

        first3_spend += (
            sum(b_costs[:3]) - 3 * case_b_cost
        )

    budget_ok = (
        year1_spend <= data.rule("year1_budget")
        and first3_spend <= data.rule("budget_total")
    )

    return {
        "strategy": strategy,
        "scenario": label,

        "five_year_hq_npv": round(npv, 2),

        "npv_change_from_case": round(
            npv - result.npv_5y, 2
        ),

        "simple_payback_years": (
            payback if payback is not None
            else "Not reached"
        ),

        "cash_at_year4": round(
            cash_at_year4, 2
        ),

        "four_year_cash_target_met": (
            cash_at_year4 >= -1e-6
        ),

        "year1_hq_spend": round(
            year1_spend, 2
        ),

        "first3years_hq_spend": round(
            first3_spend, 2
        ),

        "hq_budget_met": budget_ok,

        "owner_failing_3yr":
            result.owner_failing_3yr,
    }


# --------------------------------------------------
# 6. Run all scenarios
# --------------------------------------------------

def main():

    data = Inputs.from_file()
    rows = []

    # Strategy A scenarios
    for overhead in A_ANNUAL_HQ_OVERHEAD:

        rows.append(
            cost_scenario(
                data,
                "A Only",
                extra_a_hq_annual=overhead,
                label=f"A Extra HQ Cost ${overhead:,}/yr",
            )
        )

    # Strategy B scenarios
    for label, schedule in B_HQ_COST_SCHEDULES.items():

        rows.append(
            cost_scenario(
                data,
                "B Only",
                b_annual_costs=schedule,
                label=label,
            )
        )

    # --------------------------------------------------
    # 7. Print results
    # --------------------------------------------------

    print("\n=== COST STRUCTURE ANALYSIS ===\n")

    for row in rows:

        print(f"Scenario: {row['scenario']}")
        print(
            f"  HQ NPV: "
            f"${row['five_year_hq_npv']:,.0f}"
        )
        print(
            f"  NPV Change: "
            f"${row['npv_change_from_case']:+,.0f}"
        )
        print(
            f"  Payback: "
            f"{row['simple_payback_years']} years"
        )
        print(
            f"  Year-4 Cash: "
            f"${row['cash_at_year4']:,.0f}"
        )
        print(
            f"  Four-Year Target Met: "
            f"{row['four_year_cash_target_met']}"
        )
        print(
            f"  HQ Budget Met: "
            f"{row['hq_budget_met']}"
        )
        print()

    # --------------------------------------------------
    # 8. Export CSV
    # --------------------------------------------------

    output = ROOT / "outputs"
    output.mkdir(exist_ok=True)

    file_path = output / "cost_structure_scenarios.csv"

    with file_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"Results saved to: {file_path}")


if __name__ == "__main__":
    main()
