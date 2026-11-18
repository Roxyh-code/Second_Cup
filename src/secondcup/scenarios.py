
"""Deployment schedules and rollout validation for Second Cup.

Case Appendix A7 constraints:
- 60 candidate cafes: 18 Downtown, 10 University, 32 Suburban.
- Maximum 6 cafe launches per quarter.
- Observe pilot results for at least 2 quarters before expansion.

Quarter index:
    0 = 2027 Q1
    1 = 2027 Q2
    2 = 2027 Q3
    3 = 2027 Q4
    ...
    19 = 2031 Q4
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .inputs import (
    Inputs,
    TYPES,
    OPTIONS,
    load_rollouts,
)


@dataclass(frozen=True)
class Launch:
    """A group of cafes launching the same strategy in one quarter."""

    typ: str
    option: str
    quarter: int
    count: int


def get_launches(name: str) -> list[Launch]:
    """Load a rollout plan by strategy name.

    Supported names:
        - A Only
        - B Only
        - Hybrid

    Returns:
        List of Launch objects.
    """

    plans = load_rollouts()

    if name not in plans:
        raise ValueError(
            f"Unknown strategy: {name!r}. "
            f"Available strategies: {list(plans.keys())}"
        )

    launches = []

    for row in plans[name]:

        typ = row["type"]
        option = row["option"]
        schedule = row["launches"]

        if typ not in TYPES:
            raise ValueError(f"Unknown cafe type: {typ}")

        if option not in OPTIONS:
            raise ValueError(f"Unknown strategy option: {option}")

        if len(schedule) != 20:
            raise ValueError(
                f"{name}: rollout schedule must have 20 quarters."
            )

        for quarter, count in enumerate(schedule):

            count = int(count)

            if count < 0:
                raise ValueError(
                    f"Negative launch count in quarter {quarter}"
                )

            if count > 0:
                launches.append(
                    Launch(
                        typ=typ,
                        option=option,
                        quarter=quarter,
                        count=count,
                    )
                )

    return launches


def cap_launches(
    launches: Sequence[Launch],
    limit: int,
) -> list[Launch]:
    """Limit the total number of participating cafes.

    Keeps the earliest scheduled launches first.

    Useful for sensitivity analysis:
        What happens if only 20, 26, or 30 cafes participate?

    This function does not optimize the cafe mix.
    """

    if limit < 0:
        raise ValueError("Limit must be nonnegative.")

    capped = []

    sorted_launches = sorted(
        launches,
        key=lambda x: x.quarter,
    )

    remaining = limit

    for launch in sorted_launches:

        if remaining <= 0:
            break

        count = min(remaining, launch.count)

        capped.append(
            Launch(
                typ=launch.typ,
                option=launch.option,
                quarter=launch.quarter,
                count=count,
            )
        )

        remaining -= count

    return capped


def validate_launches(
    launches: Sequence[Launch],
    data: Inputs,
    *,
    check_pilot: bool = True,
) -> list[str]:
    """Validate a rollout plan against case constraints.

    Returns:
        Empty list if the schedule passes all checks.
        Otherwise returns a list of error messages.
    """

    errors = []

    launches_by_quarter = {}
    launches_by_type = {}

    first_launch_quarter = None

    for launch in launches:

        # Check valid quarter and count
        if launch.quarter < 0 or launch.quarter >= 20:
            errors.append(
                f"Invalid launch quarter: {launch.quarter}"
            )
            continue

        if launch.count < 0:
            errors.append(
                f"Negative launch count: {launch.count}"
            )
            continue

        if launch.typ not in TYPES:
            errors.append(
                f"Unknown cafe type: {launch.typ}"
            )
            continue

        if launch.option not in OPTIONS:
            errors.append(
                f"Unknown option: {launch.option}"
            )
            continue

        # Count launches by quarter
        launches_by_quarter[launch.quarter] = (
            launches_by_quarter.get(launch.quarter, 0)
            + launch.count
        )

        # Count launches by cafe type
        launches_by_type[launch.typ] = (
            launches_by_type.get(launch.typ, 0)
            + launch.count
        )

        # Record the earliest launch quarter
        if launch.count > 0:

            if first_launch_quarter is None:
                first_launch_quarter = launch.quarter

            else:
                first_launch_quarter = min(
                    first_launch_quarter,
                    launch.quarter,
                )

    # Constraint 1: Maximum 6 launches per quarter
    max_per_quarter = int(data.rule("max_per_q"))

    for quarter, count in launches_by_quarter.items():

        if count > max_per_quarter:
            errors.append(
                f"Quarter {quarter}: "
                f"{count} launches exceed limit "
                f"{max_per_quarter}"
            )

    # Constraint 2: Candidate cafe limits
    for typ, count in launches_by_type.items():

        candidates = int(data.get(typ, "candidates"))

        if count > candidates:
            errors.append(
                f"{typ}: {count} launches exceed "
                f"{candidates} candidate cafes"
            )

    # Constraint 3: Pilot observation period
    if check_pilot and first_launch_quarter is not None:

        observation_quarters = int(
            data.rule("pilot_obs_q")
        )

        for quarter, count in launches_by_quarter.items():

            if (
                first_launch_quarter < quarter
                <= first_launch_quarter + observation_quarters
                and count > 0
            ):
                errors.append(
                    f"Quarter {quarter}: launch occurs "
                    f"before {observation_quarters} "
                    f"pilot observation quarters finish"
                )

    return errors
