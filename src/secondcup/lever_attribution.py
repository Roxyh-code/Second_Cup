"""Counterfactual attribution for the three optional Strategy B enablers.

Common Strategy B costs ($40k setup, $90k/year sales coordination) remain
inside EVERY scenario total NPV; they cancel when calculating lever deltas.
Standalone deltas, order-specific waterfall and order-neutral Shapley values
answer DIFFERENT questions and must not be added indiscriminately.

Case A8 early interest is NOT signed consent. The default adoption comparator
assumes 20 of 20 interested cafes eventually opt in without financing;
L1 enables 27 additional cafes conditionally on a 2/3 conversion assumption.
"""
from __future__ import annotations

from itertools import combinations
from math import factorial, isclose

from .financial_engine import fixed_hq_costs
from .inputs import Inputs

NAMES = ("L1 Financing", "L2 Landlord", "L3 Deferred Fee")
BITS = (1, 2, 4)
ZERO = (False, False, False)
FULL = (True, True, True)


def scenario_key(lever_on):
    """Return the established L10_L20_L30 naming convention."""
    a, b, c = lever_on
    return f"L1{int(a)}_L2{int(b)}_L3{int(c)}"


def _to_mask(row):
    return (int(bool(row["L1"])) | (int(bool(row["L2"])) << 1)
            | (int(bool(row["L3"])) << 2))


