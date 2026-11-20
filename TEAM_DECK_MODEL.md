# UTCC 2026 Second Cup — TEAM DECK ALIGNED FINANCIAL MODEL

**Authoritative modeling entry point for the current group slide deck:** \`python model_team_deck.py\`

This supersedes the earlier presentation narrative of
Financing → Landlord Acquisition → Deferred Program Fee.
The team deck's actual three enablers are:
**Landlord Sales Channel, Cash Advance, Fixed Production Slots.**
The older \`integrated_levers.py\` is preserved for a clearly separate
historical financial alternative; do not mix its results into this deck.

## Exactly what is from the 14-slide team's PDF

- 60 total candidate cafés: 32 suburban / 18 downtown / 10 university.
- Q1 2027: 6 suburban pilots, Q2 observation only, then six per quarter;
  rollout ends Q3 2029. See \`src/secondcup/team_aligned.py:DECK_ROLLOUT\`.
- Corporate account economics: 3 orders per week, 12 cups per order,
  50 weeks/year, $4.60/cup, owner contribution **32% after ordinary
  franchise charges**, HQ royalty 7.5%. **Do not charge royalty twice.**
- Case Strategy B HQ startup $40k + **$90k every year** in coordination.
- Team's portal analogy: **$25k HQ setup**, $1.8k/store/year borne by
  owner. These are team assumptions, NOT Case B mandates.
- Team proposes extra **5% fee once original CAPEX has paid back**.
  Treat this as a **shared policy in every scenario**, NOT as L3,
  because team's L3 is Fixed Production Slots.
- Financing: 10% APR, 75% of positive net operating contribution to
  repay an advance, threshold ≥4 signed accounts (≥3 at university);
  actual signed contracts are NOT supplied. A6 account midpoints are
  planning proxies only.
- Baseline without cash advance: assume 20 informally interested cafés
  would participate without HQ financing, which is a generous **consent
  assumption**, not evidence of signed owners. With L1: the team's planned
  full 60 café rollout is assumed to be secured. This is NOT a measured
  financing causal conversion rate.
- 2/3 of the 60 active cafés use HQ cash advances, apportioned **across
  store types and launch cohorts**, rather than financing earliest cafes
  first. This gives **40 loans, $579k advances**, annual 2027 loan advances
  **$180k**. 2027 HQ *gross spend* = $65k setup + $90k coordination
  + $180k advances = **$335k** (without landlord CAC). Three-year
  gross spend = $65k setup + 3×$90k coordination + $579k loans =
  **$914k** (~$915k rounding in the team deck). Loan principal repayments
  are cash recoveries, not royalty revenues.

## Landlord assumptions (hypothetical, NOT team-proven)

The deck claims one landlord introduces approximately 10 employers, but
does not estimate the landlord partner count, signup conversion, or CAC.
For a clearly labeled **illustrative** model:
40 landlord relationships by type (12 D, 8 U, 20 S) × 10 employer
introductions × 30% sign rate = 120 expected *extra* corporate accounts
when all 60 cafés participate. The original 319 case-midpoint accounts
remain distinct and are NOT added again. $500 tasting/onboarding CAC
per signed account is charged to HQ. Landlords themselves are not paid.
No claimed courier cost savings: delivery is already within 32% margin.
To stress higher overhead pass \`--landlord-setup 5000 --landlord-annual 10000\`.

## Fixed Production Slots: operational guardrail, not invented revenue

The team proposes two daily corporate-order production windows:
before opening (delivered by 8:30), and 10:00–11:30.
Assuming five operating weekdays per week, 10 weekly production
windows. At 5.5 Case suburban accounts:
- 16.5 orders/week and 198 cups/week ⇒ **19.8 cups/window average**.
- With illustrative 1.875 additional landlord accounts/store:
  22.125 orders/week ⇒ **26.55 cups/window average**.

These are **workload requirements, NOT measured production capacity**.
No barista throughput/queueing or on-time delivery distribution is in
the Case; cannot guarantee 3.5-minute walk-in service / 4.2 satisfaction.
The pilot must verify these along with delivery on-time rate and offices'
acceptance of early deliveries. Fixed slots do not, by themselves,
produce new coffee sales, so **default L3 incremental HQ NPV is $0**.

To quantify a *separate explicitly hypothetical downside scenario*,
use \`--leakage-without-slots 0.05\`. It assumes that without fixed slots
5% of otherwise obtainable corporate orders are lost; with L3,
those sales are protected. This adds conditional NPV benefit
but **must not be called proven sales uplift**. No delivery savings are
added or double counted. The 5% leakage is a sensitivity, not a fact.

## Interpretation and guardrails

Two independent questions:
1) **Economic contribution**: change in HQ five-year NPV
   compared with Strategy B, or against the previous rollout stage.
2) **Feasibility**: HQ payback ≤4 years; 2027 gross spend ≤$600k;
   2027–29 HQ gross spend ≤$1.2m; original owner CAPEX payback ≤3y;
   service ≤3.5 min and satisfaction ≥4.2 **to be verified**, not assumed.

A further $0.5m reserve is **outside the $1.2m authorized
budget**, not an amount to deduct again from that cap.
All amounts are CAD and 10% discount over HQ q0..q20; owner returns
span 20 operating quarters after each launch.

## Commands

\`\`\`bash
python model_team_deck.py
python model_team_deck.py --leakage-without-slots .05
python model_team_deck.py --landlord-setup 5000 --landlord-annual 10000
python model_team_deck.py --supporting-fee 0
python -m unittest discover -s tests -v
\`\`\`

For presentation use: \`outputs/team_deck/scenario_matrix.csv\`,\n\`team_order_waterfall.csv\`, \`standalone_effects.csv\`,\n\`bridge_with_synergies.csv\`,
\`waterfall_for_slide.csv\`, \`fixed_slots_capacity.csv\`.
Also exports complete owner cohorts, loan ledger and quarterly HQ cash
flows. Always identify team hypothetical policies vs the supplied Case.

## What to put on the Modeling slide

Headline example: **A 60-café rollout creates value only if cash
advances unlock adoption and landlord introductions convert**.
Show a central four-stage NPV waterfall (B only → +cash advances →
+landlord pipeline → +production slots / service protection), with
the L3 step labeled **nonfinancial guardrail; $0 modeled uplift** in the
Case-faithful scenario. Show three KPI cells: **HQ five-year NPV**,
**HQ payback years**, **2027 spend / $600k**, plus a compact service
footnote **~20 cups/slot suburban; 3.5 min / 4.2 test at pilot**.
If explaining the budget, use *gross HQ spend* (including $90k/year),
and DO NOT call $579k loans sales. Put the assumed 5% deferred program
fee and $25k / $1.8k portal in small-print assumptions.

The team-order NPV bridge, financial synergy, and a one-minute talking script
are in `MODELING_SLIDE_NOTES.md`. See the root `README.md` for the
primary versus legacy model distinction.
