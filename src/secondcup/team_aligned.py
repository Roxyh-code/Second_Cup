"""Team-deck-aligned Second Cup Strategy B financial engine (UTCC 2026).

Three *strategic enablers* (matching the team's 14-slide PDF):
  L1: Cash Advance          -> higher franchise participation
  L2: Landlord Sales Channel -> new signed corporate accounts
  L3: Fixed Production Slots -> protect service / reduce downside leakage

Shared team commercial assumptions (all eight scenarios):
 - Corporate Accounts Case B: HQ setup $40k, HQ sales coordination $90k/yr;
 - Portal $25k HQ setup (analogy, NOT prescribed for B by Case);
 - Portal $1,800/store/year paid by franchisee (analogy);
 - Additional 5% program fee AFTER original operating CAPEX payback (team
   proposal, NOT a third lever, included in every scenario consistently).

The 32% corporate contribution already includes Case franchise charges.
Royalties are an HQ income line; DO NOT subtract them twice at the café.
L3's baseline incremental sales benefit is ZERO without evidence of leakage.
The optional "at-risk sales" sensitivity makes assumptions explicit.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import floor, isfinite
from typing import Sequence

from .inputs import Inputs
from .participation_uplift import ParticipationTerms, build_participation_plans
from .scenarios import Launch, validate_launches

TYPES = ("Downtown", "University", "Suburban")
LEVER_NAMES = ("Cash Advance", "Landlord Sales Channel", "Fixed Production Slots")
PROGRAM_Q = 20
DECK_ROLLOUT = (
    # 2027 Q1 6 pilot, Q2 observation; then six / quarter; completed Q3 2029.
    ("Suburban", 0, 6), ("Suburban", 2, 6),
    ("Suburban", 3, 6), ("Suburban", 4, 6),
    ("Suburban", 5, 6), ("Suburban", 6, 2),
    ("Downtown", 6, 4), ("Downtown", 7, 6),
    ("Downtown", 8, 6), ("Downtown", 9, 2),
    ("University", 9, 4), ("University", 10, 6),
)


@dataclass(frozen=True)
class TeamAssumptions:
    base_interest_consent: float = 1.0
    loan_uptake: float = 2 / 3
    annual_loan_interest: float = .10
    loan_sweep: float = .75
    landlord_partners: tuple[float, float, float] = (12., 8., 20.)
    introductions_per_partner: float = 10.0  # team slide says ~10
    conversion_of_intros: float = .30  # HYPOTHETICAL to yield 120 extra accounts
    acquisition_cost_per_account: float = 500.0  # HYPOTHETICAL
    landlord_extra_setup: float = 0.0
    landlord_extra_annual: float = 0.0
    portal_hq_setup: float = 25000.0  # team borrowed SaaS cost by analogy
    portal_owner_annual: float = 1800.0  # team borrowed annual store SaaS cost
    team_supporting_fee: float = .05  # shared team policy, NOT L3
    first_quarter_sales_ramp: float = .5
    # 0% = no quantified incremental sales attributed to production slots.
    # 5% = explicitly hypothetical loss if slots are NOT active, prevented by L3.
    no_slots_sales_leakage: float = 0.0
    production_windows_per_day: int = 2
    weekdays_per_week: int = 5
    # Costs, if any, for implementing fixed slots (not in Case/team deck).
    slot_setup_per_cafe: float = 0.0
    slot_annual_per_cafe: float = 0.0  # optional OWNER cost, not HQ

    def validate(self):
        bounded = ("base_interest_consent", "loan_uptake", "loan_sweep",
                   "conversion_of_intros", "team_supporting_fee",
                   "first_quarter_sales_ramp", "no_slots_sales_leakage")
        for key in bounded:
            n = getattr(self, key)
            if not isfinite(n) or not (0 <= n <= 1):
                raise ValueError(key + " must be finite and between zero and one")
        nonnegative = ("annual_loan_interest", "introductions_per_partner",
                       "acquisition_cost_per_account", "landlord_extra_setup",
                       "landlord_extra_annual", "portal_hq_setup",
                       "portal_owner_annual", "slot_setup_per_cafe",
                       "slot_annual_per_cafe")
        for key in nonnegative:
            n = getattr(self, key)
            if not isfinite(n) or n < 0:
                raise ValueError(key + " must be finite and nonnegative")
        if len(self.landlord_partners) != 3 or any(
            not isfinite(n) or n < 0 for n in self.landlord_partners
        ):
            raise ValueError("landlord_partners must be three nonnegative counts")
        if self.production_windows_per_day < 1 or self.weekdays_per_week < 1:
            raise ValueError("Need at least one production slot a week")


def deck_launches(data: Inputs) -> list[Launch]:
    """Exact café counts and timing from the team's rollout slide, not old repo."""
    launches = [Launch(typ, "Corporate Accounts", q, count)
                for typ, q, count in DECK_ROLLOUT]
    errors = validate_launches(launches, data)
    if errors:
        raise ValueError("Deck rollout violates constraints: " + "; ".join(errors))
    for typ in TYPES:
        n = sum(c.count for c in launches if c.typ == typ)
        if n != int(data.get(typ, "candidates")):
            raise ValueError("Rollout count mismatch for " + typ)
    return launches