def attribute_levers(rows, launches, data: Inputs, *, strategy="B Only",
                     require_participation_uplift=True):
    """Break out common Strategy B cost and true lever incremental HQ value.

    rows: all 8 scenario result dictionaries returned by run_grid().
    No hypothetical cost is reassigned from Strategy B to L1/L2/L3.
    """
    if strategy != "B Only":
        raise ValueError("This bridge compares Corporate Accounts Strategy B only")
    if len(rows) != 8:
        raise ValueError("Expected exactly eight switch combinations")
    by_mask = {}
    for row in rows:
        mask = _to_mask(row)
        if mask in by_mask:
            raise ValueError("Duplicate lever combination")
        if require_participation_uplift and not row["participation_uplift_mode"]:
            raise ValueError("Use --participation-uplift for consent-aware attribution")
        by_mask[mask] = row
    if set(by_mask) != set(range(8)):
        raise ValueError("Missing lever combinations")
    if not any(x.option == "Corporate Accounts" and x.count for x in launches):
        raise ValueError("Case B plan requires at least one Corporate Accounts launch")

    setup, annual = fixed_hq_costs(launches, data)
    expected_setup = data.rule("corp_hq_setup")
    expected_annual = data.rule("corp_hq_annual")
    if not (isclose(setup, expected_setup) and isclose(annual, expected_annual)):
        raise ValueError("Common Strategy B costs do not reconcile with Case A7")
    # In this B-only implementation, the original Case fixed cost is incurred
    # in every active scenario even as participating cafe count changes.
    discount = data.rule("discount")
    coordination_pv = sum(annual / 4 / (1 + discount) ** (q / 4)
                          for q in range(1, 21))
    fixed_cost_pv = setup + coordination_pv
    f = {mask: float(row["hq_npv_5y"]) for mask, row in by_mask.items()}
    baseline_npv = f[0]
    total_gain = f[7] - baseline_npv

    # Marginal effect when a lever alone is added to the same Strategy B base.
    isolated = []
    for i, bit in enumerate(BITS):
        row = by_mask[bit]
        isolated.append({
            "lever": NAMES[i],
            "scenario": row["scenario"],
            "base_case_npv": round(baseline_npv, 2),
            "strategy_b_plus_lever_npv": round(f[bit], 2),
            "isolated_incremental_npv": round(f[bit] - baseline_npv, 2),
            "extra_participating_cafes_vs_base":
                row["corporate_cafes"] - by_mask[0]["corporate_cafes"],
            "gross_spend_2027_2029":
                row["hq_gross_spend_2027_2029"],
            "hq_four_year_target_met": row["hq_four_year_target_met"],
            "case_setup_cost_increment": 0.0,
            "case_coordination_cost_increment": 0.0,
        })

    # Waterfall in the user's chosen business narrative: B -> L1 -> L2 -> L3.
    waterfall = []
    path = [(0, "Strategy B only", "Strategy B baseline"),
            (1, "Add L1", NAMES[0]),
            (3, "Add L2 after L1", NAMES[1]),
            (7, "Add L3 after L1+L2", NAMES[2])]
    previous = 0
    for idx, (mask, stage, lever) in enumerate(path):
        value = f[mask]
        waterfall.append({
            "step": idx, "stage": stage, "new_lever": lever if idx else "",
            "scenario": by_mask[mask]["scenario"],
            "active_cafes": by_mask[mask]["corporate_cafes"],
            "hq_npv": round(value, 2),
            "marginal_incremental_npv":
                round(value - f[previous], 2) if idx else 0.0,
            "cumulative_increase_vs_strategy_b": round(value - baseline_npv, 2),
            "gross_spend_2027_2029": by_mask[mask]["hq_gross_spend_2027_2029"],
            "hq_four_year_target_met": by_mask[mask]["hq_four_year_target_met"],
        })
        previous = mask

    # Order-neutral Shapley attribution across all 3! = 6 permutations.
    shapley = []
    exact_shapley = []
    n = 3
    for i, bit in enumerate(BITS):
        allocation = 0.0
        for subset in range(8):
            if subset & bit:
                continue
            k = subset.bit_count()
            weight = factorial(k) * factorial(n - k - 1) / factorial(n)
            allocation += weight * (f[subset | bit] - f[subset])
        exact_shapley.append(allocation)
        shapley.append({
            "lever": NAMES[i],
            "shapley_npv_contribution": round(allocation, 2),
            "isolated_incremental_npv": isolated[i]["isolated_incremental_npv"],
            "average_contribution_when_added_in_all_orderings": True,
        })
    if not isclose(sum(exact_shapley), total_gain, abs_tol=0.04):
        raise AssertionError("Shapley bridge fails to reconcile to total uplift")

    # Pairwise effects and the remaining pure three-way term.
    interactions = []
    for i, j in combinations(range(3), 2):
        a, b = BITS[i], BITS[j]
        interaction = f[a | b] - f[a] - f[b] + baseline_npv
        interactions.append({
            "interaction": NAMES[i] + " × " + NAMES[j],
            "two_lever_synergy_npv": round(interaction, 2),
        })
    total_synergy = total_gain - sum(f[bit] - baseline_npv for bit in BITS)
    third_order = total_synergy - sum(x["two_lever_synergy_npv"]
                                     for x in interactions)
    interactions.append({
        "interaction": "Three-way residual (L1 × L2 × L3)",
        "two_lever_synergy_npv": round(third_order, 2),
    })

    scenarios = []
    for mask in range(8):
        row = by_mask[mask]
        scenarios.append({
            "scenario": row["scenario"],
            "L1_enabled": row["L1"],
            "L2_enabled": row["L2"],
            "L3_enabled": row["L3"],
            "participating_cafes": row["corporate_cafes"],
            "incremental_cafes_vs_B": (
                row["corporate_cafes"] - by_mask[0]["corporate_cafes"]),
            "incremental_landlord_accounts": row["landlord_incremental_accounts"],
            "hq_case_setup_cost": round(setup, 2),
            "hq_case_annual_coordination_cost": round(annual, 2),
            "pv_common_strategy_b_fixed_cost": round(-fixed_cost_pv, 2),
            "hq_npv_before_common_B_fixed_cost": round(f[mask] + fixed_cost_pv, 2),
            "hq_npv_5y": round(f[mask], 2),
            "incremental_hq_npv_vs_B_only": round(f[mask] - baseline_npv, 2),
            "owner_npv_after_fee_total": row["owner_npv_after_fee_total"],
            "hq_fee_received_by_2031": row["hq_fee_received_by_2031"],
            "hq_spend_2027_2029": row["hq_gross_spend_2027_2029"],
            "hq_four_year_target_met": row["hq_four_year_target_met"],
            "hq_budget_3y_met": row["budget_3y_met"],
            "hq_500k_reserve_diagnostic_met": row["reserve_target_diagnostic_met"],
        })

    return {
        "summary": {
            "strategy": strategy,
            "source_case_consent": "UNKNOWN - informal interest is not consent",
            "baseline_assumed_participating_cafes":
                by_mask[0]["corporate_cafes"],
            "full_combo_participating_cafes": by_mask[7]["corporate_cafes"],
            "strategy_b_only_npv": round(baseline_npv, 2),
            "all_three_levers_npv": round(f[7], 2),
            "all_three_incremental_npv": round(total_gain, 2),
            "isolated_lever_gain_sum": round(
                sum(f[bit] - baseline_npv for bit in BITS), 2),
            "interaction_gain_total": round(total_synergy, 2),
            "shapley_attribution_sum": round(sum(exact_shapley), 2),
            "strategy_b_setup_cost": round(setup, 2),
            "strategy_b_coordination_cost_per_year": round(annual, 2),
            "pv_common_strategy_b_cost": round(-fixed_cost_pv, 2),
            "case_fixed_cost_added_by_each_lever": 0.0,
            "basis": "L1 consent uplift is hypothetical; L2 funnel and L3 fee are proposals",
            "shapley_definition": "Order-neutral average marginal HQ NPV contribution",
        },
        "scenarios": scenarios,
        "isolated": isolated,
        "waterfall": waterfall,
        "shapley": shapley,
        "interactions": interactions,
    }
