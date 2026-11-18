
"""Network head-office cash flows built from Appendix A5-A7 unit economics.

Cash-flow conventions (explicit modelling assumptions):
- q=0 is the start of 2027 Q1; q=1..20 are subsequent quarter-ends.
- HQ platform/setup cost is paid at q=0 for any option used in the plan.
- HQ recurring cost accrues at each quarter-end, q=1..20.
- A cafe launched in quarter q earns its first HQ royalty at q+1.
- Headquarters is evaluated over one five-year program horizon (2027-2031).
- Franchisee NPV is separately evaluated for five years from each cafe's launch.
- No additional 5% program fee, loan advances or 10% loan interest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .inputs import Inputs, Overrides
from .scenarios import Launch, validate_launches
from .unit_economics import unit_economics


SAAS_OPTIONS = {"Paid Reservations", "Memberships"}


@dataclass
class HQResult:
    name: str

    cashflows: list[float]

    npv_5y: float
    cumulative_cash_5y: float
    payback_years: float | None

    cash_at_year4: float

    hq_spend_year1: float
    hq_spend_first_3y: float

    owner_weighted_npv: float | None
    owner_failing_3yr: int

    launched_cafes: int

    feasible: bool
    warnings: list[str]

    hq_payback_target_met: bool
    owner_payback_target_met: bool


def fixed_hq_costs(
    launches: Sequence[Launch],
    data: Inputs,
    *,
    technology: str = "licensed",
) -> tuple[float, float]:
    """Calculate HQ fixed costs.

    Returns:
        setup: One-time HQ investment
        annual: Annual HQ operating expenses

    Costs come from Case Appendix A7.

    If both SaaS and Operator Partnership are used,
    both setup costs are included.
    """

    if technology not in ("licensed", "custom"):
        raise ValueError(
            "technology must be 'licensed' or 'custom'"
        )

    options = {
        launch.option
        for launch in launches
        if launch.count > 0
    }

    setup = 0.0
    annual = 0.0

    # Strategy A: Paid Reservations / Memberships
    if options & SAAS_OPTIONS:

        if technology == "licensed":
            setup += data.rule("licensed_hq_setup")

        else:
            setup += data.rule("custom_hq_setup")
            annual += data.rule("custom_hq_annual")

    # Strategy A: Operator Partnership
    if "Operator Partnership" in options:
        setup += data.rule("partner_hq_setup")

    # Strategy B: Corporate Accounts
    if "Corporate Accounts" in options:
        setup += data.rule("corp_hq_setup")
        annual += data.rule("corp_hq_annual")

    # Strategy B: Late-day Offer
    if "Late-day Offer" in options:
        setup += data.rule("late_hq_setup")
        annual += data.rule("late_hq_annual")

    return setup, annual


def run_hq(
    name: str,
    launches: Sequence[Launch],
    data: Inputs,
    over: Overrides | None = None,
    *,
    technology: str = "licensed",
    first_quarter_ramp: float = 1.0,
    check_pilot: bool = True,
) -> HQResult:
    """Calculate HQ financial returns for a deployment strategy.

    Inputs:
        name: Scenario name
        launches: Quarterly cafe rollout plan
        data: Original Case inputs
        over: Optional assumption overrides
        technology: licensed or custom
        first_quarter_ramp: First active quarter revenue factor
        check_pilot: Validate pilot observation period

    Outputs:
        HQ quarterly cash flows
        Five-year NPV
        Simple payback period
        HQ capital spending
        Franchisee NPV and payback diagnostics
    """

    if not 0.0 <= first_quarter_ramp <= 1.0:
        raise ValueError(
            "first_quarter_ramp must be between 0 and 1"
        )

    over = over or Overrides()

    # 1. Validate rollout constraints
    errors = validate_launches(
        launches,
        data,
        check_pilot=check_pilot,
    )

    # 2. Calculate HQ fixed costs
    setup, annual_cost = fixed_hq_costs(
        launches,
        data,
        technology=technology,
    )

    # 3. Initialize 21 cash-flow points (q0 to q20)
    # q0 = initial investment
    # q1-q20 = quarterly operating cash flows
    cashflows = [-setup] + [
        -annual_cost / 4.0
        for _ in range(20)
    ]

    cafes = 0
    owner_npv_total = 0.0
    owner_failing = 0

    # 4. Add each group of cafes
    for launch in launches:

        if launch.count <= 0:
            continue

        if not 0 <= launch.quarter < 20:
            continue

        # Calculate annual unit economics
        unit = unit_economics(
            data,
            launch.typ,
            launch.option,
            over,
            technology=technology,
        )

        cafes += launch.count

        # Aggregate franchisee five-year NPV
        owner_npv_total += (
            unit.owner_npv_5y * launch.count
        )

        # Check franchisee three-year payback
        if (
            unit.owner_simple_payback is None
            or unit.owner_simple_payback
            > data.rule("owner_payback_years")
        ):
            owner_failing += launch.count

        # 5. Add HQ royalty revenue by quarter
        for q in range(launch.quarter + 1, 21):

            if q == launch.quarter + 1:
                ramp = first_quarter_ramp
            else:
                ramp = 1.0

            quarterly_royalty = (
                launch.count
                * ramp
                * unit.annual_hq_royalty
                / 4.0
            )

            cashflows[q] += quarterly_royalty

    # 6. Calculate five-year HQ NPV
    discount = over.rule(data, "discount")

    if discount <= -1:
        raise ValueError(
            "Discount rate must be greater than -100%"
        )

    npv = sum(
        cash / (1.0 + discount) ** (q / 4.0)
        for q, cash in enumerate(cashflows)
    )

    # 7. Calculate cumulative cash flow and simple payback
    running = 0.0
    payback = None
    cash_at_year4 = 0.0

    for q, cash in enumerate(cashflows):

        running += cash

        if q == 16:
            cash_at_year4 = running

        if (
            cafes > 0
            and payback is None
            and running >= 0
        ):
            payback = q / 4.0

    # 8. Check HQ capital budget
    # Case budget covers 2027-2029.
    # Franchisee-funded capex is NOT HQ spending.
    spend_year1 = setup + annual_cost

    spend_first_3y = (
        setup + 3.0 * annual_cost
    )

    if spend_year1 > data.rule("year1_budget") + 1e-6:
        errors.append(
            "Year-1 head-office budget exceeded"
        )

    if (
        spend_first_3y
        > data.rule("budget_total") + 1e-6
    ):
        errors.append(
            "2027-2029 head-office budget exceeded"
        )

    # 9. Evaluate financial return targets
    hq_target = (
        payback is not None
        and payback <= data.rule("hq_payback_years")
    )

    owner_target = (
        cafes > 0
        and owner_failing == 0
    )

    warnings = list(errors)

    if cafes and not hq_target:
        warnings.append(
            "HQ fails the four-year simple-payback target"
        )

    if owner_failing:
        warnings.append(
            f"{owner_failing} cafes fail the owner "
            "three-year payback expectation"
        )

    if not cafes:
        warnings.append(
            "No participating cafes"
        )

    # 10. Return financial result
    return HQResult(
        name=name,
        cashflows=cashflows,
        npv_5y=npv,
        cumulative_cash_5y=running,
        payback_years=payback,
        cash_at_year4=cash_at_year4,
        hq_spend_year1=spend_year1,
        hq_spend_first_3y=spend_first_3y,
        owner_weighted_npv=(
            owner_npv_total / cafes
            if cafes else None
        ),
        owner_failing_3yr=owner_failing,
        launched_cafes=cafes,
        feasible=not errors,
        warnings=warnings,
        hq_payback_target_met=hq_target,
        owner_payback_target_met=owner_target,
    )
