
"""Business Model Levers Analysis — Second Cup 2026.

Run from repository root:
    python business_model_levers.py

Case baseline inputs come from Appendix A5-A7.
All new fees, pricing changes, discounts and sales improvements
are hypothetical management interventions, NOT Case facts.

Both head-office and franchisee returns are recalculated.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from secondcup.inputs import Inputs, Overrides, load_rollouts
from secondcup.scenarios import get_launches
from secondcup.unit_economics import unit_economics
from secondcup.financial_engine import run_hq


# ==================================================
# 1. BUSINESS MODEL LEVER CONFIGURATION
# ==================================================

@dataclass(frozen=True)
class Lever:
    label: str
    strategy: str

    # Strategy B: additional program fee on corporate sales
    b_program_fee: float = 0.0
    fee_timing: str = "immediate"
    fee_incremental_only: bool = False

    # Strategy B: incremental business development
    extra_accounts_per_cafe: float = 0.0
    order_volume_uplift: float = 0.0
    acquisition_cost_per_new_account: float = 0.0

    # Strategy B: annual HQ coordination costs
    b_hq_costs_by_year: tuple[float, ...] | None = None

    # Strategy A: pricing and investment levers
    workspace_price_uplift: float = 0.0
    owner_capex_saving_pct: float = 0.0
    hq_owner_capex_subsidy_pct: float = 0.0
    extra_a_hq_cost_per_year: float = 0.0


# ==================================================
# 2. APPLY SCENARIO OVERRIDES
# ==================================================

def scenario_overrides(
    data: Inputs,
    launches: list,
    lever: Lever,
) -> Overrides:

    by_type: dict[str, dict[str, float]] = {}

    for launch in launches:

        if not launch.count:
            continue

        p = by_type.setdefault(launch.typ, {})

        # Strategy A: Paid Reservations
        if launch.option in (
            "Paid Reservations",
            "Operator Partnership",
        ):

            if lever.workspace_price_uplift:

                p["res_hour_price"] = (
                    data.get(launch.typ, "res_hour_price")
                    * (1 + lever.workspace_price_uplift)
                )

        # Strategy A: Memberships
        elif launch.option == "Memberships":

            if lever.workspace_price_uplift:

                p["member_month_price"] = (
                    data.get(launch.typ, "member_month_price")
                    * (1 + lever.workspace_price_uplift)
                )

        # Strategy B: Corporate Accounts
        elif launch.option == "Corporate Accounts":

            if lever.extra_accounts_per_cafe:

                base_accounts = (
                    data.get(launch.typ, "accounts_min")
                    + data.get(launch.typ, "accounts_max")
                ) / 2

                new_accounts = (
                    base_accounts
                    + lever.extra_accounts_per_cafe
                )

                p["accounts_min"] = new_accounts
                p["accounts_max"] = new_accounts

            if lever.order_volume_uplift:

                p["orders_per_week"] = (
                    data.get(launch.typ, "orders_per_week")
                    * (1 + lever.order_volume_uplift)
                )

    return Overrides(type_parameters=by_type)


# ==================================================
# 3. FRANCHISEE PROGRAM FEE AND PAYBACK
# ==================================================

def owner_fee_schedule(
    unit,
    original_capex: float,
    lever: Lever,
    data: Inputs,
    *,
    is_corporate: bool,
    incremental_fee_sales: float,
) -> tuple[list[float], float | None]:

    # Real investment savings for Strategy A
    capex_savings = (
        original_capex * lever.owner_capex_saving_pct
        if not is_corporate
        else 0.0
    )

    # HQ co-investment for Strategy A
    owner_subsidy = (
        original_capex * lever.hq_owner_capex_subsidy_pct
        if not is_corporate
        else 0.0
    )

    owner_cash_investment = (
        original_capex
        - capex_savings
        - owner_subsidy
    )

    fees = []

    base_contribution_so_far = 0.0
    owner_cash_so_far = 0.0

    payback = (
        0.0 if owner_cash_investment <= 0
        else None
    )

    # Evaluate 20 quarters = 5 years per franchisee
    for k in range(1, 21):

        contribution_q = (
            unit.annual_owner_contribution / 4
        )

        # Additional fee becomes payable either:
        # 1. Immediately
        # 2. After original investment is recovered

        fee_applies = (
            is_corporate
            and lever.b_program_fee > 0
            and (
                lever.fee_timing == "immediate"
                or (
                    base_contribution_so_far + 1e-8
                    >= original_capex
                )
            )
        )

        fee_q = (
            incremental_fee_sales
            * lever.b_program_fee / 4
            if fee_applies
            else 0.0
        )

        fees.append(fee_q)

        net_q = contribution_q - fee_q

        before = owner_cash_so_far
        owner_cash_so_far += net_q

        if (
            payback is None
            and net_q > 0
            and owner_cash_so_far >= owner_cash_investment
        ):

            fraction_of_quarter = (
                (owner_cash_investment - before)
                / net_q
            )

            payback = (
                (k - 1 + fraction_of_quarter) / 4
            )

        base_contribution_so_far += contribution_q

    return fees, payback


# ==================================================
# 4. EVALUATE FINANCIAL EFFECTS
# ==================================================

def evaluate(
    data: Inputs,
    lever: Lever,
) -> tuple[dict, list[dict]]:

    if lever.fee_timing not in (
        "immediate",
        "after_owner_payback",
    ):
        raise ValueError("Unsupported fee_timing")

    if lever.b_hq_costs_by_year is not None:

        if len(lever.b_hq_costs_by_year) != 5:
            raise ValueError(
                "B cost schedule must have five years"
            )

    for key in (
        "b_program_fee",
        "extra_accounts_per_cafe",
        "order_volume_uplift",
        "acquisition_cost_per_new_account",
        "workspace_price_uplift",
        "owner_capex_saving_pct",
        "hq_owner_capex_subsidy_pct",
        "extra_a_hq_cost_per_year",
    ):
        if getattr(lever, key) < 0:
            raise ValueError(
                f"{key} must be nonnegative"
            )

    if (
        lever.owner_capex_saving_pct
        + lever.hq_owner_capex_subsidy_pct
        > 1
    ):
        raise ValueError(
            "Owner investment reductions exceed 100%"
        )

    launches = get_launches(lever.strategy)

    overrides = scenario_overrides(
        data,
        launches,
        lever,
    )

    # Original financial model
    base = run_hq(
        lever.strategy,
        launches,
        data,
    )

    # Model with adjusted operating assumptions
    modified = run_hq(
        lever.strategy,
        launches,
        data,
        overrides,
    )

    hq_cash = modified.cashflows.copy()

    opts = {
        x.option
        for x in launches
        if x.count > 0
    }

    has_a = bool(
        opts & {
            "Paid Reservations",
            "Memberships",
            "Operator Partnership",
        }
    )

    has_b = "Corporate Accounts" in opts

    if (
        lever.b_hq_costs_by_year is not None
        and not has_b
    ):
        raise ValueError(
            "B cost schedule used without Corporate Accounts"
        )

    # ----------------------------------------------
    # 4.1 HQ fixed cost adjustments
    # ----------------------------------------------

    original_b_cost = (
        data.rule("corp_hq_annual")
        if has_b
        else 0.0
    )

    by_year = (
        lever.b_hq_costs_by_year
        or (original_b_cost,) * 5
    )

    for q in range(1, 21):

        yr = (q - 1) // 4

        # Additional HQ management costs for A
        if has_a:
            hq_cash[q] -= (
                lever.extra_a_hq_cost_per_year / 4
            )

        # Replace original B costs with phased costs
        if has_b:
            hq_cash[q] += (
                original_b_cost - by_year[yr]
            ) / 4

    # ----------------------------------------------
    # 4.2 Franchisee and transaction adjustments
    # ----------------------------------------------

    owner_npv_total = 0.0
    owner_failures = 0
    owner_rows = []

    owner_hq_capital_by_q = [0.0] * 20
    extra_hq_capex_by_q = [0.0] * 20

    rate = data.rule("discount")

    for launch in launches:

        if not launch.count:
            continue

        unit = unit_economics(
            data,
            launch.typ,
            launch.option,
            overrides,
        )

        is_corporate = (
            launch.option == "Corporate Accounts"
        )

        is_workspace = launch.option in (
            "Paid Reservations",
            "Memberships",
            "Operator Partnership",
        )

        # ------------------------------------------
        # A: renovation savings / HQ investment
        # ------------------------------------------

        saving = (
            unit.capex_owner
            * lever.owner_capex_saving_pct
            if is_workspace else 0.0
        )

        subsidy = (
            unit.capex_owner
            * lever.hq_owner_capex_subsidy_pct
            if is_workspace else 0.0
        )

        if subsidy:

            hq_cash[launch.quarter] -= (
                launch.count * subsidy
            )

            owner_hq_capital_by_q[launch.quarter] += (
                launch.count * subsidy
            )

        # ------------------------------------------
        # B: acquisition costs for new accounts
        # ------------------------------------------

        acquisition_cost = (
            lever.extra_accounts_per_cafe
            * lever.acquisition_cost_per_new_account
            if is_corporate else 0.0
        )

        if acquisition_cost:

            hq_cash[launch.quarter] -= (
                launch.count * acquisition_cost
            )

            extra_hq_capex_by_q[launch.quarter] += (
                launch.count * acquisition_cost
            )

        # ------------------------------------------
        # B: incremental-account fee calculation
        # ------------------------------------------

        new_account_sales = (
            lever.extra_accounts_per_cafe
            * overrides.get(
                data, launch.typ, "orders_per_week"
            )
            * data.get(
                launch.typ, "cups_per_order"
            )
            * data.get(
                launch.typ, "weeks_year"
            )
            * data.get(
                launch.typ, "cup_price"
            )
        ) if is_corporate else 0.0

        fee_base = (
            new_account_sales
            if lever.fee_incremental_only
            else unit.annual_sales_delta
        )

        fees, payback = owner_fee_schedule(
            unit,
            unit.capex_owner,
            lever,
            data,
            is_corporate=is_corporate,
            incremental_fee_sales=fee_base,
        )

        # ------------------------------------------
        # Franchisee five-year NPV
        # ------------------------------------------

        # Original model discounts annual owner cash.
        # Additional fees are therefore aggregated by
        # operating year before discounting.

        fee_pv = 0.0

        for yr in range(5):

            annual_fee = sum(
                fees[4 * yr: 4 * (yr + 1)]
            )

            fee_pv += (
                annual_fee / (1 + rate) ** (yr + 1)
            )

        owner_npv_per_cafe = (
            unit.owner_npv_5y
            + saving
            + subsidy
            - fee_pv
        )

        owner_npv_total += (
            owner_npv_per_cafe * launch.count
        )

        if (
            payback is None
            or payback
            > data.rule("owner_payback_years") + 1e-8
        ):
            owner_failures += launch.count

        # ------------------------------------------
        # HQ receives additional program fees
        # ------------------------------------------

        for k, fee in enumerate(
            fees,
            start=1,
        ):

            global_q = launch.quarter + k

            if global_q <= 20:

                hq_cash[global_q] += (
                    launch.count * fee
                )

        owner_rows.append({
            "scenario": lever.label,
            "type": launch.typ,
            "option": launch.option,
            "launch_q": launch.quarter,
            "cafes": launch.count,

            "annual_sales_per_cafe": round(
                unit.annual_sales_delta, 2
            ),

            "annual_owner_contrib_before_new_fee": round(
                unit.annual_owner_contribution, 2
            ),

            "owner_npv_5y_per_cafe": round(
                owner_npv_per_cafe, 2
            ),

            "owner_payback_years": (
                ""
                if payback is None
                else round(payback, 3)
            ),

            "total_5yr_program_fees_per_cafe": round(
                sum(fees), 2
            ),
        })

    # ----------------------------------------------
    # 4.3 HQ NPV
    # ----------------------------------------------

    hq_npv = sum(
        cash / (1 + rate) ** (q / 4)
        for q, cash in enumerate(hq_cash)
    )

    cumulative = 0.0
    payback_hq = None
    y4_cash = 0.0

    for q, cash in enumerate(hq_cash):

        cumulative += cash

        if q == 16:
            y4_cash = cumulative

        if (
            payback_hq is None
            and cumulative >= 0
            and q > 0
        ):
            payback_hq = q / 4

    # ----------------------------------------------
    # 4.4 HQ budget constraints
    # ----------------------------------------------

    year1_spend = (
        base.hq_spend_year1
        + (
            lever.extra_a_hq_cost_per_year
            if has_a else 0
        )
        + (
            by_year[0] - original_b_cost
            if has_b else 0
        )
        + sum(owner_hq_capital_by_q[:4])
        + sum(extra_hq_capex_by_q[:4])
    )

    three_year_spend = (
        base.hq_spend_first_3y
        + (
            3 * lever.extra_a_hq_cost_per_year
            if has_a else 0
        )
        + (
            sum(by_year[:3]) - 3 * original_b_cost
            if has_b else 0
        )
        + sum(owner_hq_capital_by_q[:12])
        + sum(extra_hq_capex_by_q[:12])
    )

    budget_ok = (
        year1_spend
        <= data.rule("year1_budget") + 1e-8
        and three_year_spend
        <= data.rule("budget_total") + 1e-8
    )

    # ----------------------------------------------
    # 4.5 Return results
    # ----------------------------------------------

    result = {

        "scenario": lever.label,

        "strategy": lever.strategy,

        "cafes": base.launched_cafes,

        "hq_npv_5y": round(
            hq_npv, 2
        ),

        "hq_npv_change_vs_base": round(
            hq_npv - base.npv_5y, 2
        ),

        "hq_cash_year4": round(
            y4_cash, 2
        ),

        "hq_payback_years": (
            ""
            if payback_hq is None
            else payback_hq
        ),

        "owner_avg_npv_5y": round(
            owner_npv_total / base.launched_cafes, 2
        ),

        "owner_failures_3yr": owner_failures,

        "hq_budget_met": budget_ok,

        "hq_four_year_met": (
            y4_cash >= -1e-8
        ),

        "all_targets_met": (
            base.feasible
            and budget_ok
            and y4_cash >= -1e-8
            and hq_npv >= 0
            and owner_failures == 0
        ),
    }

    return result, owner_rows


# ==================================================
# 5. DEFINE BUSINESS MODEL SCENARIOS
# ==================================================

def scenarios() -> list[Lever]:

    available = load_rollouts()

    hybrid = (
        "Hybrid - Optimized"
        if "Hybrid - Optimized" in available
        else "Hybrid"
    )

    return [

        # ------------------------------------------
        # Strategy A
        # ------------------------------------------

        Lever(
            "A | Strict Case",
            "A Only",
        ),

        Lever(
            "A | +10% workspace price (same demand)",
            "A Only",
            workspace_price_uplift=0.10,
        ),

        Lever(
            "A | -15% renovation cost",
            "A Only",
            owner_capex_saving_pct=0.15,
        ),

        Lever(
            "A | HQ subsidizes 20% capex",
            "A Only",
            hq_owner_capex_subsidy_pct=0.20,
        ),

        Lever(
            "A | HQ overhead +$20k/year",
            "A Only",
            extra_a_hq_cost_per_year=20_000,
        ),

        # ------------------------------------------
        # Strategy B
        # ------------------------------------------

        Lever(
            "B | Strict Case",
            "B Only",
        ),

        Lever(
            "B | 5% fee from launch",
            "B Only",
            b_program_fee=0.05,
        ),

        Lever(
            "B | 5% fee after owner payback",
            "B Only",
            b_program_fee=0.05,
            fee_timing="after_owner_payback",
        ),

        Lever(
            "B | +1 new account + 3% incremental fee",
            "B Only",
            extra_accounts_per_cafe=1.0,
            b_program_fee=0.03,
            fee_incremental_only=True,
            acquisition_cost_per_new_account=500,
        ),

        Lever(
            "B | +10% recurring-order volume",
            "B Only",
            order_volume_uplift=0.10,
        ),

        Lever(
            "B | Phased HQ costs (45/60/90k)",
            "B Only",
            b_hq_costs_by_year=(
                45_000,
                60_000,
                90_000,
                90_000,
                90_000,
            ),
        ),

        # ------------------------------------------
        # Hybrid
        # ------------------------------------------

        Lever(
            "Hybrid | Strict Case",
            hybrid,
        ),

        Lever(
            "Hybrid | B +5% post-payback fee",
            hybrid,
            b_program_fee=0.05,
            fee_timing="after_owner_payback",
        ),
    ]


# ==================================================
# 6. EXPORT RESULTS
# ==================================================

def write_csv(
    path: Path,
    rows: list[dict],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0]),
        )

        writer.writeheader()
        writer.writerows(rows)


# ==================================================
# 7. MAIN
# ==================================================

def main() -> None:

    data = Inputs.from_file()

    all_rows = []
    all_owners = []

    for lever in scenarios():

        result, owners = evaluate(
            data,
            lever,
        )

        all_rows.append(result)
        all_owners.extend(owners)

    print(
        "\n=== BUSINESS MODEL LEVERS | "
        "HQ and FRANCHISEES ==="
    )

    print(
        f"{'Scenario':<47} "
        f"{'HQ NPV':>11} "
        f"{'Delta HQ':>11} "
        f"{'Owner avg NPV':>15} "
        f"{'Owner fail':>10}"
    )

    print("-" * 101)

    for r in all_rows:

        print(
            f"{r['scenario']:<47} "
            f"{r['hq_npv_5y']:>11,.0f} "
            f"{r['hq_npv_change_vs_base']:>+11,.0f} "
            f"{r['owner_avg_npv_5y']:>15,.0f} "
            f"{r['owner_failures_3yr']:>10}"
        )

    output = ROOT / "outputs"

    write_csv(
        output / "business_model_levers.csv",
        all_rows,
    )

    write_csv(
        output / "business_model_levers_owners.csv",
        all_owners,
    )

    print(f"\nSaved results to {output}")

    print(
        "DISCLAIMER: New fees, discounts, volume gains "
        "and cost stages are hypothetical."
    )

    print(
        "Owner NPVs use 5 years from store launch; "
        "HQ NPV uses the 2027-2031 program."
    )


if __name__ == "__main__":
    main()
