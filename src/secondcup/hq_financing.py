"""Lever 1: repayable HQ financing layered over the existing Second Cup model.

No baseline inputs, rollout plans, royalties or HQ fixed costs are modified.
A loan is a cash outflow followed by principal/interest cash receipts, NOT sales.
Store economics are evaluated for 20 quarters from each store's launch; HQ
cash flows cover only the common 2027-2031 (q0-q20) program horizon.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Mapping, Sequence

from .financial_engine import HQResult, run_hq
from .inputs import Inputs, Overrides, midpoint
from .scenarios import Launch, validate_launches
from .unit_economics import unit_economics

LOAN_LIMITS = {"Downtown": 15_000.0, "University": 12_000.0, "Suburban": 15_000.0}
MIN_SIGNED_ACCOUNTS = {"Downtown": 4, "University": 3, "Suburban": 4}
PROGRAM_END_Q = 20
OWNER_HORIZON_Q = 20


@dataclass(frozen=True)
class FinancingTerms:
    uptake: float = 2 / 3
    annual_interest: float = 0.10
    contribution_sweep: float = 0.75
    first_quarter_ramp: float = 0.50
    # Explicit signed counts take precedence. Case midpoints are planning proxies,
    # not proof of signed contracts; use real signed counts before live financing.
    signed_accounts_by_type: Mapping[str, float] | None = None

    def validate(self) -> None:
        for name in ("uptake", "contribution_sweep", "first_quarter_ramp"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.annual_interest < 0:
            raise ValueError("annual_interest must be nonnegative")
        if self.signed_accounts_by_type is not None:
            for typ, signed in self.signed_accounts_by_type.items():
                if typ not in MIN_SIGNED_ACCOUNTS or signed < 0:
                    raise ValueError(f"Invalid signed account input: {typ}={signed}")


@dataclass
class FinancingResult:
    strategy: str
    terms: FinancingTerms
    baseline: HQResult
    summary: dict
    hq_quarters: list[dict]
    loan_schedule: list[dict]
    owner_groups: list[dict]


def _financed_counts(launches: Sequence[Launch], data: Inputs,
                     over: Overrides, terms: FinancingTerms) -> dict[str, int]:
    """Hamilton apportionment of integer loans by store type, then earliest cohorts.

    Eligibility is checked before allocating loans. An explicit signed-account
    value is preferred; a Case midpoint is used only as a labelled proxy.
    """
    counts = {typ: 0 for typ in LOAN_LIMITS}
    for cohort in launches:
        if cohort.option != "Corporate Accounts" or cohort.count <= 0:
            continue
        typ = cohort.typ
        signed = (terms.signed_accounts_by_type[typ]
                  if terms.signed_accounts_by_type is not None
                  and typ in terms.signed_accounts_by_type
                  else midpoint(data, typ, "accounts_min", "accounts_max", over))
        if signed >= MIN_SIGNED_ACCOUNTS[typ]:
            counts[typ] += cohort.count

    eligible = sum(counts.values())
    target = min(eligible, floor(eligible * terms.uptake + 0.5))
    if eligible == 0 or target == 0:
        return {typ: 0 for typ in counts}
    raw = {typ: target * n / eligible for typ, n in counts.items()}
    allotted = {typ: floor(value) for typ, value in raw.items()}
    remainder = target - sum(allotted.values())
    ranked = sorted(counts, key=lambda typ: (-(raw[typ] - allotted[typ]), typ))
    for typ in ranked[:remainder]:
        allotted[typ] += 1
    return allotted


def _payback_quarters(initial: float, flows: Sequence[float]) -> float | None:
    if initial <= 0:
        return 0.0
    cumulative = 0.0
    for k, flow in enumerate(flows, start=1):
        before = cumulative
        cumulative += flow
        if flow > 0 and cumulative >= initial:
            return (k - 1 + (initial - before) / flow) / 4.0
    return None


def _npv(cashflows: Sequence[float], rate: float) -> float:
    return sum(c / (1 + rate) ** (q / 4) for q, c in enumerate(cashflows))


def run_financing(strategy: str, launches: Sequence[Launch], data: Inputs,
                  terms: FinancingTerms | None = None,
                  over: Overrides | None = None) -> FinancingResult:
    """Apply Lever 1 independently to an existing rollout and Case baseline.

    Each loan starts at the cohort's launch quarter. First operations, interest
    and repayment occur at the next quarter end. Each quarter accrues interest
    on opening *principal* (simple 10% APR / 4); unpaid interest is carried but
    does not itself earn interest. Payments cover accrued interest before
    principal and never exceed 75% of positive quarterly owner contribution.
    No defaults are assumed; arrears and outstanding principal are reported.
    """
    terms = terms or FinancingTerms()
    terms.validate()
    over = over or Overrides()
    launches = list(launches)
    baseline = run_hq(strategy, launches, data, over,
                      first_quarter_ramp=terms.first_quarter_ramp)
    discount = over.rule(data, "discount")
    if discount <= -1:
        raise ValueError("Discount rate must exceed -100%")

    target_by_type = _financed_counts(launches, data, over, terms)
    remaining = target_by_type.copy()
    advances = [0.0] * (PROGRAM_END_Q + 1)
    principal_receipts = [0.0] * (PROGRAM_END_Q + 1)
    interest_receipts = [0.0] * (PROGRAM_END_Q + 1)
    interest_accruals = [0.0] * (PROGRAM_END_Q + 1)
    loan_schedule: list[dict] = []
    owner_groups: list[dict] = []
    owner_base_total = owner_with_total = 0.0
    owner_failing = 0
    financed_cafes = 0
    gross_loan_advances = 0.0

    for cohort in sorted(launches, key=lambda c: (c.quarter, c.typ, c.option)):
        if cohort.count <= 0:
            continue
        unit = unit_economics(data, cohort.typ, cohort.option, over)
        funded = (min(cohort.count, remaining[cohort.typ])
                  if cohort.option == "Corporate Accounts" else 0)
        if funded:
            remaining[cohort.typ] -= funded
        loan = min(unit.capex_owner, LOAN_LIMITS[cohort.typ]) if funded else 0.0
        equity_investment = unit.capex_owner - loan
        financed_cafes += funded
        total_loan = loan * funded
        gross_loan_advances += total_loan
        if funded:
            advances[cohort.quarter] += total_loan

        # Track a complete five-year owner horizon even if launch is in 2031.
        principal = loan
        unpaid_interest = 0.0
        owner_operating: list[float] = []
        owner_free_cash: list[float] = []
        payments: list[float] = []
        loan_payoff = 0.0 if not funded else None
        for k in range(1, OWNER_HORIZON_Q + 1):
            global_q = cohort.quarter + k
            ramp = terms.first_quarter_ramp if k == 1 else 1.0
            contribution = unit.annual_owner_contribution * ramp / 4.0
            owner_operating.append(contribution)
            accrued = principal * terms.annual_interest / 4.0 if funded else 0.0
            interest_due = unpaid_interest + accrued
            capacity = max(0.0, contribution) * terms.contribution_sweep
            payment = min(principal + interest_due, capacity) if funded else 0.0
            interest_paid = min(payment, interest_due)
            principal_paid = payment - interest_paid
            principal = max(0.0, principal - principal_paid)
            unpaid_interest = max(0.0, interest_due - interest_paid)
            free_cash = contribution - payment
            owner_free_cash.append(free_cash)
            payments.append(payment)
            if funded and loan_payoff is None and principal + unpaid_interest < 1e-8:
                loan_payoff = k / 4.0

            if funded:
                within = global_q <= PROGRAM_END_Q
                if within:
                    principal_receipts[global_q] += principal_paid * funded
                    interest_receipts[global_q] += interest_paid * funded
                    interest_accruals[global_q] += accrued * funded
                loan_schedule.append({
                    "strategy": strategy, "type": cohort.typ,
                    "launch_q": cohort.quarter, "operating_q": k,
                    "global_q": global_q, "inside_hq_horizon": within,
                    "funded_cafes": funded,
                    "opening_principal_per_cafe": round(principal + principal_paid, 6),
                    "contribution_per_cafe": round(contribution, 6),
                    "interest_accrued_per_cafe": round(accrued, 6),
                    "interest_paid_per_cafe": round(interest_paid, 6),
                    "principal_paid_per_cafe": round(principal_paid, 6),
                    "total_debt_service_per_cafe": round(payment, 6),
                    "owner_retained_per_cafe": round(free_cash, 6),
                    "closing_principal_per_cafe": round(principal, 6),
                    "unpaid_interest_per_cafe": round(unpaid_interest, 6),
                })

        operating_payback = _payback_quarters(unit.capex_owner, owner_operating)
        baseline_owner_npv = -unit.capex_owner + sum(
            c / (1 + discount) ** (k / 4)
            for k, c in enumerate(owner_operating, start=1))
        financed_owner_npv = -equity_investment + sum(
            c / (1 + discount) ** (k / 4)
            for k, c in enumerate(owner_free_cash, start=1))
        # At end of owner forecast, remaining debt is a liability, not free money.
        terminal_debt = principal + unpaid_interest
        if funded and terminal_debt:
            financed_owner_npv -= terminal_debt / (1 + discount) ** 5
        owner_base_total += baseline_owner_npv * cohort.count
        owner_with_total += (financed_owner_npv * funded
                             + baseline_owner_npv * (cohort.count - funded))
        if operating_payback is None or operating_payback > data.rule("owner_payback_years"):
            owner_failing += cohort.count
        owner_groups.append({
            "strategy": strategy, "type": cohort.typ, "option": cohort.option,
            "launch_q": cohort.quarter, "cafes": cohort.count,
            "financed_cafes": funded, "loan_per_financed_cafe": round(loan, 2),
            "equity_capex_financed_cafe": round(equity_investment, 2),
            "operating_payback_years": operating_payback,
            "equity_cash_payback_years": _payback_quarters(
                equity_investment, owner_free_cash) if funded else None,
            "loan_payoff_years": loan_payoff if funded else None,
            "owner_npv_without_financing_per_cafe": round(baseline_owner_npv, 2),
            "owner_npv_with_financing_per_cafe": round(financed_owner_npv, 2) if funded else None,
            "loan_balance_after_owner_5y_per_cafe": round(terminal_debt, 2) if funded else None,
        })

    q_cashflows = []
    hq_quarters = []
    cumulative = 0.0
    outstanding_principal = 0.0
    outstanding_interest = 0.0
    hq_payback = None
    hq_cash_year4 = 0.0
    for q in range(PROGRAM_END_Q + 1):
        outstanding_principal += advances[q] - principal_receipts[q]
        outstanding_interest += interest_accruals[q] - interest_receipts[q]
        financing_cash = -advances[q] + principal_receipts[q] + interest_receipts[q]
        combined = baseline.cashflows[q] + financing_cash
        q_cashflows.append(combined)
        cumulative += combined
        if q == 16:
            hq_cash_year4 = cumulative
        if q > 0 and hq_payback is None and cumulative >= 0:
            hq_payback = q / 4
        hq_quarters.append({
            "strategy": strategy, "q": q, "year": 2027 + max(q - 1, 0) // 4,
            "baseline_hq_cash": round(baseline.cashflows[q], 2),
            "loan_advances": round(advances[q], 2),
            "principal_received": round(principal_receipts[q], 2),
            "interest_received": round(interest_receipts[q], 2),
            "net_loan_cash": round(financing_cash, 2),
            "combined_hq_cash": round(combined, 2),
            "cumulative_hq_cash": round(cumulative, 2),
            "principal_outstanding": round(max(0.0, outstanding_principal), 2),
            "interest_in_arrears": round(max(0.0, outstanding_interest), 2),
        })

    total_cafes = sum(c.count for c in launches)
    spending_y1 = baseline.hq_spend_year1 + sum(advances[:4])
    spending_3y = baseline.hq_spend_first_3y + sum(advances[:12])
    hq_npv = _npv(q_cashflows, discount)
    summary = {
        "strategy": strategy, "uptake_target": terms.uptake,
        "eligible_cafes": sum(_financed_counts(launches, data, over,
                                            FinancingTerms(uptake=1.0,
                                            signed_accounts_by_type=terms.signed_accounts_by_type)).values()),
        "financed_cafes": financed_cafes, "total_cafes": total_cafes,
        "gross_loan_advances": round(gross_loan_advances, 2),
        "principal_collected_by_2031": round(sum(principal_receipts), 2),
        "interest_collected_by_2031": round(sum(interest_receipts), 2),
        "principal_outstanding_at_2031": round(max(0, outstanding_principal), 2),
        "interest_in_arrears_at_2031": round(max(0, outstanding_interest), 2),
        "baseline_hq_npv_5y": round(baseline.npv_5y, 2),
        "financed_hq_npv_5y": round(hq_npv, 2),
        "hq_npv_change": round(hq_npv - baseline.npv_5y, 2),
        "hq_payback_years": hq_payback,
        "hq_cash_at_year4": round(hq_cash_year4, 2),
        "hq_four_year_target_met": hq_cash_year4 >= -1e-8,
        "owner_npv_without_financing_total": round(owner_base_total, 2),
        "owner_npv_with_financing_total": round(owner_with_total, 2),
        "owner_npv_delta_total": round(owner_with_total - owner_base_total, 2),
        "owner_failing_operating_3y": owner_failing,
        "hq_gross_spend_y1": round(spending_y1, 2),
        "hq_gross_spend_2027_2029": round(spending_3y, 2),
        "budget_y1_met": spending_y1 <= data.rule("year1_budget") + 1e-8,
        "budget_3y_met": spending_3y <= data.rule("budget_total") + 1e-8,
        # A planning diagnostic only: source budget_reserve is not assumed to
        # impose an additional binding constraint without Case confirmation.
        "remaining_3y_budget": round(data.rule("budget_total") - spending_3y, 2),
        "reserve_target_diagnostic_met": (
            data.rule("budget_total") - spending_3y >= data.rule("budget_reserve") - 1e-8),
        "rollout_feasible": not validate_launches(launches, data),
        "account_eligibility_basis": (
            "Case_midpoints_proxy_NOT_signed" if terms.signed_accounts_by_type is None
            else "explicit_signed_accounts" if all(
                typ in terms.signed_accounts_by_type for typ in LOAN_LIMITS)
            else "mixed_signed_accounts_and_Case_midpoints_proxy"),
    }
    return FinancingResult(strategy, terms, baseline, summary, hq_quarters,
                           loan_schedule, owner_groups)
