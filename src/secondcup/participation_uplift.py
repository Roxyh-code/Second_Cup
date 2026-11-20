"""Financing-led franchisee consent: compare realistic participation plans.

Case A8: 60 screening candidates, 20 *informally interested*, ZERO confirmed
consents. 20 is a modeling scenario ceiling for the no-financing baseline,
not 20 signed stores. L1 may unlock extra stores through financing.
Source baseline rollout has hard site-type and quarterly launch limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from typing import Mapping, Sequence

from .financial_engine import run_hq
from .hq_financing import FinancingTerms, run_financing
from .inputs import Inputs
from .scenarios import Launch, validate_launches
from .unit_economics import unit_economics

TYPES = ("Downtown", "University", "Suburban")


@dataclass(frozen=True)
class ParticipationTerms:
    # Illustrative conversion of informal interest into consent, NOT Case data.
    interested_conversion: float = 1.0
    # Conditional, assumed fraction of still-uncommitted candidates unlocked by L1.
    additional_conversion_with_finance: float = 2 / 3
    # Share of the new converts requiring an HQ advance to participate.
    incremental_financing_uptake: float = 1.0

    def validate(self) -> None:
        for key in ("interested_conversion", "additional_conversion_with_finance",
                    "incremental_financing_uptake"):
            value = getattr(self, key)
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{key} must be finite and in [0,1]")


def _allocate_hamilton(pool: Mapping[str, int], conversion: float) -> dict[str, int]:
    """Apportion a whole-network conversion target without fractional cafes."""
    total = sum(pool.values())
    desired = min(total, floor(total * conversion + 0.5))
    raw = {t: pool[t] * conversion for t in TYPES}
    counts = {t: min(pool[t], floor(raw[t])) for t in TYPES}
    gap = desired - sum(counts.values())
    ranked = sorted(TYPES, key=lambda t: (-(raw[t] - floor(raw[t])), t))
    for typ in ranked:
        if gap <= 0:
            break
        if counts[typ] < pool[typ]:
            counts[typ] += 1
            gap -= 1
    if gap:
        raise ValueError("Could not apportion participation")
    return counts


def select_rollout_slots(full_rollout: Sequence[Launch],
                         by_type: Mapping[str, int]) -> list[Launch]:
    """Reuse earliest available slots from original B Only, never invent launches."""
    remaining = dict(by_type)
    out = []
    for c in sorted(full_rollout, key=lambda x: (x.quarter, x.typ, x.option)):
        if c.option != "Corporate Accounts" and c.count:
            raise ValueError("Participation-only model requires Corporate Accounts rollout")
        n = min(c.count, remaining.get(c.typ, 0))
        if n:
            out.append(Launch(c.typ, c.option, c.quarter, n))
            remaining[c.typ] -= n
    if any(v != 0 for v in remaining.values()):
        raise ValueError(f"Not enough original rollout slots: {remaining}")
    return out


def build_participation_plans(full_rollout: Sequence[Launch], data: Inputs,
                              terms: ParticipationTerms | None = None) -> dict:
    terms = terms or ParticipationTerms()
    terms.validate()
    full_rollout = list(full_rollout)
    if any(c.option != "Corporate Accounts" for c in full_rollout):
        raise ValueError("This participation scenario requires B Only corporate rollout")
    if validate_launches(full_rollout, data):
        raise ValueError("Full rollout violates Case constraints")
    candidates = {t: int(data.get(t, "candidates")) for t in TYPES}
    interest = {t: int(data.get(t, "early_interest")) for t in TYPES}
    if sum(c.count for c in full_rollout) != sum(candidates.values()):
        raise ValueError("Need full candidate rollout to model participation uplift")
    baseline_counts = _allocate_hamilton(interest, terms.interested_conversion)
    remaining_pool = {t: candidates[t] - baseline_counts[t] for t in TYPES}
    incremental_counts = _allocate_hamilton(
        remaining_pool, terms.additional_conversion_with_finance)
    with_finance_counts = {
        t: baseline_counts[t] + incremental_counts[t] for t in TYPES}
    baseline = select_rollout_slots(full_rollout, baseline_counts)
    with_finance = select_rollout_slots(full_rollout, with_finance_counts)
    for plan in (baseline, with_finance):
        errors = validate_launches(plan, data)
        if errors:
            raise ValueError("Filtered rollout violates Case rules: " + "; ".join(errors))
    return {
        "baseline": baseline,
        "with_finance": with_finance,
        "baseline_counts": baseline_counts,
        "incremental_counts": incremental_counts,
        "with_finance_counts": with_finance_counts,
        "candidate_counts": candidates,
        "informal_interest_counts": interest,
    }


def financing_terms_for_participation(plans: dict, terms: ParticipationTerms):
    """Self-finance all baseline participants; fund only incremental converts."""
    return FinancingTerms(
        uptake=terms.incremental_financing_uptake,
        unfunded_priority_by_type=plans["baseline_counts"])


def run_participation_uplift(strategy: str, full_rollout: Sequence[Launch],
                             data: Inputs,
                             terms: ParticipationTerms | None = None) -> dict:
    terms = terms or ParticipationTerms()
    plans = build_participation_plans(full_rollout, data, terms)
    base = run_hq(strategy, plans["baseline"], data, first_quarter_ramp=.5)
    grown = run_hq(strategy, plans["with_finance"], data, first_quarter_ramp=.5)
    financed = run_financing(
        strategy, plans["with_finance"], data,
        financing_terms_for_participation(plans, terms))
    baseline_npv = base.npv_5y
    gross_royalty_effect = grown.npv_5y - baseline_npv
    financing_net_effect = financed.summary["financed_hq_npv_5y"] - grown.npv_5y
    by_type = {}
    annual_sales = annual_hq_royalty = annual_owner_contribution = 0.0
    for t in TYPES:
        u = unit_economics(data, t, "Corporate Accounts")
        n = plans["incremental_counts"][t]
        by_type[t] = {
            "type": t,
            "case_candidates": plans["candidate_counts"][t],
            "informally_interested_not_signed": plans["informal_interest_counts"][t],
            "baseline_consent_assumption": plans["baseline_counts"][t],
            "financing_unlocked_assumption": n,
            "with_finance_participants": plans["with_finance_counts"][t],
            "incremental_annual_store_sales": round(n * u.annual_sales_delta, 2),
            "incremental_annual_hq_royalty": round(n * u.annual_hq_royalty, 2),
            "incremental_annual_owner_contribution": round(
                n * u.annual_owner_contribution, 2),
        }
        annual_sales += n * u.annual_sales_delta
        annual_hq_royalty += n * u.annual_hq_royalty
        annual_owner_contribution += n * u.annual_owner_contribution
    summary = {
        "strategy": strategy,
        "consent_status_case": "NOT CONFIRMED - early interest is not owner consent",
        "confirmed_participants_case": None,
        "candidate_cafes": sum(plans["candidate_counts"].values()),
        "informally_interested_cafes": sum(plans["informal_interest_counts"].values()),
        "baseline_assumed_participants": sum(plans["baseline_counts"].values()),
        "financing_unlocked_cafes": sum(plans["incremental_counts"].values()),
        "assumed_participants_with_financing": sum(
            plans["with_finance_counts"].values()),
        "interest_to_consent_rate_assumed": terms.interested_conversion,
        "remaining_candidates_conversion_assumed": terms.additional_conversion_with_finance,
        "incremental_financing_uptake_assumed": terms.incremental_financing_uptake,
        "incremental_store_annual_sales_at_steady_state": round(annual_sales, 2),
        "incremental_owner_annual_contribution_at_steady_state": round(
            annual_owner_contribution, 2),
        "incremental_hq_annual_royalty_at_steady_state": round(
            annual_hq_royalty, 2),
        "hq_npv_without_financing_or_uplift": round(baseline_npv, 2),
        "hq_npv_full_participation_without_loans": round(grown.npv_5y, 2),
        "hq_npv_with_financing_and_uplift": (
            financed.summary["financed_hq_npv_5y"]),
        "incremental_hq_royalty_npv_from_new_participants": round(gross_royalty_effect, 2),
        "financing_net_cash_npv": round(financing_net_effect, 2),
        "total_hq_npv_gain_vs_baseline": round(
            financed.summary["financed_hq_npv_5y"] - baseline_npv, 2),
        "loans_issued_to_incremental_cafes": financed.summary["financed_cafes"],
        "gross_loan_advances": financed.summary["gross_loan_advances"],
        "hq_gross_spend_y1": financed.summary["hq_gross_spend_y1"],
        "hq_gross_spend_2027_2029": financed.summary["hq_gross_spend_2027_2029"],
        "remaining_3y_budget": financed.summary["remaining_3y_budget"],
        "hq_four_year_target_met": financed.summary["hq_four_year_target_met"],
        "hq_payback_years": financed.summary["hq_payback_years"],
        "hq_budget_y1_met": financed.summary["budget_y1_met"],
        "hq_budget_3y_met": financed.summary["budget_3y_met"],
        "hq_500k_reserve_diagnostic_met": financed.summary["reserve_target_diagnostic_met"],
    }
    return {
        "summary": summary, "by_type": list(by_type.values()),
        "baseline_launches": plans["baseline"],
        "assisted_launches": plans["with_finance"],
        "hq_quarters": financed.hq_quarters,
        "loans": financed.loan_schedule,
        "planning": plans,
    }
