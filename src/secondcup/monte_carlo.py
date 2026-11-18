
"""Paired Monte Carlo comparison of Second Cup rollout scenarios.

Run from the project root (PowerShell):
    $env:PYTHONPATH = "src"
    python -m secondcup.monte_carlo --trials 10000 --seed 42

The Case reports planning ranges, not observed probability distributions.
Triangular / uniform distributions below are explicit modelling assumptions.
Each draw is for a cafe type, not an observed individual store.
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path
from statistics import mean, median

from .financial_engine import run_hq
from .inputs import Inputs, Overrides, ROOT, TYPES, load_rollouts
from .scenarios import get_launches


# Each source pair is replaced with one sampled value in a trial.
# This works with unit_economics.py's midpoint(...) calculations.

RANGES = (
    ("peak_sell_min", "peak_sell_max"),
    ("quiet_sell_min", "quiet_sell_max"),
    ("lost_walkin_min", "lost_walkin_max"),
    ("member_conv_min", "member_conv_max"),
    ("member_hours_min", "member_hours_max"),
    ("late_tx_min", "late_tx_max"),
    ("accounts_min", "accounts_max"),
)


DEFAULT_STRATEGIES = (
    "A Only",
    "A Full Network",
    "B Only",
    "Hybrid",
    "Hybrid - Optimized",
)


def draw_inputs(
    data: Inputs,
    rng: random.Random,
    distribution: str,
) -> Overrides:
    """Sample one set of uncertain inputs for all strategies."""

    type_parameters = {}

    for typ in TYPES:
        params = {}

        for low_key, high_key in RANGES:

            low = data.get(typ, low_key)
            high = data.get(typ, high_key)

            if low > high:
                raise ValueError(
                    f"Invalid interval: {typ}/{low_key}"
                )

            if distribution == "triangular":
                sample = rng.triangular(
                    low,
                    high,
                    (low + high) / 2,
                )

            elif distribution == "uniform":
                sample = rng.uniform(low, high)

            else:
                raise ValueError(
                    "distribution must be triangular or uniform"
                )

            params[low_key] = sample
            params[high_key] = sample

        type_parameters[typ] = params

    return Overrides(type_parameters=type_parameters)


def percentile(
    values: list[float],
    probability: float,
) -> float:
    """Calculate a percentile using linear interpolation."""

    if not values or not 0 <= probability <= 1:
        raise ValueError(
            "Invalid values/probability for percentile"
        )

    sorted_values = sorted(values)
    pos = probability * (len(sorted_values) - 1)

    lower = int(pos)
    upper = min(lower + 1, len(sorted_values) - 1)

    return sorted_values[lower] + (pos - lower) * (
        sorted_values[upper] - sorted_values[lower]
    )


def write_csv(path: Path, records: list[dict]) -> None:
    """Save simulation results to CSV."""

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
            fieldnames=list(records[0].keys()),
        )

        writer.writeheader()
        writer.writerows(records)


def run_simulation(
    trials: int = 10_000,
    seed: int = 42,
    distribution: str = "triangular",
    strategies: list[str] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Run paired Monte Carlo simulations for all strategies."""

    if trials < 1:
        raise ValueError("trials must be >= 1")

    data = Inputs.from_file()
    available = load_rollouts()

    if strategies is None:

        strategies = [
            s for s in DEFAULT_STRATEGIES
            if s in available
        ]

        missing = [
            s for s in DEFAULT_STRATEGIES
            if s not in available
        ]

        if missing:
            print(
                "Skipped scenarios not found in "
                "rollout_plans.json:",
                missing,
            )

    else:

        missing = [
            s for s in strategies
            if s not in available
        ]

        if missing:
            raise ValueError(
                f"Unknown strategies: {missing}"
            )

    if not strategies:
        raise ValueError(
            "No valid rollout scenarios found"
        )

    launches_by_strategy = {
        name: get_launches(name)
        for name in strategies
    }

    rng = random.Random(seed)

    rows = []
    winners = []

    for trial in range(1, trials + 1):

        # Use the SAME sampled inputs for every strategy
        # within a trial, ensuring paired comparison.

        overrides = draw_inputs(
            data,
            rng,
            distribution,
        )

        results = {
            name: run_hq(
                name,
                launches,
                data,
                overrides,
            )
            for name, launches in launches_by_strategy.items()
        }

        eligible = []

        for name, result in results.items():

            four_year = (
                result.cash_at_year4 >= -1e-8
            )

            owners_ok = (
                result.owner_failing_3yr == 0
            )

            npv_positive = (
                result.npv_5y >= 0
            )

            # Success requires all financial and
            # rollout/budget conditions to be met.

            success = (
                result.feasible
                and owners_ok
                and four_year
                and npv_positive
            )

            if success:
                eligible.append(name)

            rows.append({
                "trial": trial,
                "strategy": name,
                "cafes": result.launched_cafes,
                "hq_npv": result.npv_5y,
                "cash_at_year4": result.cash_at_year4,

                "simple_payback_years": (
                    ""
                    if result.payback_years is None
                    else result.payback_years
                ),

                "owner_failing_3yr":
                    result.owner_failing_3yr,

                "rollout_budget_feasible":
                    int(result.feasible),

                "npv_nonnegative":
                    int(npv_positive),

                "cash_positive_by_year4":
                    int(four_year),

                "all_owners_meet_3yr":
                    int(owners_ok),

                "all_targets_met":
                    int(success),
            })

        # Select highest-NPV strategy among those
        # meeting all financial requirements.

        winner = (
            max(
                eligible,
                key=lambda name: results[name].npv_5y,
            )
            if eligible
            else "None"
        )

        winners.append({
            "trial": trial,
            "best_feasible_strategy": winner,
        })

    # Summarize results by strategy.

    summary = []

    for name in strategies:

        group = [
            row for row in rows
            if row["strategy"] == name
        ]

        npvs = [
            float(row["hq_npv"])
            for row in group
        ]

        summary.append({

            "strategy": name,

            "cafes": group[0]["cafes"],

            "trials": trials,

            "mean_hq_npv": mean(npvs),

            "median_hq_npv": median(npvs),

            "p05_hq_npv": percentile(
                npvs, 0.05
            ),

            "p95_hq_npv": percentile(
                npvs, 0.95
            ),

            "share_negative_npv": (
                sum(x < 0 for x in npvs) / trials
            ),

            "share_hq_cash_positive_by_year4": mean(
                row["cash_positive_by_year4"]
                for row in group
            ),

            "share_all_owners_meet_3yr": mean(
                row["all_owners_meet_3yr"]
                for row in group
            ),

            "share_all_targets_met": mean(
                row["all_targets_met"]
                for row in group
            ),

            "share_best_feasible": (
                sum(
                    x["best_feasible_strategy"] == name
                    for x in winners
                ) / trials
            ),
        })

    return rows, summary, winners