def _apportion_by_capacity(capacities, target, *, priority=None):
    """Hamilton allocation subject to integral maximum per cohort."""
    total = sum(capacities)
    if not 0 <= target <= total:
        raise ValueError("Target exceeds café capacity")
    if total == 0:
        return [0] * len(capacities)
    raw = [target * c / total for c in capacities]
    out = [floor(x) for x in raw]
    remaining = target - sum(out)
    # Fractions first; earlier cohort wins exact ties.
    order = sorted(range(len(out)),
                   key=lambda i: (-(raw[i] - out[i]), priority[i] if priority else i))
    for i in order:
        if remaining == 0:
            break
        if out[i] < capacities[i]:
            out[i] += 1
            remaining -= 1
    if remaining:
        raise ValueError("Unable to allocate total integer loans")
    return out


def allocate_team_advances(launches: Sequence[Launch], uptake: float) -> dict:
    """About 2/3 FINANCED IN EACH COHORT, not front-load to earliest launches.

    Apportion full network by type first: for 60 cafés this gives
    Downtown 12, University 7, Suburban 21 (40 loans, $579k).
    Within each type spread loans over the source deck launch cohorts.
    In 2027, 18 suburban launches receive exactly 12 loans ($180k).
    """
    totals = [sum(c.count for c in launches if c.typ == t) for t in TYPES]
    loan_total = floor(sum(totals) * uptake + .5)
    by_type = _apportion_by_capacity(totals, loan_total)
    funded = {}
    for typ, want in zip(TYPES, by_type):
        group = [(i, c) for i, c in enumerate(launches) if c.typ == typ]
        allot = _apportion_by_capacity([c.count for _, c in group], want,
                                       priority=[c.quarter for _, c in group])
        for (i, _), n in zip(group, allot):
            funded[i] = n
    return funded


def _npv(flows, discount, *, offset=0):
    return sum(v / (1 + discount) ** ((k + offset) / 4)
               for k, v in enumerate(flows))


def _payback(capex, owner_operating_flow):
    if capex <= 0:
        return 0.
    total = 0.
    for k, f in enumerate(owner_operating_flow, 1):
        before = total
        total += f
        if f > 0 and total + 1e-9 >= capex:
            return (k - 1 + (capex - before) / f) / 4
    return None


