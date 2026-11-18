
"""Data and parameter plumbing. Monetary amounts are Canadian dollars (CAD)."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
import json

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
TYPES = ("Downtown", "University", "Suburban")
OPTIONS = ("Paid Reservations", "Memberships", "Operator Partnership", "Late-day Offer", "Corporate Accounts")


@dataclass(frozen=True)
class Inputs:
    stores: Mapping[str, Mapping[str, float]]
    global_rules: Mapping[str, float]

    @classmethod
    def from_file(cls, path: Path | None = None) -> "Inputs":
        payload = json.loads(
            (path or DATA_DIR / "case_inputs.json").read_text(encoding="utf-8")
        )
        return cls(payload["store_types"], payload["global"])

    def get(self, typ: str, key: str) -> float:
        return float(self.stores[typ][key])

    def rule(self, key: str) -> float:
        return float(self.global_rules[key])


@dataclass(frozen=True)
class Overrides:
    """Scenario-specific input overrides, not empirical data.

    `type_parameters` maps store type -> source-case input key -> replacement.
    `global_parameters` similarly overrides source-case global drivers.
    """
    type_parameters: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    global_parameters: Mapping[str, float] = field(default_factory=dict)

    def get(self, data: Inputs, typ: str, key: str) -> float:
        return float(
            self.type_parameters.get(typ, {}).get(key, data.get(typ, key))
        )

    def rule(self, data: Inputs, key: str) -> float:
        return float(
            self.global_parameters.get(key, data.rule(key))
        )


def midpoint(
    data: Inputs,
    typ: str,
    low_key: str,
    high_key: str,
    over: Overrides
) -> float:
    return (
        over.get(data, typ, low_key)
        + over.get(data, typ, high_key)
    ) / 2


def load_rollouts() -> dict[str, list[dict]]:
    return json.loads(
        (DATA_DIR / "rollout_plans.json").read_text(encoding="utf-8")
    )
