"""Lever 3: deferred program fee on Corporate Accounts sales.

Built on existing L1 and L2 engines without modifying the Case baseline.
HQ fee receipts = owner fee payments (a transfer, not incremental cafe sales).
An equity investment of zero after HQ financing does NOT trigger fees at launch.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from .financial_engine import run_hq
from .hq_financing import FinancingTerms, run_financing, _payback_quarters
from .inputs import Inputs, Overrides
from .landlord_acquisition import LandlordTerms, run_landlord
from .scenarios import Launch
from .unit_economics import unit_economics

TYPES = ("Downtown", "University", "Suburban")
HQ_END = 20
OWNER_QUARTERS = 20
START_MODES = ("after_operating_payback", "after_operating_and_loan_payoff",
               "immediate")
FEE_BASES = ("all_corporate", "landlord_incremental")


@dataclass(frozen=True)
class DeferredFeeTerms:
    rate: float = 0.05
    start_mode: str = "after_operating_payback"
    fee_base: str = "all_corporate"
    first_quarter_ramp: float = 0.50

    def validate(self) -> None:
        if not isfinite(self.rate) or not 0.0 <= self.rate <= 1.0:
            raise ValueError("rate must be finite and in [0, 1]")
        if self.start_mode not in START_MODES:
            raise ValueError(f"start_mode must be one of {START_MODES}")
        if self.fee_base not in FEE_BASES:
            raise ValueError(f"fee_base must be one of {FEE_BASES}")
        if not isfinite(self.first_quarter_ramp) or not 0 <= self.first_quarter_ramp <= 1:
            raise ValueError("first_quarter_ramp must be in [0, 1]")


@dataclass
class DeferredFeeResult:
    summary: dict
    hq_quarters: list[dict]
    fee_schedule: list[dict]
    owner_cohorts: list[dict]
    loan_schedule: list[dict]


def _npv_quarters(flows, discount):
    return sum(value / (1.0 + discount) ** (q / 4.0)
               for q, value in enumerate(flows))


def _added_accounts_by_type(launches, landlord):
    if landlord is None:
        return {t: 0.0 for t in TYPES}
    participants = {t: sum(x.count for x in launches
                           if x.typ == t and x.option == "Corporate Accounts")
                    for t in TYPES}
    return {
        t: (landlord.partners_by_type.get(t, 0.0)
            * landlord.tenant_introductions_per_partner
            * landlord.signed_conversion_rate / participants[t])
        if participants[t] else 0.0
        for t in TYPES
    }


def run_deferred_fee(strategy: str, launches: Sequence[Launch],
                     data: Inputs, fee: DeferredFeeTerms | None = None,
                     *, financing: FinancingTerms | None = None,
                     landlord: LandlordTerms | None = None) -> DeferredFeeResult:
    """Evaluate deferred fees, optionally integrating L1 and/or L2.

    All operating contributions are before L3 fees. Loan servicing follows
    the existing 75%-of-positive-operating-contribution waterfall; the fee
    is paid out of the owner's remaining cash. Negative owner cash is flagged,
    not silently reallocated to the lender. Default fee trigger is the first
    quarter AFTER cumulative before-fee operating contribution has recovered
    the original Corporate Accounts CAPEX, regardless of financing equity.
    """
    fee = fee or DeferredFeeTerms()
    fee.validate()
    if landlord is not None:
        landlord.validate()
        if abs(landlord.first_quarter_ramp - fee.first_quarter_ramp) > 1e-12:
            raise ValueError("Landlord and fee ramps must match")
    if financing is not None:
        financing.validate()
        if abs(financing.first_quarter_ramp - fee.first_quarter_ramp) > 1e-12:
            raise ValueError("Financing and fee ramps must match")

    launches = list(launches)
    if landlord is not None:
        upstream = run_landlord(strategy, launches, data, landlord,
                                financing=financing)
        upstream_summary = upstream.summary
        pre_fee_owner_npv = (upstream_summary["owner_npv_financed_total"]
                             if financing is not None else
                             upstream_summary["owner_npv_operating_after_acquisition_total"])
        pre_fee_hq_npv = upstream_summary["integrated_hq_npv_5y"]
        loan_schedule = upstream.loan_schedule
        upstream_quarters = upstream.hq_quarters
    else:
        loan_terms = financing or FinancingTerms(
            uptake=0.0, first_quarter_ramp=fee.first_quarter_ramp)
        upstream = run_financing(strategy, launches, data, loan_terms)
        upstream_summary = upstream.summary
        pre_fee_owner_npv = upstream_summary["owner_npv_with_financing_total"]
        pre_fee_hq_npv = upstream_summary["financed_hq_npv_5y"]
        loan_schedule = upstream.loan_schedule
        upstream_quarters = upstream.hq_quarters

    discount = data.rule("discount")
    if discount <= -1:
        raise ValueError("Discount rate must exceed -100%")
    added = _added_accounts_by_type(launches, landlord)
    overrides = {}
    for t in TYPES:
        if added[t]:
            overrides[t] = {
                "accounts_min": data.get(t, "accounts_min") + added[t],
                "accounts_max": data.get(t, "accounts_max") + added[t],
            }
    over = Overrides(type_parameters=overrides)
    # Each funded corporate cohort has 20 loan rows, including beyond HQ 2031.
    loan_lookup = {}
    funded_lookup = {}
    for row in loan_schedule:
        key = (row["type"], row["launch_q"], row["operating_q"])
        if key in loan_lookup:
            raise ValueError("Ambiguous financed cohorts with identical type and launch quarter")
        loan_lookup[key] = row
        if row["operating_q"] == 1:
            funded_lookup[(row["type"], row["launch_q"])] = row["funded_cafes"]

    hq_fee = [0.0] * (HQ_END + 1)
    fee_rows = []
    owner_rows = []
    fee_pv_owner = 0.0
    fee_cash_owner = 0.0
    active_owner_stores = 0
    owner_failures_after_fee = 0
    owner_negative_cash_quarters = 0
    earliest_activation = None
    for cohort in sorted(launches, key=lambda c: (c.quarter, c.typ, c.option)):
        if cohort.count <= 0:
            continue
        unit = unit_economics(data, cohort.typ, cohort.option, over)
        is_corporate = cohort.option == "Corporate Accounts"
        if is_corporate:
            if fee.fee_base == "all_corporate":
                annual_feeable_sales = unit.annual_sales_delta
            else:
                annual_feeable_sales = (
                    added[cohort.typ] * data.get(cohort.typ, "orders_per_week")
                    * data.get(cohort.typ, "cups_per_order")
                    * data.get(cohort.typ, "weeks_year")
                    * data.get(cohort.typ, "cup_price"))
        else:
            annual_feeable_sales = 0.0

        n_funded = funded_lookup.get((cohort.typ, cohort.quarter), 0) if is_corporate else 0
        if n_funded > cohort.count:
            raise ValueError("Financed store count exceeds cohort stores")
        for funded, store_count in ((True, n_funded),
                                    (False, cohort.count - n_funded)):
            if not store_count:
                continue
            before_fee_operating = 0.0
            operating = []
            after_fee_operating = []
            fee_total_per_store = 0.0
            pv_fee_per_store = 0.0
            min_owner_cash = float("inf")
            first_charge_k = None
            post_debt_cash = []
            for k in range(1, OWNER_QUARTERS + 1):
                global_q = cohort.quarter + k
                ramp = fee.first_quarter_ramp if k == 1 else 1.0
                contribution = unit.annual_owner_contribution * ramp / 4.0
                operating.append(contribution)
                base_recovered_before_q = (before_fee_operating + 1e-8 >=
                                           unit.capex_owner)
                debt_row = (loan_lookup.get((cohort.typ, cohort.quarter, k))
                            if funded else None)
                if funded and debt_row is None:
                    raise ValueError("Missing loan schedule for a funded cohort")
                debt_service = debt_row["total_debt_service_per_cafe"] if debt_row else 0.0
                prev_debt_row = (loan_lookup.get((cohort.typ, cohort.quarter, k - 1))
                                 if funded and k > 1 else None)
                paid_off_before_q = (not funded or (
                    prev_debt_row is not None
                    and prev_debt_row["closing_principal_per_cafe"] < 1e-7
                    and prev_debt_row["unpaid_interest_per_cafe"] < 1e-7))
                if fee.start_mode == "immediate":
                    triggered = True
                elif fee.start_mode == "after_operating_payback":
                    triggered = base_recovered_before_q
                else:
                    triggered = base_recovered_before_q and paid_off_before_q
                charged = (annual_feeable_sales * ramp * fee.rate / 4.0
                           if is_corporate and triggered else 0.0)
                if charged > 0 and first_charge_k is None:
                    first_charge_k = k
                    if earliest_activation is None or global_q < earliest_activation:
                        earliest_activation = global_q
                free_cash = contribution - debt_service - charged
                min_owner_cash = min(min_owner_cash, free_cash)
                if free_cash < -1e-7:
                    owner_negative_cash_quarters += store_count
                after_fee_operating.append(contribution - charged)
                post_debt_cash.append(free_cash)
                before_fee_operating += contribution
                fee_total_per_store += charged
                pv_fee_per_store += charged / (1 + discount) ** (k / 4.0)
                if global_q <= HQ_END:
                    hq_fee[global_q] += charged * store_count
                if is_corporate:
                    fee_rows.append({
                        "type": cohort.typ, "option": cohort.option,
                        "launch_q": cohort.quarter, "global_q": global_q,
                        "operating_q": k, "inside_hq_horizon": global_q <= HQ_END,
                        "financed": funded, "cafes": store_count,
                        "operating_contribution_per_cafe": round(contribution, 6),
                        "cumulative_operating_before_quarter": round(
                            before_fee_operating - contribution, 6),
                        "original_capex_per_cafe": round(unit.capex_owner, 2),
                        "feeable_sales_per_cafe": round(annual_feeable_sales, 2),
                        "fee_rate": fee.rate,
                        "fee_active": charged > 0,
                        "fee_per_cafe": round(charged, 6),
                        "fee_total": round(charged * store_count, 6),
                        "loan_debt_service_per_cafe": round(debt_service, 6),
                        "owner_cash_after_loan_and_fee_per_cafe": round(free_cash, 6),
                    })
            operating_payback = _payback_quarters(unit.capex_owner, operating)
            after_fee_payback = _payback_quarters(unit.capex_owner, after_fee_operating)
            if after_fee_payback is None or after_fee_payback > data.rule("owner_payback_years"):
                owner_failures_after_fee += store_count
            fee_pv_owner += pv_fee_per_store * store_count
            fee_cash_owner += fee_total_per_store * store_count
            if first_charge_k is not None:
                active_owner_stores += store_count
            owner_rows.append({
                "type": cohort.typ, "option": cohort.option,
                "launch_q": cohort.quarter, "cafes": store_count,
                "financed": funded,
                "operating_payback_years_before_fee": operating_payback,
                "operating_payback_years_after_fee": after_fee_payback,
                "first_fee_operating_q": first_charge_k,
                "first_fee_global_q": (cohort.quarter + first_charge_k
                                        if first_charge_k is not None else None),
                "fee_per_cafe_owner_5y": round(fee_total_per_store, 2),
                "fee_npv_per_cafe_owner_5y": round(pv_fee_per_store, 2),
                "minimum_owner_cash_after_loan_and_fee": round(min_owner_cash, 2),
                "owner_fee_receiving_cash_5y": round(
                    sum(post_debt_cash), 2),
            })
    hq_quarters = []
    running = 0.0
    cash_year4 = 0.0
    hq_payback = None
    for q in range(HQ_END + 1):
        pre_fee = upstream_quarters[q]["combined_hq_cash"]
        post_fee = pre_fee + hq_fee[q]
        running += post_fee
        if q == 16:
            cash_year4 = running
        if q > 0 and hq_payback is None and running >= 0:
            hq_payback = q / 4.0
        hq_quarters.append({
            "q": q, "year": 2027 + max(q - 1, 0) // 4,
            "pre_fee_hq_cash": round(pre_fee, 2),
            "fee_receipts": round(hq_fee[q], 2),
            "post_fee_hq_cash": round(post_fee, 2),
            "cumulative_hq_cash": round(running, 2),
        })
    new_hq_npv = _npv_quarters(
        [upstream_quarters[q]["combined_hq_cash"] + hq_fee[q]
         for q in range(HQ_END + 1)], discount)
    gross_spend_y1 = upstream_summary["hq_gross_spend_y1"]
    gross_spend_3y = upstream_summary["hq_gross_spend_2027_2029"]
    out = {
        "strategy": strategy,
        "lever1_financing_enabled": financing is not None,
        "lever2_landlord_enabled": landlord is not None,
        "lever3_deferred_fee_enabled": fee.rate > 0.0,
        "fee_rate": fee.rate, "fee_start_mode": fee.start_mode,
        "fee_base": fee.fee_base, "first_quarter_ramp": fee.first_quarter_ramp,
        "corporate_cafes": sum(
            x.count for x in launches if x.option == "Corporate Accounts"),
        "landlord_incremental_accounts": round(sum(
            added[t] * sum(x.count for x in launches
                           if x.typ == t and x.option == "Corporate Accounts")
            for t in TYPES), 4),
        "first_fee_global_q": earliest_activation,
        "cafes_charged_within_owner_5y": active_owner_stores,
        "hq_fee_received_by_2031": round(sum(hq_fee), 2),
        "owner_fees_paid_across_5y_cohorts": round(fee_cash_owner, 2),
        "owner_fee_pv_across_5y_cohorts": round(fee_pv_owner, 2),
        "hq_npv_before_fee": round(pre_fee_hq_npv, 2),
        "hq_npv_5y": round(new_hq_npv, 2),
        "hq_npv_gain_from_fee": round(new_hq_npv - pre_fee_hq_npv, 2),
        "owner_npv_before_fee_total": round(pre_fee_owner_npv, 2),
        "owner_npv_after_fee_total": round(pre_fee_owner_npv - fee_pv_owner, 2),
        "owner_npv_change_from_fee": round(-fee_pv_owner, 2),
        "owner_failing_3yr_after_fee": owner_failures_after_fee,
        "owner_negative_cash_quarters": owner_negative_cash_quarters,
        "hq_cash_at_year4": round(cash_year4, 2),
        "hq_payback_years": hq_payback,
        "hq_four_year_target_met": cash_year4 >= -1e-8,
        "hq_gross_spend_y1": gross_spend_y1,
        "hq_gross_spend_2027_2029": gross_spend_3y,
        "budget_y1_met": upstream_summary["budget_y1_met"],
        "budget_3y_met": upstream_summary["budget_3y_met"],
        "remaining_3y_budget": upstream_summary["remaining_3y_budget"],
        "reserve_target_diagnostic_met":
            upstream_summary["reserve_target_diagnostic_met"],
        "financed_cafes": upstream_summary["financed_cafes"],
        "gross_loan_advances": upstream_summary["gross_loan_advances"],
        "principal_collected_by_2031":
            upstream_summary["principal_collected_by_2031"],
        "interest_collected_by_2031":
            upstream_summary["interest_collected_by_2031"],
    }
    return DeferredFeeResult(out, hq_quarters, fee_rows, owner_rows, loan_schedule)
