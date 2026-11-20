# Lever 3 — Deferred Program Fee

Incremental program fee **only on Corporate Accounts**; it does not alter
the Case's 7.5% HQ royalty, normal 32% owner contribution margin, CAPEX,
$40k corporate HQ setup, or mandatory $90k/year coordination.

All fees are hypothetical team proposals, **not Case facts**.

## Independent and combined runs

```bash
python lever3_deferred_fee.py
python lever3_deferred_fee.py --with-financing
python lever3_deferred_fee.py --with-landlord
python lever3_deferred_fee.py --with-landlord --with-financing
python integrated_levers.py
python integrated_levers.py --fee-rate .025
python -m unittest discover -s tests -v
```

- Standalone L3 compares **0%, 2.5%, 5%** fees by default.
- `--with-financing` adds L1's HQ loans (2/3 uptake by default).
- `--with-landlord` adds L2's incremental account funnel and costs.
  Conservatively, L2 is assumed to have $500 CAC, **$5k additional setup**
  and **$10k additional annual management** in the new integrated scripts.
  Pass `--landlord-setup 0 --landlord-annual 0` for the old L2 base case.
- `integrated_levers.py` evaluates all **eight** on/off configurations
  independently; no stand-alone NPVs are added together.
- No Case inputs, rollout data or existing L1/L2 scripts are overwritten.

## Default contract trigger

A Corporate Accounts cafe must first recover its **original program CAPEX**
from cumulative **before-fee operating contribution** (not HQ loan proceeds).
The fee becomes payable at the NEXT quarter-end after the quarter in which
CAPEX recovery occurs. Fee is not back-charged. Full equity financing may
mean zero cash equity at launch but **must not trigger immediate fees**.

Fee per quarter = fee_rate * qualifying annual Corporate Accounts sales / 4,
subject to the same 50% first-operating-quarter ramp as other business flows.
The default fee base is **all Corporate Accounts sales** (existing Case
midpoint accounts + new landlord accounts). To test only incremental new
landlord sales, use `--fee-base landlord_incremental`. No fee applies to A.

Options for sensitivity:

- `after_operating_payback` (default): after CAPEX payback, even if HQ debt
  is still being repaid.
- `after_operating_and_loan_payoff`: wait until BOTH operating CAPEX
  recovery and full debt repayment, with the fee starting in the next quarter.
- `immediate`: fee from first active operating quarter (for comparison,
  not the proposed deferred policy).

**Loan waterfall ordering:** L1 repayment remains 75% of the *pre-fee*
positive program contribution, with 10% annual interest. L3 fees reduce
the remaining franchisee cash; the model flags any negative owner cash
quarters rather than ignoring repayment pressure or treating fee as royalty.
HQ fee receipts are matched by franchisee cash expenses. Loan principal
repayments are not classified as income.

**Time horizons:** HQ NPV uses 2027–2031 quarterly program cash flow;
each franchisee NPV is its own 20 operating quarters from launch. HQ does not
claim fee payments falling after 2031 as cash by the program horizon. Thus
owner 5-year total fee payments may exceed HQ cash collected by 2031.

## Outputs

- `outputs/deferred_fee/L1-off_L2-off/summary.csv` and corresponding toggle
  folders: `hq_quarterly.csv`, `fee_schedule.csv`, `owner_cohorts.csv`,
  `assumptions.json`.
- `outputs/integrated/` contains `summary.csv` for all eight combinations,
  plus detailed quarterly HQ flows, fee schedules, owner cohorts, and assumptions.
- GitHub Actions also runs three-lever regression tests and uploads the
  integrated outputs as a downloadable workflow artifact.

## Financial interpretation

The proposed fee reallocates cash flow between franchisee and HQ. It is not
new coffee sales: every additional HQ fee receipt is an owner fee payment,
before timing and horizon differences. Evaluate owner NPV, the original
3-year operating payback, post-fee owner cash and HQ 4-year payback together.
With 0% fee, all results reconcile with the prior L1/L2 engine to cents.
