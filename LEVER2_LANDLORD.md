# Lever 2 — Landlord-led Corporate Account Acquisition

This is an **independently switchable** module using the original Case inputs,
quarterly rollout and unit-economics engine. Lever 3 remains off.

## Run

```bash
python lever2_landlord_acquisition.py
python lever2_landlord_acquisition.py --with-financing
python lever2_landlord_acquisition.py --partners 12 8 20 --introductions 6 --conversion .5 --cac 500
python -m unittest discover -s tests -v
```

Results go to distinct folders: `outputs/landlord/standalone/` and
`outputs/landlord/with_financing/`. Each includes HQ quarterly flows,
acquisition cohorts, owner cohorts, assumptions and summary. The combined run
also exports a loan schedule.

## Model assumptions and guardrails

- All **landlord funnel** inputs are explicitly hypothetical, not Case facts.
  Illustrative scenario: 12 Downtown + 8 University + 20 Suburban partners;
  each introduces 6 tenant prospects, 50% sign, $500 tasting/onboarding CAC
  per newly signed account. This gives **120 incremental accounts** at the
  60-cafe B Only rollout: 36 / 24 / 60 respectively.
- Case midpoint **319 existing corporate accounts** are retained, not
  reclassified as acquisitions. Modelled total is **439** in this example.
- Annual steady-state per extra account: 3 orders/week × 12 cups/order ×
  50 weeks × $4.60 = **$8,280** sales; **32%** contribution to owner;
  **7.5%** royalty to HQ = **$621**.
- Apply 50% first-quarter revenue ramp, then normal quarterly rate.
  CAC is an HQ expense at cafe launch, not deducted again from owner margin.
  Existing Case delivery expense is included in contribution margin.
- Keep HQ Corporate Sales Coordination **$90,000 every year**, original
  $40,000 setup, no portal expense and unchanged rollout restrictions.
- Cohort averages allow fractional expected accounts per cafe; actual
  signed accounts and timing need operational verification. No additional
  participating cafes are invented.
- With L1 on, re-run the loan waterfall on **enhanced owner contribution**,
  not a sum of independent NPVs. Financing eligibility is based on pre-lever
  Case midpoints unless verified signed counts are explicitly supplied.
  Principal collected is recovery of an advance, not incremental revenue.
- Gross financing advances plus CAC count against HQ budgets. $500k reserve
  is a distinct diagnostic, not silently a binding constraint.
- Owner NPVs run 20 operating quarters after each cafe launch; HQ NPV uses
  2027–2031 program quarters. L3 Deferred Program Fee is not included.

Scenario forecasts are **conditional** on these management assumptions;
they are not empirical likelihood estimates.

## Landlord partnership cost sensitivity and break-even

The original default model **already charges HQ $500 per additional account**:
120 accounts cost **$60,000** in total across launch cohorts. It does **not**
assume a reduction in the Case's **$90,000 per year** Corporate Sales
Coordination expense, which is mandatory in every operating year.

Landlord introductions might reduce the *hypothetical incremental acquisition
CAC* (e.g. $500 to $250 per signed account). This is a saving **relative to
our modeled $500 CAC case**, not a reduction from the strict Case budget.
To test relationship management burden beyond existing coordination expense,
optional inputs add a $5,000 one-time setup and $10,000/year recurring HQ
administration. The core defaults remain zero to preserve backward compatibility.

```bash
python lever2_landlord_acquisition.py --cac 500 --extra-hq-setup 5000 --extra-hq-annual 10000
python landlord_cost_sensitivity.py
python landlord_cost_sensitivity.py --with-financing
python landlord_cost_sensitivity.py --cac 500 --setup 5000 --annual 20000
python -m unittest discover -s tests -v
```

`landlord_cost_sensitivity.py` writes scenario comparisons to
`outputs/landlord/cost_sensitivity/{standalone,with_financing}/cost_scenarios.csv` and analytic cost ceilings
to `break_even.json`; other assumptions are exported separately. Compare the
same funnel with CAC $250 (savings), $500 (prior default), +$5k upfront and
+$10k or +$20k/year (additional management), and a CAC $1,000 stress. It also includes a mixed case of **CAC $250 plus
$5k setup and $10k/year** and writes `cost_matrix.csv`, a 4×4 two-way
sensitivity of CAC versus annual incremental HQ cost at the selected setup.

**HQ incremental economic break-even** means incremental HQ NPV of L2
compared with the **same financing/no-L2 baseline** is exactly zero. The
maximum allowable per-account CAC is not the same as a bound on recurring
annual HQ cost. Both are output, together with constraints from HQ 4-year
cash payback, first-year budget, 2027-2029 budget, and a **separately identified
nonbinding** $500k reserve diagnostic. All cost ceilings hold the number and
timing of expected new accounts constant and should not be presented as
market forecasts or observed cost benchmarks.

Annual net HQ contribution from a single *additional* corporate account is
$8,280 sales * 7.5% royalty = $621. Thus, $10,000/year recurring added cost
requires approximately 16.1 more fully productive accounts each year simply
to cover that annual cost on a steady-state basis, **before** extra CAC and
ramp-up. Reducing CAC from $500 to $250 saves $30,000 in undiscounted
launch-year cash costs for 120 accounts, but does not itself create sales.

GitHub Actions runs both modes and uploads downloadable `landlord-cost-analysis`
CSV/JSON outputs as a workflow artifact. Default output folders are separate
so the combined L1+L2 results never overwrite standalone L2.
