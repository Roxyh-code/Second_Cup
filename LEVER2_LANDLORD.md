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
