"""Lever 2: landlord-introduced corporate accounts, standalone or combined with Lever 1.

All funnel numbers are adjustable, hypothetical scenario inputs, not Case facts.
No change to original Case assumptions, rollout, coordination cost or 32% margin.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .inputs import Inputs, Overrides
from .scenarios import Launch
from .unit_economics import unit_economics
from .financial_engine import run_hq
from .hq_financing import FinancingTerms, run_financing

TYPES = ("Downtown", "University", "Suburban")


@dataclass(frozen=True)
class LandlordTerms:
    partners_by_type: Mapping[str, float] = field(default_factory=lambda: {
        "Downtown": 12.0, "University": 8.0, "Suburban": 20.0})
    tenant_introductions_per_partner: float = 6.0
    signed_conversion_rate: float = 0.50
    acquisition_cost_per_signed_account: float = 500.0
    first_quarter_ramp: float = 0.50
    additional_hq_setup_cost: float = 0.0
    additional_hq_annual_cost: float = 0.0

    def validate(self):
        if not 0 <= self.signed_conversion_rate <= 1:
            raise ValueError("signed_conversion_rate must be in [0,1]")
        if not 0 <= self.first_quarter_ramp <= 1:
            raise ValueError("first_quarter_ramp must be in [0,1]")
        if self.tenant_introductions_per_partner < 0 or self.acquisition_cost_per_signed_account < 0:
            raise ValueError("introductions and CAC cannot be negative")
        if self.additional_hq_setup_cost < 0 or self.additional_hq_annual_cost < 0:
            raise ValueError("Additional HQ setup and annual costs cannot be negative")
        if any(t not in TYPES or n < 0 for t, n in self.partners_by_type.items()):
            raise ValueError("Invalid landlord partner counts")


@dataclass
class LandlordResult:
    summary: dict
    hq_quarters: list[dict]
    acquisition_cohorts: list[dict]
    owner_cohorts: list[dict]
    loan_schedule: list[dict]


def run_landlord(strategy: str, launches: Sequence[Launch], data: Inputs,
                 terms: LandlordTerms | None = None, *,
                 financing: FinancingTerms | None = None) -> LandlordResult:
    """Switchable L2 layer; optional L1+L2 integrated quarterly loan waterfall."""
    terms = terms or LandlordTerms()
    terms.validate()
    launches = list(launches)
    participants = {
        typ: sum(c.count for c in launches
                 if c.typ == typ and c.option == "Corporate Accounts")
        for typ in TYPES}
    # Engaging landlords has potential management expense even when no
    # tenant signs. It is only incurred if at least one eligible corporate
    # cafe is in the rollout and a landlord partnership is attempted.
    partner_program_active = any(
        participants[t] > 0 and terms.partners_by_type.get(t, 0) > 0 for t in TYPES)
    extra_setup = terms.additional_hq_setup_cost if partner_program_active else 0.0
    extra_annual = terms.additional_hq_annual_cost if partner_program_active else 0.0
    per_cafe = {}
    by_type = {}
    for typ in TYPES:
        accounts = (terms.partners_by_type.get(typ, 0)
                    * terms.tenant_introductions_per_partner
                    * terms.signed_conversion_rate) if participants[typ] else 0
        per_cafe[typ] = accounts / participants[typ] if participants[typ] else 0.0
        if accounts:
            by_type[typ] = {
                "accounts_min": data.get(typ, "accounts_min") + per_cafe[typ],
                "accounts_max": data.get(typ, "accounts_max") + per_cafe[typ]}
    over = Overrides(type_parameters=by_type)
    base = run_hq(strategy, launches, data,
                  first_quarter_ramp=terms.first_quarter_ramp)
    acquisition_costs = [0.0] * 21
    cohorts = []
    for c in sorted(launches, key=lambda c: (c.quarter, c.typ, c.option)):
        if c.option != "Corporate Accounts" or c.count <= 0:
            continue
        added = per_cafe[c.typ] * c.count
        cost = added * terms.acquisition_cost_per_signed_account
        acquisition_costs[c.quarter] += cost
        value = (data.get(c.typ, "orders_per_week")
                 * data.get(c.typ, "cups_per_order")
                 * data.get(c.typ, "weeks_year")
                 * data.get(c.typ, "cup_price"))
        cohorts.append({
            "type": c.typ, "launch_q": c.quarter, "cafes": c.count,
            "incremental_accounts": round(added, 6),
            "incremental_accounts_per_cafe": round(per_cafe[c.typ], 6),
            "hq_acquisition_cost": round(cost, 2),
            "incremental_annual_sales": round(added * value, 2),
            "incremental_annual_owner_contribution": round(
                added * value * data.get(c.typ, "corp_contrib"), 2),
            "incremental_annual_hq_royalty": round(
                added * value * data.rule("royalty"), 2)})
    if financing is None:
        modeled = run_hq(strategy, launches, data, over,
                         first_quarter_ramp=terms.first_quarter_ramp)
        before_cac = modeled.cashflows
        loan_rows = []
        loan_quarters = None
        funded = 0
        advances = principal = interest = remaining_loan = arrears = 0.0
    else:
        if abs(financing.first_quarter_ramp - terms.first_quarter_ramp) > 1e-12:
            raise ValueError("Financing and acquisition must use the same ramp")
        financed = run_financing(strategy, launches, data, financing, over)
        before_cac = [q["combined_hq_cash"] for q in financed.hq_quarters]
        loan_quarters = financed.hq_quarters
        loan_rows = financed.loan_schedule
        ss = financed.summary
        funded = ss["financed_cafes"]
        advances = ss["gross_loan_advances"]
        principal = ss["principal_collected_by_2031"]
        interest = ss["interest_collected_by_2031"]
        remaining_loan = ss["principal_outstanding_at_2031"]
        arrears = ss["interest_in_arrears_at_2031"]

    discount = data.rule("discount")
    if discount <= -1:
        raise ValueError("Discount rate must exceed -100%")
    owner_rows = []
    base_owner_npv = operating_owner_npv = 0.0
    owner_failures = 0
    for c in launches:
        if c.count <= 0:
            continue
        original = unit_economics(data, c.typ, c.option)
        improved = unit_economics(data, c.typ, c.option, over)
        def owner_forecast(unit):
            flow = [unit.annual_owner_contribution * (
                terms.first_quarter_ramp if k == 1 else 1.0) / 4
                for k in range(1, 21)]
            npv = -unit.capex_owner + sum(
                f / (1 + discount) ** (k / 4)
                for k, f in enumerate(flow, 1))
            running = 0.0
            payback = None
            for k, f in enumerate(flow, 1):
                prior = running
                running += f
                if f > 0 and running >= unit.capex_owner:
                    payback = (k - 1 + (unit.capex_owner - prior) / f) / 4
                    break
            return npv, payback
        n0, _ = owner_forecast(original)
        n1, pb = owner_forecast(improved)
        base_owner_npv += n0 * c.count
        operating_owner_npv += n1 * c.count
        if pb is None or pb > data.rule("owner_payback_years"):
            owner_failures += c.count
        owner_rows.append({
            "type": c.typ, "option": c.option, "launch_q": c.quarter,
            "cafes": c.count, "owner_npv_baseline_per_cafe": round(n0, 2),
            "owner_npv_operating_after_acquisition_per_cafe": round(n1, 2),
            "operating_payback_years": pb})

    extra_fixed_costs = [extra_setup] + [extra_annual / 4.0] * 20
    cash = [v - acquisition_costs[q] - extra_fixed_costs[q]
            for q, v in enumerate(before_cac)]
    cumulative = 0.0
    payback = None
    cash_at_year4 = 0.0
    quarter_rows = []
    for q, v in enumerate(cash):
        cumulative += v
        if q == 16:
            cash_at_year4 = cumulative
        if q > 0 and payback is None and cumulative >= 0:
            payback = q / 4
        loanq = loan_quarters[q] if loan_quarters is not None else {}
        quarter_rows.append({
            "q": q, "year": 2027 + max(q - 1, 0) // 4,
            "baseline_hq_cash": round(base.cashflows[q], 2),
            "cash_before_acquisition_cost": round(before_cac[q], 2),
            "acquisition_cost": round(acquisition_costs[q], 2),
            "additional_partner_setup_cost": round(extra_setup if q == 0 else 0.0, 2),
            "additional_partner_annual_cost": round(extra_annual / 4 if q else 0.0, 2),
            "total_landlord_cost": round(acquisition_costs[q] + extra_fixed_costs[q], 2),
            "combined_hq_cash": round(v, 2),
            "cumulative_hq_cash": round(cumulative, 2),
            "loan_advances": loanq.get("loan_advances", 0.0),
            "loan_principal_received": loanq.get("principal_received", 0.0),
            "loan_interest_received": loanq.get("interest_received", 0.0),
            "loan_principal_outstanding": loanq.get("principal_outstanding", 0.0)})
    y1 = base.hq_spend_year1 + sum(acquisition_costs[:4]) + extra_setup + extra_annual
    three_y = (base.hq_spend_first_3y + sum(acquisition_costs[:12])
               + extra_setup + 3.0 * extra_annual)
    if loan_quarters is not None:
        y1 += sum(q["loan_advances"] for q in loan_quarters[:4])
        three_y += sum(q["loan_advances"] for q in loan_quarters[:12])
    remaining = data.rule("budget_total") - three_y
    final_npv = sum(v / (1 + discount) ** (q / 4)
                    for q, v in enumerate(cash))
    summary = {
        "strategy": strategy, "lever1_financing_enabled": financing is not None,
        "corporate_cafes": sum(participants.values()),
        "existing_accounts_planning_basis": round(sum(
            participants[t] * (data.get(t, "accounts_min")
                               + data.get(t, "accounts_max")) / 2
            for t in TYPES), 6),
        "incremental_accounts": round(sum(
            per_cafe[t] * participants[t] for t in TYPES), 6),
        "incremental_acquisition_cost": round(sum(acquisition_costs), 2),
        "additional_hq_setup_cost": round(extra_setup, 2),
        "additional_hq_annual_cost": round(extra_annual, 2),
        "additional_hq_fixed_cost_5y_gross": round(extra_setup + 5 * extra_annual, 2),
        "total_incremental_hq_cost_5y_gross": round(
            sum(acquisition_costs) + extra_setup + 5 * extra_annual, 2),
        "partner_program_active": partner_program_active,
        "incremental_annual_sales_at_steady_state": round(sum(
            r["incremental_annual_sales"] for r in cohorts), 2),
        "incremental_annual_hq_royalty_at_steady_state": round(sum(
            r["incremental_annual_hq_royalty"] for r in cohorts), 2),
        "owner_npv_baseline_total": round(base_owner_npv, 2),
        "owner_npv_operating_after_acquisition_total": round(operating_owner_npv, 2),
        "owner_npv_financed_total": (financed.summary["owner_npv_with_financing_total"]
                                     if financing is not None else None),
        "owner_operating_failures_3y": owner_failures,
        "baseline_hq_npv_5y": round(base.npv_5y, 2),
        "integrated_hq_npv_5y": round(final_npv, 2),
        "hq_npv_change": round(final_npv - base.npv_5y, 2),
        "hq_payback_years": payback,
        "hq_cash_at_year4": round(cash_at_year4, 2),
        "hq_four_year_target_met": cash_at_year4 >= -1e-8,
        "financed_cafes": funded, "gross_loan_advances": round(advances, 2),
        "principal_collected_by_2031": round(principal, 2),
        "interest_collected_by_2031": round(interest, 2),
        "principal_outstanding_at_2031": round(remaining_loan, 2),
        "interest_in_arrears_at_2031": round(arrears, 2),
        "hq_gross_spend_y1": round(y1, 2),
        "hq_gross_spend_2027_2029": round(three_y, 2),
        "remaining_3y_budget": round(remaining, 2),
        "budget_y1_met": y1 <= data.rule("year1_budget") + 1e-8,
        "budget_3y_met": three_y <= data.rule("budget_total") + 1e-8,
        "reserve_target_diagnostic_met": remaining >= data.rule("budget_reserve") - 1e-8,
        "assumptions_status": "HYPOTHETICAL_PARTNERS_INTROS_CONVERSION_CAC"}
    return LandlordResult(summary, quarter_rows, cohorts, owner_rows, loan_rows)