def evaluate_team_case(data: Inputs, *,
                       switches=(False, False, False),
                       terms: TeamAssumptions | None = None) -> dict:
    """Run one fully linked Case B scenario; no independent NPV addition."""
    terms = terms or TeamAssumptions()
    terms.validate()
    l1, l2, l3 = switches
    full = deck_launches(data)
    # No L1: use the 20 *informally interested* cafés as a generous scenario
    # for consent, not signed commitments. With L1: team assumes all 60 opt in.
    plans = build_participation_plans(
        full, data,
        ParticipationTerms(
            interested_conversion=terms.base_interest_consent,
            additional_conversion_with_finance=1.0,
            incremental_financing_uptake=terms.loan_uptake))
    launch = full if l1 else plans["baseline"]
    funded = allocate_team_advances(launch, terms.loan_uptake) if l1 else {}
    first_q = [0.] * (PROGRAM_Q + 1)
    fees_q = [0.] * (PROGRAM_Q + 1)
    royalties_q = [0.] * (PROGRAM_Q + 1)
    loans_q = [0.] * (PROGRAM_Q + 1)
    repay_q = [0.] * (PROGRAM_Q + 1)
    interest_q = [0.] * (PROGRAM_Q + 1)
    cac_q = [0.] * (PROGRAM_Q + 1)
    slot_cost_q = [0.] * (PROGRAM_Q + 1)
    active = len(launch) > 0
    setup_hq_case = data.rule("corp_hq_setup") if active else 0.
    setup_portal = terms.portal_hq_setup if active else 0.
    one_time_landlord = terms.landlord_extra_setup if (active and l2) else 0.
    onetime = setup_hq_case + setup_portal + one_time_landlord
    first_q[0] -= onetime
    annual_fixed = data.rule("corp_hq_annual") if active else 0.
    for q in range(1, PROGRAM_Q + 1):
        first_q[q] -= annual_fixed / 4
        if l2:
            first_q[q] -= terms.landlord_extra_annual / 4

    signups_per_cafe = {}
    steady_extra = 0.
    for t, n_partners in zip(TYPES, terms.landlord_partners):
        # Full-network partners proportional to the number of activated
        # stores. This permits fractional expected signups for planning.
        signups_per_cafe[t] = (n_partners * terms.introductions_per_partner
                              * terms.conversion_of_intros
                              / data.get(t, "candidates") if l2 else 0.)
    loan_schedule = []
    store_rows = []
    actual_funded = 0
    total_owner_npv = 0.
    owner_failures = 0
    total_annual_sales = 0.
    negative_owner_cash_periods = 0
    advanced = 0.
    fully_recovered_loans = 0
    all_loan_interest = 0.
    all_loan_principal = 0.
    for idx, cohort in enumerate(launch):
        t = cohort.typ
        case_accounts = (data.get(t, "accounts_min") +
                         data.get(t, "accounts_max")) / 2
        new_accounts = signups_per_cafe[t]
        accounts = case_accounts + new_accounts
        rate_loss = terms.no_slots_sales_leakage if not l3 else 0.
        annual_sales = accounts * data.get(t, "orders_per_week") * (
            data.get(t, "cups_per_order") * data.get(t, "weeks_year")
            * data.get(t, "cup_price")) * (1 - rate_loss)
        nominal_annual_sales = accounts * data.get(t, "orders_per_week") * (
            data.get(t, "cups_per_order") * data.get(t, "weeks_year")
            * data.get(t, "cup_price"))
        total_annual_sales += annual_sales * cohort.count
        steady_extra += new_accounts * cohort.count
        capex = data.get(t, "capex_corp")
        n_funded = funded.get(idx, 0)
        actual_funded += n_funded
        if n_funded > cohort.count:
            raise AssertionError("Financed stores exceed cohort")
        if l2:
            cac_q[cohort.quarter] += (
                cohort.count * new_accounts * terms.acquisition_cost_per_account)
        if l3:
            slot_cost_q[cohort.quarter] += (
                cohort.count * terms.slot_setup_per_cafe)
        if n_funded:
            advance_amount = capex * n_funded
            loans_q[cohort.quarter] += advance_amount
            advanced += advance_amount
        for is_funded, count in ((True, n_funded),
                                 (False, cohort.count - n_funded)):
            if not count:
                continue
            owner_capital = capex * (0 if is_funded else 1)
            principal = capex if is_funded else 0.
            arrears = 0.
            pre_fee_cumulative_operating = 0.
            owner_npv = -owner_capital
            debt_zero = 0. if not is_funded else None
            operating_flows = []
            fee_first_k = None
            for k in range(1, PROGRAM_Q + 1):
                global_q = cohort.quarter + k
                ramp = terms.first_quarter_sales_ramp if k == 1 else 1.
                revenue = annual_sales / 4 * ramp
                # Only the first operating quarter is revenue-ramped;
                # platform subscription cost applies to entire quarter.
                before_fee = (
                    revenue * data.get(t, "corp_contrib")
                    - terms.portal_owner_annual / 4
                    - (terms.slot_annual_per_cafe / 4 if l3 else 0.))
                fee_live = pre_fee_cumulative_operating + 1e-8 >= capex
                extra_program_fee = (
                    revenue * terms.team_supporting_fee if fee_live else 0.)
                if extra_program_fee and fee_first_k is None:
                    fee_first_k = k
                owner_operating_net = before_fee - extra_program_fee
                operating_flows.append(owner_operating_net)
                pre_fee_cumulative_operating += before_fee
                interest_due = (principal * terms.annual_loan_interest / 4
                                if is_funded else 0.) + arrears
                repayment_capacity = max(0., owner_operating_net) * terms.loan_sweep
                payment = (min(principal + interest_due, repayment_capacity)
                           if is_funded else 0.)
                interest_paid = min(payment, interest_due)
                principal_paid = payment - interest_paid
                principal = max(0., principal - principal_paid)
                arrears = max(0., interest_due - interest_paid)
                if is_funded and debt_zero is None and principal + arrears < 1e-8:
                    debt_zero = k / 4
                owner_cash = owner_operating_net - payment
                if owner_cash < -1e-7:
                    negative_owner_cash_periods += count
                owner_npv += owner_cash / (1 + data.rule("discount")) ** (k / 4)
                if global_q <= PROGRAM_Q:
                    royalties_q[global_q] += (
                        revenue * data.rule("royalty") * count)
                    fees_q[global_q] += extra_program_fee * count
                    interest_q[global_q] += interest_paid * count
                    repay_q[global_q] += principal_paid * count
                    # Optional annual slot operating expense is borne by
                    # franchisees above, not HQ; do not charge it a second time.
                loan_schedule.append({
                    "type": t, "launch_q": cohort.quarter,
                    "financed": is_funded, "stores": count,
                    "operating_q": k, "global_q": global_q,
                    "owner_revenue_per_store": round(revenue, 4),
                    "before_fee_owner_operating_per_store": round(before_fee, 4),
                    "fee_charged_per_store": round(extra_program_fee, 4),
                    "principal_paid_per_store": round(principal_paid, 4),
                    "interest_paid_per_store": round(interest_paid, 4),
                    "owner_retained_cash_per_store": round(owner_cash, 4),
                    "closing_loan_principal_per_store": round(principal, 4),
                    "closing_interest_arrears_per_store": round(arrears, 4),
                    "inside_hq_horizon": global_q <= PROGRAM_Q,
                })
            owner_npv -= ((principal + arrears) /
                          (1 + data.rule("discount")) ** 5)
            total_owner_npv += owner_npv * count
            owner_operating_payback = _payback(capex, operating_flows)
            if owner_operating_payback is None or owner_operating_payback > 3:
                owner_failures += count
            store_rows.append({
                "type": t, "launch_q": cohort.quarter,
                "stores": count, "financed": is_funded,
                "original_case_accounts_per_store": case_accounts,
                "new_landlord_accounts_per_store": round(new_accounts, 5),
                "total_accounts_per_store": round(accounts, 5),
                "annual_corporate_sales_per_store": round(annual_sales, 2),
                "annual_sales_at_full_case_demand_per_store":
                    round(nominal_annual_sales, 2),
                "annual_owner_operating_before_fee_per_store":
                    round(annual_sales * data.get(t, "corp_contrib")
                          - terms.portal_owner_annual
                          - (terms.slot_annual_per_cafe if l3 else 0.), 2),
                "owner_capex_original_per_store": capex,
                "operating_capex_payback_years": owner_operating_payback,
                "first_program_fee_operating_q": fee_first_k,
                "loan_payback_years": debt_zero,
                "owner_npv_5y_per_store": round(owner_npv, 2),
                "remaining_principal_after_owner_5y_per_store":
                    round(principal, 2),
            })
    for q in range(PROGRAM_Q + 1):
        first_q[q] += royalties_q[q] + fees_q[q]
        first_q[q] -= loans_q[q]
        first_q[q] += repay_q[q] + interest_q[q]
        first_q[q] -= cac_q[q] + slot_cost_q[q]
    if sum(interest_q) < -1e-8:
        raise AssertionError("Negative loan interest")
    annual_results = []
    running = 0.
    payback_q = None
    cash_4y = None
    peak_draw = 0.
    for q in range(PROGRAM_Q + 1):
        running += first_q[q]
        peak_draw = max(peak_draw, -running)
        if q == 16:
            cash_4y = running
        if q > 0 and payback_q is None and running >= -1e-8:
            payback_q = q / 4
        annual_results.append({
            "q": q, "calendar_year": (2027 if q == 0
                                    else 2027 + (q - 1) // 4),
            "hq_royalty": round(royalties_q[q], 2),
            "hq_program_fee_common_policy": round(fees_q[q], 2),
            "hq_recurring_common_cost": round(
                annual_fixed / 4 if q else 0, 2),
            "hq_loan_advances": round(loans_q[q], 2),
            "hq_loan_principal_receipts": round(repay_q[q], 2),
            "hq_loan_interest_receipts": round(interest_q[q], 2),
            "hq_landlord_cac": round(cac_q[q], 2),
            "hq_slot_setup_and_running_cost": round(slot_cost_q[q], 2),
            "hq_net_cash": round(first_q[q], 2),
            "hq_cumulative_net_cash": round(running, 2)
        })
    fee_total = sum(fees_q)
    royalty_total = sum(royalties_q)
    gross_y1 = (onetime + annual_fixed + (terms.landlord_extra_annual if l2 else 0)
                + sum(loans_q[:4]) + sum(cac_q[:4]) + sum(slot_cost_q[:4]))
    gross_3y = (onetime + 3 * (annual_fixed +
                (terms.landlord_extra_annual if l2 else 0))
                + sum(loans_q[:12]) + sum(cac_q[:12])
                + sum(slot_cost_q[:12]))
    full_counts = {t: sum(c.count for c in launch if c.typ == t)
                   for t in TYPES}
    summary = {
        "scenario": f"L1{int(l1)}_L2{int(l2)}_L3{int(l3)}",
        "L1_cash_advance": l1, "L2_landlord": l2, "L3_fixed_slots": l3,
        "strategy": "B Corporate Accounts only",
        "case_confirmed_franchisee_consents": "UNKNOWN",
        "case_informal_interest": 20,
        "base_interest_consent_assumed": terms.base_interest_consent,
        "participating_cafes": sum(c.count for c in launch),
        "participating_downtown": full_counts["Downtown"],
        "participating_university": full_counts["University"],
        "participating_suburban": full_counts["Suburban"],
        "new_cafes_enabled_by_L1": (sum(c.count for c in launch)
                                      - sum(c.count for c in plans["baseline"])),
        "financed_cafes": actual_funded,
        "gross_hq_loan_advances": round(advanced, 2),
        "principal_recovered_by_2031": round(sum(repay_q), 2),
        "interest_received_by_2031": round(sum(interest_q), 2),
        "total_landlord_new_accounts": round(steady_extra, 4),
        "annual_store_sales_steady_state": round(total_annual_sales, 2),
        "annual_hq_royalty_steady_state": round(
            total_annual_sales * data.rule("royalty"), 2),
        "hq_royalty_cash_through_2031": round(royalty_total, 2),
        "hq_common_program_fee_through_2031": round(fee_total, 2),
        "hq_5y_npv": round(_npv(first_q, data.rule("discount")), 2),
        "hq_net_cash_end_2031": round(sum(first_q), 2),
        "hq_payback_years": payback_q,
        "hq_4y_net_cash": round(cash_4y, 2),
        "hq_4y_payback_met": cash_4y >= -1e-8,
        "hq_gross_spending_2027": round(gross_y1, 2),
        "hq_gross_spending_2027_2029": round(gross_3y, 2),
        "hq_spending_budget_2027_met": gross_y1 <= data.rule("year1_budget")+1e-8,
        "hq_spending_budget_3y_met": gross_3y <= data.rule("budget_total")+1e-8,
        "head_office_peak_cash_exposure": round(peak_draw, 2),
        "budget_unused_3y": round(data.rule("budget_total")-gross_3y, 2),
        "separate_extra_reserve_not_approved": data.rule("budget_reserve"),
        "hq_program_setup_common": round(setup_hq_case, 2),
        "hq_portal_setup_common": round(setup_portal, 2),
        "hq_coordination_cost_per_year_common": annual_fixed,
        "owner_portal_cost_per_store_per_year_common": terms.portal_owner_annual,
        "shared_program_fee_rate": terms.team_supporting_fee,
        "hq_extra_landlord_cost_5yr": round(
            sum(cac_q) + (one_time_landlord if l2 else 0)
            + (5 * terms.landlord_extra_annual if l2 else 0), 2),
        "owner_combined_npv_5yr": round(total_owner_npv, 2),
        "owner_failing_original_capex_payback_3yr": owner_failures,
        "owner_negative_cash_quarters": negative_owner_cash_periods,
        "no_slots_at_risk_sales_assumed": terms.no_slots_sales_leakage,
        "slot_capacity_not_proven": True,
    }
    return {"summary": summary, "hq_quarters": annual_results,
            "owner_cohorts": store_rows, "loan_schedule": loan_schedule}


def team_slots_operational_metrics(data, terms: TeamAssumptions):
    """Physical workload implied by Case order counts; not validated capacity."""
    result = []
    for typ in TYPES:
        case_accounts = (data.get(typ, "accounts_min") +
                         data.get(typ, "accounts_max")) / 2
        new_per_cafe = (terms.landlord_partners[TYPES.index(typ)]
                        * terms.introductions_per_partner
                        * terms.conversion_of_intros / data.get(typ, "candidates"))
        for landlord_active, acc in ((False, case_accounts),
                                     (True, case_accounts + new_per_cafe)):
            orders_week = acc * data.get(typ, "orders_per_week")
            slots_week = terms.production_windows_per_day * terms.weekdays_per_week
            result.append({
                "cafe_type": typ, "landlord_pipeline_active": landlord_active,
                "total_expected_accounts_per_cafe": round(acc, 3),
                "orders_per_week_per_cafe": round(orders_week, 3),
                "cups_per_week_per_cafe": round(
                    orders_week * data.get(typ, "cups_per_order"), 3),
                "windows_per_day_assumed": terms.production_windows_per_day,
                "weekdays_per_week_assumed": terms.weekdays_per_week,
                "slots_per_week": slots_week,
                "average_corporate_orders_per_slot": round(
                    orders_week / slots_week, 3),
                "average_cups_per_slot": round(
                    orders_week * data.get(typ, "cups_per_order") / slots_week, 3),
                "capacity_verified": False,
                "service_target_minutes": data.rule("service_mins"),
                "satisfaction_target": data.rule("satisfaction"),
            })
    return result


def run_team_matrix(data, terms: TeamAssumptions | None = None):
    terms = terms or TeamAssumptions()
    results = [evaluate_team_case(data, switches=bits, terms=terms)
               for bits in product((False, True), repeat=3)]
    rows = []
    baseline = results[0]["summary"]["hq_5y_npv"]
    for r in results:
        s = dict(r["summary"])
        s["hq_incremental_npv_vs_B_only"] = round(s["hq_5y_npv"] - baseline, 2)
        rows.append(s)
    lookup = {s["scenario"]: s for s in rows}
    order = ("L10_L20_L30", "L11_L20_L30",
             "L11_L21_L30", "L11_L21_L31")
    waterfall = []
    previous = None
    for scenario in order:
        s = lookup[scenario]
        waterfall.append({
            "scenario": scenario,
            "stage": ("Strategy B only" if previous is None else
                      "Add " + ("L1 Cash Advance" if scenario == order[1] else
                                "L2 Landlord" if scenario == order[2] else
                                "L3 Fixed Slots")),
            "participating_cafes": s["participating_cafes"],
            "hq_5y_npv": s["hq_5y_npv"],
            "step_npv_increase": round(
                s["hq_5y_npv"] - previous["hq_5y_npv"], 2)
                if previous is not None else 0.,
            "total_npv_increase_vs_B": s["hq_incremental_npv_vs_B_only"],
            "hq_4y_payback_met": s["hq_4y_payback_met"],
            "hq_gross_spending_2027_2029": s["hq_gross_spending_2027_2029"],
        })
        previous = s
    return {"scenarios": rows, "waterfall": waterfall,
            "hq_quarters": [dict(r2, scenario=r["summary"]["scenario"])
                            for r in results for r2 in r["hq_quarters"]],
            "owners": [dict(r2, scenario=r["summary"]["scenario"])
                       for r in results for r2 in r["owner_cohorts"]],
            "loans": [dict(r2, scenario=r["summary"]["scenario"])
                      for r in results for r2 in r["loan_schedule"]],
            "slot_metrics": team_slots_operational_metrics(data, terms)}
