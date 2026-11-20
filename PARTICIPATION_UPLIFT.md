# Participation uplift as the economic driver for Lever 1 (Case A8)

## Critical correction to the fixed-60 model

**No franchisee has confirmed consent in the Case.** Appendix A8 says
9 Downtown + 5 University + 6 Suburban (20) **informally expressed early
pilot interest**, not signed consent or commitment to Corporate Accounts.
The other 40 are *candidate* cafés, not existing participants. The 60-café
rollout in the old model is a **full network opportunity**, not a measured
unfinanced baseline.

## Participation sensitivity

Default **illustrative**, NOT case-observed, comparison:

- Without HQ Financing: assume 100% of the 20 *interested* stores eventually
  consent (9 downtown, 5 university, 6 suburban). This is a generous
  baseline; 50% and 0% are also useful downside cases.
- With financing: convert ~2/3 of the **40 remaining candidates** (rounded,
  allocated by type), creating approximately 27 *incremental* participants.
- Only the additional participants receive financing in this scenario.
  Earlier participants are assumed self-funded. These separate assumptions
  are transparently configurable.
- Actual eligibility still requires 4 signed employer accounts in Downtown/
  Suburban, or 3 at University. As in the original L1 module, Case midpoint
  accounts are an *eligibility proxy*, never evidence of signed customers.
- Original B Only launch slots are reused chronologically. No new locations
  are manufactured and the 6-per-quarter, 2-quarter pilot observation,
  candidate counts and HQ budget constraints are still validated.
- Existing **319 accounts** is a reference full-60 *opportunity* count, NOT
  319 signed customers at the 20-store baseline. For new participating stores
  we recognize **their own Case midpoint accounts** for the first time.
  Landlord-introduced accounts must be added *on top* only at participating
  stores. A café is counted only once. In this sense financing unlocks
  stores and their base accounts; landlord acquisition increases accounts
  *per store*.
- $40,000 HQ program setup + $90,000 every year is unchanged.
- Loan principal is a cash advance/recovery, never HQ revenue.
  Additional **coffee sales go to the cafés**; HQ earns 7.5% royalty, extra
  fees only if L3 is enabled and activated, and interest received on loans.
- This models attribution *conditional on financing causing consent*.
  It cannot prove the causal impact of financing: assess conversion rates
  and unfinanced willingness through an actual pilot.

```bash
python participation_uplift.py
python participation_uplift.py --interest-conversion .5 --financing-conversion .25
python integrated_levers.py --participation-uplift
python -m unittest discover -s tests -v
```

Outputs: `outputs/participation/` (summary, type-level economics, separate
rollout schedules, HQ quarterly flows, loan schedule, 2D consent sensitivity).
The original fixed-60 scripts remain available for comparison. The integrated
8-combination model can optionally use participation uplift (L1 off has only
the baseline assumed consenting stores; L1 on includes the additional financed
stores). Partner counts scale to realized Corporate Accounts participant
counts by type in this mode, avoiding the same 40 landlords creating 120 new
accounts in both a 20-store and a 47-store scenario.

**Model limitations:** This is a consent / adoption hypothesis, not an
empirical conversion estimate. Type-average cafés are not identified actual
sites. Increasing participation beyond these source slots or toward a new
timeline requires separate operational evidence and scheduling analysis.

The integrated comparator also reports the participant count in each scenario,
and scales the expected number of landlord partners to realized participant
counts by café type. L1's role as *consent enablement* can therefore affect
L2 acquisitions and L3 fee receipts without inventing new locations.
