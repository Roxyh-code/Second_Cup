
"""Generate charts for Second Cup Monte Carlo and sensitivity analysis.

Run from project root:

    $env:PYTHONPATH = "src"
    python -m secondcup.plots

Requires:
    matplotlib

Input CSV files:
    outputs/monte_carlo_trials.csv
    outputs/sensitivity_one_way.csv
    outputs/sensitivity_two_way_accounts.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from .inputs import ROOT


OUTPUT = ROOT / "outputs"


# --------------------------------------------------
# 1. Read CSV
# --------------------------------------------------

def read_rows(
    path: Path,
    required: set[str],
) -> list[dict[str, str]]:

    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path.name}. "
            "Run monte_carlo.py and sensitivity.py first."
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        missing = required - set(reader.fieldnames or [])

        if missing:
            raise ValueError(
                f"{path.name} is missing columns: "
                f"{sorted(missing)}"
            )

        rows = list(reader)

    if not rows:
        raise ValueError(
            f"{path.name} contains no data rows"
        )

    return rows


# --------------------------------------------------
# 2. Monte Carlo NPV Distribution
# --------------------------------------------------

def plot_npv_distribution(
    rows: list[dict[str, str]],
    path: Path,
) -> None:

    groups = defaultdict(list)

    for row in rows:

        groups[row["strategy"]].append(
            float(row["hq_npv"]) / 1000
        )

    preferred = [
        "A Only",
        "A Full Network",
        "B Only",
        "Hybrid",
        "Hybrid - Optimized",
    ]

    names = [
        s for s in preferred
        if s in groups
    ]

    names += sorted(
        set(groups) - set(names)
    )

    all_values = np.array([
        value
        for values in groups.values()
        for value in values
    ])

    edges = np.linspace(
        all_values.min() - 1,
        all_values.max() + 1,
        61,
    )

    fig, ax = plt.subplots(
        figsize=(10, 6)
    )

    for name in names:

        ax.hist(
            groups[name],
            bins=edges,
            density=True,
            histtype="step",
            linewidth=2,
            label=name,
        )

    ax.axvline(
        0,
        linestyle="--",
        linewidth=1.5,
        label="NPV = 0",
    )

    ax.set(
        title="Head-office NPV: Monte Carlo Comparison",
        xlabel="Five-year HQ NPV (CAD $ thousands)",
        ylabel="Simulated Probability Density",
    )

    ax.legend(fontsize=9)
    ax.grid(alpha=0.2)

    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


# --------------------------------------------------
# 3. One-Way Sensitivity Tornado Chart
# --------------------------------------------------

def plot_tornado(
    rows: list[dict[str, str]],
    strategy: str,
    path: Path,
    top: int = 8,
) -> None:

    selected = [
        r for r in rows
        if r["strategy"] == strategy
    ]

    if not selected:

        available = sorted({
            r["strategy"]
            for r in rows
        })

        raise ValueError(
            f"No one-way data for {strategy!r}. "
            f"Available: {available}"
        )

    selected.sort(
        key=lambda r: float(r["npv_swing"]),
        reverse=True,
    )

    selected = selected[:top][::-1]

    labels = [
        f"{r['store_type']} | {r['driver']}"
        for r in selected
    ]

    low = np.array([
        float(r["hq_npv_at_low"]) / 1000
        for r in selected
    ])

    high = np.array([
        float(r["hq_npv_at_high"]) / 1000
        for r in selected
    ])

    base = (
        float(selected[0]["base_hq_npv"])
        / 1000
    )

    y = np.arange(len(selected))

    fig, ax = plt.subplots(
        figsize=(
            11,
            max(5, len(selected) * 0.63 + 1.7),
        )
    )

    ax.barh(
        y - 0.18,
        low - base,
        left=base,
        height=0.34,
        label="Case Low",
    )

    ax.barh(
        y + 0.18,
        high - base,
        left=base,
        height=0.34,
        label="Case High",
    )

    ax.axvline(
        base,
        linestyle="--",
        linewidth=1.5,
        label=f"Base NPV ${base:,.1f}k",
    )

    ax.set_yticks(y, labels)

    ax.set(
        title=f"One-Way Sensitivity | {strategy}",
        xlabel="Five-year HQ NPV (CAD $ thousands)",
    )

    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.2)

    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


# --------------------------------------------------
# 4. Two-Way Heatmap
# --------------------------------------------------

def plot_heatmap(
    rows: list[dict[str, str]],
    metric: str,
    path: Path,
) -> None:

    if metric not in {"hq_npv", "year4_cash"}:
        raise ValueError(
            "metric must be 'hq_npv' or 'year4_cash'"
        )

    strategy_names = {
        r["strategy"]
        for r in rows
    }

    if len(strategy_names) != 1:
        raise ValueError(
            "Heatmap CSV must contain exactly one strategy"
        )

    strategy = next(iter(strategy_names))

    cafes = sorted({
        int(r["participating_cafes"])
        for r in rows
    })

    positions = sorted({
        float(r["account_range_position"])
        for r in rows
    })

    lookup = {
        (
            int(r["participating_cafes"]),
            float(r["account_range_position"]),
        ): float(r[metric]) / 1000

        for r in rows
    }

    grid = np.array([
        [
            lookup.get(
                (c, p),
                np.nan,
            )
            for p in positions
        ]
        for c in cafes
    ])

    if np.isnan(grid).any():
        raise ValueError(
            "Missing cafe-count / account-position combinations"
        )

    bound = max(
        abs(float(grid.min())),
        abs(float(grid.max())),
        1.0,
    )

    fig, ax = plt.subplots(
        figsize=(
            9,
            max(5, 0.65 * len(cafes) + 2),
        )
    )

    image = ax.imshow(
        grid,
        aspect="auto",
        cmap="RdYlGn",
        vmin=-bound,
        vmax=bound,
    )

    ax.set_xticks(
        range(len(positions)),
        [f"{p:.0%}" for p in positions],
    )

    ax.set_yticks(
        range(len(cafes)),
        [str(c) for c in cafes],
    )

    ax.set(
        xlabel="Position within Case account range (0%=Low, 100%=High)",
        ylabel="Participating Cafes",
    )

    title = (
        "Five-year HQ NPV"
        if metric == "hq_npv"
        else "HQ Cumulative Cash at End of Year 4"
    )

    ax.set_title(
        f"{title} | {strategy}"
    )

    for i in range(len(cafes)):

        for j in range(len(positions)):

            ax.text(
                j,
                i,
                f"{grid[i, j]:+.0f}",
                ha="center",
                va="center",
                fontsize=9,
                bbox=dict(
                    facecolor="white",
                    alpha=0.65,
                    edgecolor="none",
                    pad=1,
                ),
            )

    fig.colorbar(
        image,
        ax=ax,
        label="CAD $ thousands (0 = Break-even)",
    )

    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


# --------------------------------------------------
# 5. Main
# --------------------------------------------------

def main() -> None:

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--strategy",
        default=None,
        help='Tornado scenario, e.g. "Hybrid - Optimized"',
    )

    parser.add_argument(
        "--top",
        type=int,
        default=8,
    )

    args = parser.parse_args()

    if args.top < 1:
        parser.error("--top must be >= 1")

    trials = read_rows(
        OUTPUT / "monte_carlo_trials.csv",
        {"strategy", "hq_npv"},
    )

    one_way = read_rows(
        OUTPUT / "sensitivity_one_way.csv",
        {
            "strategy",
            "store_type",
            "driver",
            "npv_swing",
            "hq_npv_at_low",
            "hq_npv_at_high",
            "base_hq_npv",
        },
    )

    two_way = read_rows(
        OUTPUT / "sensitivity_two_way_accounts.csv",
        {
            "strategy",
            "participating_cafes",
            "account_range_position",
            "hq_npv",
            "year4_cash",
        },
    )

    available = {
        r["strategy"]
        for r in one_way
    }

    strategy = args.strategy or (
        "Hybrid - Optimized"
        if "Hybrid - Optimized" in available

        else "B Only"
        if "B Only" in available

        else sorted(available)[0]
    )

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = {
        "NPV Distribution":
            OUTPUT / "npv_distribution.png",

        "Tornado Chart":
            OUTPUT / "sensitivity_tornado.png",

        "NPV Heatmap":
            OUTPUT / "heatmap_hq_npv.png",

        "Year-4 Cash Heatmap":
            OUTPUT / "heatmap_year4_cash.png",
    }

    plot_npv_distribution(
        trials,
        files["NPV Distribution"],
    )

    plot_tornado(
        one_way,
        strategy,
        files["Tornado Chart"],
        top=args.top,
    )

    plot_heatmap(
        two_way,
        "hq_npv",
        files["NPV Heatmap"],
    )

    plot_heatmap(
        two_way,
        "year4_cash",
        files["Year-4 Cash Heatmap"],
    )

    print(
        f"\nCreated 4 charts "
        f"(Tornado strategy: {strategy}):"
    )

    for label, file in files.items():

        print(
            f"  {label}: {file}"
        )

    print(
        "\nNote: simulations use assumed distributions, "
        "not observed probabilities."
    )

    print(
        "Heatmaps vary corporate-account levels, "
        "not the 5% program fee."
    )


if __name__ == "__main__":
    main()