def main() -> None:

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--trials",
        type=int,
        default=10_000,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    parser.add_argument(
        "--distribution",
        choices=("triangular", "uniform"),
        default="triangular",
    )

    parser.add_argument(
        "--strategies",
        nargs="+",
        default=None,
        help=(
            'Optional names, e.g. '
            '--strategies "A Only" "Hybrid - Optimized"'
        ),
    )

    args = parser.parse_args()

    rows, summary, winners = run_simulation(
        trials=args.trials,
        seed=args.seed,
        distribution=args.distribution,
        strategies=args.strategies,
    )

    output = ROOT / "outputs"

    write_csv(
        output / "monte_carlo_trials.csv",
        rows,
    )

    write_csv(
        output / "monte_carlo_summary.csv",
        summary,
    )

    write_csv(
        output / "monte_carlo_winners.csv",
        winners,
    )

    print("\n=== Monte Carlo Simulation ===")

    print(
        f"Trials: {args.trials:,} | "
        f"Distribution: {args.distribution} | "
        f"Seed: {args.seed}"
    )

    print(
        "\nStrategy                  Mean HQ NPV"
        "   P(NPV<0)   P(4yr cash>=0)  P(all targets)"
    )

    print("-" * 88)

    for item in summary:

        print(
            f"{item['strategy']:<25}"
            f"${item['mean_hq_npv']:>11,.0f}"
            f"  {item['share_negative_npv']:>8.1%}"
            f"  {item['share_hq_cash_positive_by_year4']:>15.1%}"
            f"  {item['share_all_targets_met']:>13.1%}"
        )

    counts = Counter(
        row["best_feasible_strategy"]
        for row in winners
    )

    print(
        "\nBest feasible strategy by trial "
        "(including 'None'):"
    )

    for name, count in counts.most_common():

        print(
            f"  {name}: {count / args.trials:.1%}"
        )

    print(
        f"\nCSV results saved in: {output}"
    )

    print(
        "CAUTION: Shares are conditional on assumed "
        "parameter distributions, not empirically "
        "calibrated probabilities."
    )


if __name__ == "__main__":
    main()
