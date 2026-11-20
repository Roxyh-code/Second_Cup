# Second Cup — UTCC 2026 Financial Modeling

## Current team-deck financial model (PRIMARY)

The team's 14-slide proposal uses **three strategic enablers**:
1. Landlord Sales Channel
2. Cash Advance
3. Fixed Production Slots

Run the primary analysis:

```bash
python model_team_deck.py
```

**Use `TEAM_DECK_MODEL.md` for documented source-versus-assumption
boundaries. Use `MODELING_SLIDE_NOTES.md` for the final modeling slide.**

Key output files in `outputs/team_deck/`:
`scenario_matrix.csv`, `team_order_waterfall.csv`,
`waterfall_for_slide.csv`, `standalone_effects.csv`,
`bridge_with_synergies.csv`, `fixed_slots_capacity.csv`,
`hq_quarterly.csv`, `loan_schedule.csv`, `owner_cohorts.csv`.

The 5% after-CAPEX-payback program fee is a **shared team commercial
assumption** in this primary analysis, NOT one of these three enablers.
The fixed production slots default to **no invented HQ profit uplift**;
the optional 5% lost-order sensitivity is
`python model_team_deck.py --leakage-without-slots 0.05`.

Inputs from the Case, team deck design choices, and hypothetical planning
assumptions are explicitly distinguished in the notes.

## Historic / alternative model (ARCHIVED FOR REPRODUCIBILITY)

`integrated_levers.py`, `strategy_b_attribution.py` and
`lever3_deferred_fee.py` implement the earlier research alternative of
Financing + Landlord + Deferred Program Fee as three separate levers.
**Those NPVs are NOT comparable to the new team-deck aligned results**:
rollout, portal fee, common program fee and the third intervention differ.
Do not place older numbers in the team's final PPT.

## Tests

```bash
python -m unittest discover -s tests -v
```

GitHub Actions executes both historical regressions and the primary
team-aligned scenario including downside sensitivities.
