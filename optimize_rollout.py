"""Optimize the Hybrid rollout timing using the existing financial model.

Objective: maximize 5-year head-office NPV, without changing the cafe mix,
case assumptions, annual unit economics, or HQ cost structure.

We enumerate feasible Q1 pilot compositions, then put remaining launches in
highest annual-HQ-royalty order at the earliest permitted quarters. This is
optimal for *this model* because every store of a type has the same positive
annual royalty, same activation delay, and no per-store HQ startup cost.

Run from repo root:
    python optimize_rollout.py
    python optimize_rollout.py --save
    python optimize_rollout.py --min-pilot 1,1,1  # more aggressive pilot
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from secondcup.inputs import Inputs  # noqa: E402
from secondcup.financial_engine import run_hq  # noqa: E402
from secondcup.scenarios import Launch, get_launches, validate_launches  # noqa: E402
from secondcup.unit_economics import unit_economics  # noqa: E402

TYPE_ORDER = ("Downtown", "University", "Suburban")
STRATEGY = "Hybrid"
OUTPUT_NAME = "Hybrid - Optimized"
LAST_LAUNCH_QUARTER = 11  # 2029 Q4; 2027-2029 rollout period


def quarter_label(q: int) -> str:
    return f"{2027 + q // 4} Q{q % 4 + 1}"


def read_hybrid_configuration() -> tuple[dict[str, str], dict[str, int]]:
    """Preserve the currently configured Hybrid options and cafe counts."""
    options: dict[str, str] = {}
    totals: Counter[str] = Counter()
    for row in get_launches(STRATEGY):
        if row.typ in options and options[row.typ] != row.option:
            raise ValueError(f"Hybrid has multiple options for {row.typ}")
        options[row.typ] = row.option
        totals[row.typ] += row.count
    if set(options) != set(TYPE_ORDER):
        raise ValueError("Hybrid must include Downtown, University and Suburban")
    return options, dict(totals)


def build_rollout(
    pilot: dict[str, int],
    options: dict[str, str],
    totals: dict[str, int],
    data: Inputs,
) -> list[Launch]:
    """Fill all remaining launch slots by descending annual HQ royalty."""
    remaining = {typ: totals[typ] - pilot[typ] for typ in TYPE_ORDER}
    launches = [
        Launch(typ, options[typ], 0, pilot[typ])
        for typ in TYPE_ORDER
        if pilot[typ] > 0
    ]

    # In this case-only model, sorting positive marginal returns is exact:
    # earlier revenue has greater discounted present value.
    priority = sorted(
        TYPE_ORDER,
        key=lambda typ: unit_economics(
            data, typ, options[typ]
        ).annual_hq_royalty,
        reverse=True,
    )

    first_expansion_q = 1 + int(data.rule("pilot_obs_q"))
    for q in range(first_expansion_q, LAST_LAUNCH_QUARTER + 1):
        available = int(data.rule("max_per_q"))
        for typ in priority:
            count = min(remaining[typ], available)
            if count:
                launches.append(Launch(typ, options[typ], q, count))
                remaining[typ] -= count
                available -= count

    if any(remaining.values()):
        raise ValueError(f"Not enough rollout capacity: {remaining}")
    return sorted(launches, key=lambda x: (x.quarter, TYPE_ORDER.index(x.typ)))


def optimize_hybrid(
    data: Inputs,
    min_pilot: tuple[int, int, int] = (2, 1, 2),
) -> tuple[list[Launch], object, dict[str, int]]:
    """Choose the highest-NPV valid pilot split, then optimize later launches.

    Pilot upper bounds use A8's *early interest*, not confirmed consent.
    Results are conditional on all subsequent franchisees consenting.
    """
    options, totals = read_hybrid_configuration()
    pilot_size = int(data.rule("max_per_q"))
    if len(min_pilot) != 3 or any(v < 0 for v in min_pilot):
        raise ValueError("--min-pilot needs three nonnegative integer counts")
    if sum(min_pilot) > pilot_size:
        raise ValueError("Minimum pilot requirements exceed Q1 capacity")

    best_launches = None
    best_result = None
    best_pilot = None

    dmin, umin, smin = min_pilot
    for d in range(dmin, min(pilot_size, totals["Downtown"], int(data.get("Downtown", "early_interest"))) + 1):
        for u in range(umin, min(pilot_size-d, totals["University"], int(data.get("University", "early_interest"))) + 1):
            s = pilot_size - d - u
            if not (smin <= s <= min(totals["Suburban"], int(data.get("Suburban", "early_interest")))):
                continue
            pilot = {"Downtown": d, "University": u, "Suburban": s}
            try:
                launches = build_rollout(pilot, options, totals, data)
            except ValueError:
                continue
            if validate_launches(launches, data):
                continue
            result = run_hq(OUTPUT_NAME, launches, data)
            if not result.feasible or result.owner_failing_3yr:
                continue
            if result.payback_years is None or result.payback_years > data.rule("hq_payback_years"):
                continue
            if best_result is None or result.npv_5y > best_result.npv_5y:
                best_launches, best_result, best_pilot = launches, result, pilot

    if best_launches is None:
        raise ValueError(
            "No rollout meets the pilot, launch, franchisee and HQ payback constraints. "
            "Relax the pilot minimums or review the financial assumptions."
        )
    return best_launches, best_result, best_pilot


def print_schedule(launches: list[Launch]) -> None:
    print("\nQuarter    Downtown    University    Suburban    Total")
    print("-" * 61)
    for q in range(LAST_LAUNCH_QUARTER + 1):
        n = Counter()
        for launch in launches:
            if launch.quarter == q:
                n[launch.typ] += launch.count
        print(
            f"{quarter_label(q):<11}"
            f"{n['Downtown']:>8}"
            f"{n['University']:>14}"
            f"{n['Suburban']:>12}"
            f"{sum(n.values()):>9}"
        )


def save_plan(launches: list[Launch], options: dict[str, str]) -> Path:
    path = ROOT / "data" / "rollout_plans.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    schedule = []
    for typ in TYPE_ORDER:
        counts = [0] * 20
        for launch in launches:
            if launch.typ == typ:
                counts[launch.quarter] += launch.count
        schedule.append({"type": typ, "option": options[typ], "launches": counts})
    payload[OUTPUT_NAME] = schedule
    backup = path.with_name("rollout_plans.backup.json")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-pilot", default="2,1,2",
        help="Minimum Q1 pilots: Downtown,University,Suburban (default 2,1,2)",
    )
    parser.add_argument("--save", action="store_true", help="Add Hybrid - Optimized to rollout_plans.json")
    args = parser.parse_args()

    try:
        min_pilot = tuple(int(x.strip()) for x in args.min_pilot.split(","))
    except ValueError as exc:
        parser.error(f"Invalid --min-pilot: {exc}")
    if len(min_pilot) != 3:
        parser.error("--min-pilot must have exactly three numbers, e.g. 2,1,2")

    data = Inputs.from_file()
    original = run_hq(STRATEGY, get_launches(STRATEGY), data)
    launches, optimized, pilot = optimize_hybrid(data, min_pilot)

    print("\n=== HYBRID ROLLOUT OPTIMIZATION (CASE BASELINE) ===")
    print(f"Pilot: {pilot}")
    print(f"Original HQ NPV:  ${original.npv_5y:,.2f}")
    print(f"Optimized HQ NPV: ${optimized.npv_5y:,.2f}")
    print(f"NPV improvement:  ${optimized.npv_5y - original.npv_5y:,.2f}")
    print(f"Original payback:  {original.payback_years} years")
    print(f"Optimized payback: {optimized.payback_years} years")
    print(f"Cash at year 4:   ${optimized.cash_at_year4:,.2f}")
    print(f"Owner 3-year payback failures: {optimized.owner_failing_3yr}")
    print(f"Total cafes: {optimized.launched_cafes}")
    print(f"HQ 2027 spending: ${optimized.hq_spend_year1:,.2f}")
    print(f"HQ 2027-29 spending: ${optimized.hq_spend_first_3y:,.2f}")
    print_schedule(launches)

    if args.save:
        options, _ = read_hybrid_configuration()
        path = save_plan(launches, options)
        print(f"\nSaved '{OUTPUT_NAME}' to {path}")
        print("Original 'Hybrid' unchanged. Backup: data/rollout_plans.backup.json")


if __name__ == "__main__":
    main()
