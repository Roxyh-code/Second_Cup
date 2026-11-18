
"""Deterministic sensitivity analysis for Second Cup strategies.

Run from repository root (PowerShell):
    $env:PYTHONPATH = "src"
    python -m secondcup.sensitivity

This tests Case Appendix A5/A6 planning ranges; it does NOT estimate
probabilities. No team-added 5% fee or advance interest is included.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .financial_engine import run_hq
from .inputs import Inputs, Overrides, ROOT, TYPES, load_rollouts
from .scenarios import cap_launches, get_launches


# (label, lower-bound key, upper-bound key, relevant business options)
DRIVERS = (
    (
        "Peak seat sell-through",
        "peak_sell_min",
        "peak_sell_max",
        {"Paid Reservations", "Operator Partnership"},
    ),
    (
        "Off-peak seat sell-through",
        "quiet_sell_min",
        "quiet_sell_max",
        {"Paid Reservations", "Operator Partnership"},
    ),
    (
        "Walk-in departure rate",
        "lost_walkin_min",
        "lost_walkin_max",
        {"Paid Reservations", "Operator Partnership", "Memberships"},
    ),
    (
        "Membership conversion",
        "member_conv_min",
        "member_conv_max",
        {"Memberships"},
    ),
    (
        "Member hours per month",
        "member_hours_min",
        "member_hours_max",
        {"Memberships"},
    ),
    (
        "Late-day transactions per day",
        "late_tx_min",
        "late_tx_max",
        {"Late-day Offer"},
    ),
    (
        "Corporate accounts per cafe",
        "accounts_min",
        "accounts_max",
        {"Corporate Accounts"},
    ),
)


DEFAULT_STRATEGIES = (
    "A Only",
    "A Full Network",
    "B Only",
    "Hybrid",
    "Hybrid - Optimized",
)


def save_csv(path: Path, records: list[dict]) -> None:
    """Save analysis results to CSV."""

    if not records:
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=list(records[0]),
        )

        writer.writeheader()
        writer.writerows(records)


def one_way_sensitivity(
    data: Inputs,
    strategies: list[str],
) -> list[dict]:
    """Vary one Case-range driver for one cafe type at a time.

    All other inputs remain at their Case midpoints.

    The low/high planning figures are not probability quantiles.
    """

    records = []

    for name in strategies:

        launches = get_launches(name)

        base = run_hq(
            name,
            launches,
            data,
        )

        for typ in TYPES:

            active_options = {
                launch.option
                for launch in launches
                if launch.count > 0 and launch.typ == typ
            }

            if not active_options:
                continue

            for (
                label,
                low_key,
                high_key,
                relevant_options,
            ) in DRIVERS:

                if not (active_options & relevant_options):
                    continue

                low = data.get(typ, low_key)
                high = data.get(typ, high_key)

                if low > high:
                    raise ValueError(
                        f"Invalid range for {typ}: {low_key}"
                    )

                results = {}

                for bound, sampled_value in (
                    ("low", low),
                    ("high", high),
                ):

                    # unit_economics uses midpoint(lo, hi).
                    # Set both keys to the chosen endpoint.

                    overrides = Overrides(
                        type_parameters={
                            typ: {
                                low_key: sampled_value,
                                high_key: sampled_value,
                            }
                        }
                    )

                    results[bound] = run_hq(
                        name,
                        launches,
                        data,
                        overrides,
                    )

                low_result = results["low"]
                high_result = results["high"]

                lo_npv = low_result.npv_5y
                hi_npv = high_result.npv_5y

                records.append({
                    "strategy": name,
                    "store_type": typ,
                    "driver": label,

                    "case_low": low,
                    "case_high": high,

                    "base_hq_npv": round(
                        base.npv_5y, 2
                    ),

                    "hq_npv_at_low": round(
                        lo_npv, 2
                    ),

                    "hq_npv_at_high": round(
                        hi_npv, 2
                    ),

                    "npv_swing": round(
                        abs(hi_npv - lo_npv), 2
                    ),

                    "worst_hq_npv": round(
                        min(lo_npv, hi_npv), 2
                    ),

                    "best_hq_npv": round(
                        max(lo_npv, hi_npv), 2
                    ),

                    "year4_cash_at_low": round(
                        low_result.cash_at_year4, 2
                    ),

                    "year4_cash_at_high": round(
                        high_result.cash_at_year4, 2
                    ),

                    "owner_failures_at_low":
                        low_result.owner_failing_3yr,

                    "owner_failures_at_high":
                        high_result.owner_failing_3yr,
                })

    return sorted(
        records,
        key=lambda r: (
            r["strategy"],
            -r["npv_swing"],
        ),
    )


def accounts_override(
    data: Inputs,
    position: float,
) -> Overrides:
    """Choose a position within each cafe type's account range.

    position=0: Case low
    position=0.5: Case midpoint
    position=1: Case high

    Fractional accounts per cafe represent planning averages.
    """

    if not 0 <= position <= 1:
        raise ValueError(
            "position must be in [0, 1]"
        )

    parameters = {}

    for typ in TYPES:

        low = data.get(
            typ,
            "accounts_min",
        )

        high = data.get(
            typ,
            "accounts_max",
        )

        value = low + position * (high - low)

        parameters[typ] = {
            "accounts_min": value,
            "accounts_max": value,
        }

    return Overrides(
        type_parameters=parameters
    )


def two_way_accounts_heatmap(
    data: Inputs,
    strategy: str = "B Only",
    counts: tuple[int, ...] = (
        20, 26, 30, 38, 44, 60
    ),
    positions: tuple[float, ...] = (
        0, 0.25, 0.5, 0.75, 1
    ),
) -> list[dict]:
    """Vary participating cafes and corporate accounts together.

    Counts use the earliest launches from the chosen schedule.

    The cafe-type mix changes when the count is reduced.

    This is not store optimization and does not include
    the teammate's enhanced 5% fee or loan model.
    """

    original = get_launches(strategy)

    max_cafes = sum(
        row.count for row in original
    )

    if not any(
        row.option == "Corporate Accounts"
        for row in original
    ):
        raise ValueError(
            "Heatmap strategy must include Corporate Accounts"
        )

    records = []

    for count in counts:

        if not 1 <= count <= max_cafes:
            raise ValueError(
                f"Store count must be 1..{max_cafes}: {count}"
            )

        subset = cap_launches(
            original,
            count,
        )

        mix = {
            typ: sum(
                row.count
                for row in subset
                if row.typ == typ
            )
            for typ in TYPES
        }

        for position in positions:

            result = run_hq(
                strategy,
                subset,
                data,
                accounts_override(
                    data,
                    position,
                ),
            )

            records.append({

                "strategy": strategy,

                "participating_cafes": count,

                "downtown_cafes":
                    mix["Downtown"],

                "university_cafes":
                    mix["University"],

                "suburban_cafes":
                    mix["Suburban"],

                "account_range_position":
                    position,

                "hq_npv": round(
                    result.npv_5y, 2
                ),

                "year4_cash": round(
                    result.cash_at_year4, 2
                ),

                "payback_years": (
                    ""
                    if result.payback_years is None
                    else result.payback_years
                ),

                "owner_failing_3yr":
                    result.owner_failing_3yr,

                "budget_and_rollout_valid": int(
                    result.feasible
                ),

                "meets_all_financial_targets": int(
                    result.feasible
                    and result.cash_at_year4 >= 0
                    and result.npv_5y >= 0
                    and result.owner_failing_3yr == 0
                ),
            })

    return records


def parse_ints(text: str) -> tuple[int, ...]:
    return tuple(
        int(item.strip())
        for item in text.split(",")
    )


def parse_floats(text: str) -> tuple[float, ...]:
    return tuple(
        float(item.strip())
        for item in text.split(",")
    )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--strategies",
        nargs="+",
        default=None,
    )

    parser.add_argument(
        "--heatmap-strategy",
        default="B Only",
    )

    parser.add_argument(
        "--counts",
        default="20,26,30,38,44,60",
    )

    parser.add_argument(
        "--account-positions",
        default="0,0.25,0.5,0.75,1",
    )

    args = parser.parse_args()

    available = load_rollouts()

    names = args.strategies or [
        name
        for name in DEFAULT_STRATEGIES
        if name in available
    ]

    unknown = [
        name
        for name in names + [args.heatmap_strategy]
        if name not in available
    ]

    if unknown:
        parser.error(
            f"Unknown strategies: {unknown}"
        )

    data = Inputs.from_file()

    # One-way sensitivity analysis
    one_way = one_way_sensitivity(
        data,
        names,
    )

    # Two-way sensitivity analysis
    two_way = two_way_accounts_heatmap(
        data,
        args.heatmap_strategy,
        counts=parse_ints(args.counts),
        positions=parse_floats(
            args.account_positions
        ),
    )

    output = ROOT / "outputs"

    save_csv(
        output / "sensitivity_one_way.csv",
        one_way,
    )

    save_csv(
        output / "sensitivity_two_way_accounts.csv",
        two_way,
    )

    print(
        "\n=== One-way sensitivity: "
        "top 3 NPV drivers per strategy ==="
    )

    for name in names:

        print(f"\n{name}")

        top = [
            row
            for row in one_way
            if row["strategy"] == name
        ][:3]

        for item in top:

            print(
                f"  {item['store_type']:10} "
                f"{item['driver']:30} "
                f"NPV swing: "
                f"${item['npv_swing']:,.0f}"
            )

    print(
        f"\n=== Two-way sensitivity: "
        f"{args.heatmap_strategy} ==="
    )

    print(
        "Row: cafe count; column: "
        "position in each cafe type's account range"
    )

    positions = parse_floats(
        args.account_positions
    )

    print(
        "Cafes  "
        + " ".join(
            f"{p:>11.0%}"
            for p in positions
        )
    )

    for count in parse_ints(args.counts):

        subset = [
            row
            for row in two_way
            if row["participating_cafes"] == count
        ]

        print(
            f"{count:>5}  "
            + " ".join(
                f"{x['hq_npv']/1000:>+10.1f}k"
                for x in subset
            )
        )

    print(
        f"\nSaved: "
        f"{output / 'sensitivity_one_way.csv'}"
    )

    print(
        f"Saved: "
        f"{output / 'sensitivity_two_way_accounts.csv'}"
    )

    print(
        "Note: this is deterministic scenario testing, "
        "NOT success probabilities."
    )


if __name__ == "__main__":
    main()
