# Lever 2 — Landlord acquisition cost sensitivity

This is an **additive cost-analysis layer**, not a redesign of the Second Cup
strategy. It uses `src/secondcup/landlord_acquisition.py` and optionally
`src/secondcup/hq_financing.py`. It does **not** modify Case inputs or the
$90,000/year corporate HQ coordination requirement.

## Run

```bash
python landlord_cost_sensitivity.py
python landlord_cost_sensitivity.py --with-financing
python landlord_cost_sensitivity.py --partner-onboarding 100 --annual-support 10000 --cac-values 0 250 500 750 1000 1500 2000
python landlord_cost_sensitivity.py --conversion .25 --annual-support 10000 --with-financing
python -m unittest discover -s tests -v
```

Outputs go under `outputs/landlord/cost_standalone/` or
`outputs/landlord/cost_with_financing/`:

- `cost_scenarios.csv`: HQ five-year NPV, **marginal L2 NPV vs matching L1
  baseline**, four-year cumulative HQ cash, and gross-spend budget tests;
- `breakeven.json`: present-value and 4-year cash break-even CAC per signed
  account, plus first-three-year budget limits;
- `channel_comparison.json`: a **counterfactual** (not a booked savings item)
  comparing direct-channel CAC against landlord-led CAC, for the same accounts;
- `assumptions.json`: all inputs; no new unverified baseline savings.

### Default cost-side planning case

The original L2 model **already charges $500 per signed new account**. This
is **$60,000** of initial HQ CAC for the illustrative 120 incremental signed
accounts. The new stress test adds, purely as management assumptions:

- $100 one-time activation/onboarding per participating landlord partner
  (40 × $100 = **$4,000**, paid q0), e.g. agreement setup and coordination;
- $10,000 **incremental** annual HQ support (five years = **$50,000**),
  e.g. external support, partner training or events beyond existing staff
  capacity; paid $2,500 at each quarter-end;
- CAC stress cases: $0 / $250 / $500 / $750 / $1,000 / $1,500 / $2,000 per
  new signed account. Low CAC is plausible if warm introductions reduce
  outreach, trial and onboarding effort. These are **not established market
  benchmarks**, and are not empirical estimates of Second Cup spend.

Illustrative CAC component structure, not observational data: at $500 per
signed account, $150 tasting/sample product + $200 incremental outreach and
onboarding + $150 follow-up and administration; **include only incremental**
external costs, not labor already funded by the $90k fixed annual expense.
If the incremental staff time is already covered by that $90k, do not charge
it again. Scenario $0 is a mathematical lower bound, not a prediction.

### Base assumptions and what cost savings mean

The default L2 demand funnel is **40 partners × 6 introductions × 50% signing
conversion = 120 signed incremental accounts**, in addition to Case midpoint
319 baseline accounts. With fixed account volume:

- incremental annual store sales = `120 × $8,280 = $993,600`;
- incremental annual HQ royalty = `120 × $621 = $74,520`;
- **varying CAC does not vary sales**; it changes HQ costs and NPV.

Cost reduction has two distinct meanings:

1. **Relative to original L2 planning case:** $500 to $250 CAC saves $30k
   nominal over 120 accounts; no new sales follow automatically.
2. **Relative to hypothetical direct B2B acquisition:** e.g. $750 direct CAC
   vs $250 landlord CAC saves another $60k nominal **for the same 120 accounts**.
   This is a **channel comparison**, not a saving against the original Case
   HQ budget; it is NOT added to HQ cash flows because Case does not provide
   that avoidable direct-acquisition cost line.

To convert saved CAC into additional sales, a larger verified landlord/tenant
funnel and additional operating capacity would be needed. An extra $30k could
fund *at most* 120 additional accounts at $250 CAC, but **the stated funnel
has capacity for only 120 accounts in total**. At the same conversion rate it
would require e.g. 80 partners instead of 40 (or 12 intros per partner).
This is **not** included in the baseline or headline NPV.

### What 'break-even CAC' means

For cost schedule `[one-time setup, annual support q1..q20]`, calculate
`L2 incremental HQ 5y NPV = HQ NPV (L2 enabled) - HQ NPV (L2 disabled)`
with financing uptake *unchanged* in both. Signed-account CAC is incurred at
store launch. The maximum CAC before this **incremental NPV** becomes zero is

`(PV(incremental cash at CAC=0 after fixed support) / sum(accounts_cohort / (1+r)^(launch_q/4)))`.

A separate **four-year incremental cash-flow** threshold uses incremental
cumulative HQ cash through q16. This is distinct from Second Cup's **absolute
HQ four-year payback target**, which is also reported. The budget test covers
**gross HQ outlays**, not loan repayments netted against spending. The $500k
reserve is only flagged as a diagnostic (not silently binding).

Head-office 5-year NPV uses 2027–2031 q0..q20. Required $90k/year is retained
by the unchanged baseline engine. Owner contributions/loan repayments are
calculated by the existing modules; acquisition and partner support costs here
are paid by HQ only. Do not add standalone lever NPVs together.
