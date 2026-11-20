# Lever 1 — HQ Financing (standalone)

Additive financing layer on the current `Second_Cup` Python model. Original
`data/case_inputs.json`, rollout schedules, `unit_economics.py`, and
`financial_engine.py` are unchanged. Lever 2 (landlord acquisition) and Lever 3
(deferred program fee) are **off** in this run.

## Run

From repository root (Python standard library only):

```bash
python lever1_hq_financing.py
python lever1_hq_financing.py --strategy "Hybrid - Optimized" --rates 0 0.6666666667 1
python -m unittest discover -s tests -v
```

The default run compares **0%, two-thirds, 100%** financing uptake among
eligible Corporate Accounts cafés. Files are written to `outputs/financing/`:
`summary.csv`, `hq_quarterly.csv`, `loan_schedule.csv`, `owner_cohorts.csv`,
and `assumptions.json`.

## Formula and cash-flow accounting

- Maximum advance per café: Downtown **$15,000**, University **$12,000**,
  Suburban **$15,000**, capped at corporate program CAPEX.
- Funding eligibility: **at least four signed corporate accounts** in
  Downtown/Suburban or **three** in University. Until actual signed data is
  supplied, the **Case midpoint number of accounts is a planning proxy, not
  verified signatures**. To inject verified type-level counts, pass
  `FinancingTerms(signed_accounts_by_type={...})` to `run_financing`.
- Annual simple loan interest: **10%**, accrued per quarter on the opening
  unpaid principal: `interest_due = opening_principal * 10% / 4`.
- First active operating quarter has **50%** of steady-state quarterly program
  contribution and royalties; subsequent quarters use 100%.
- At each operating quarter end, `cash_available = 75% * max(0, contribution)`.
  Repayment `min(cash_available, principal + interest_due + prior_interest_arrears)`.
  Apply the cash repayment first to accrued interest, then loan principal.
  Unpaid interest is carried without charging interest on interest; no negative
  payments and no assumed defaults. The café retains at least 25% of positive
  contribution while debt is outstanding, and 100% thereafter.
- **HQ ledger:** advance = HQ cash outflow in the launch quarter; collected
  principal and interest = HQ cash inflow at active quarter-end. Repaid
  principal is **not** revenue or royalty. The annual $90,000 Corporate HQ
  coordination expense is left intact in the existing baseline for all years.
- **Franchisee ledger:** initial equity outflow = CAPEX minus loan; quarterly
  free cash = operating contribution minus loan payments. The model separately
  outputs **loan payoff**, **operating CAPEX payback** (before finance), and
  **equity cash payback** (after finance). The latter can be zero when CAPEX is
  fully financed: **never use it to automatically trigger Lever 3 fees**.
- HQ financial horizon = 2027–2031 (q0–q20). Each franchisee gets a separate
  20-operating-quarter, five-year forecast from its launch. Any owner debt still
  outstanding at its five-year endpoint is deducted as a terminal liability.
  HQ shows loan balances still due at the **end of 2031**, with no invented
  salvage cash receipt. There are no defaults in this base case.
- HQ program gross spending in years 1 and 1–3 includes financing advances
  **without netting loan repayments**; it is checked against the $600k and
  $1.2m budgets. The $500k `budget_reserve` is shown as a separate diagnostic,
  not silently imposed as an extra hard constraint.

## Integration API for independent levers

```python
from secondcup.hq_financing import FinancingTerms, run_financing
from secondcup.inputs import Inputs
from secondcup.scenarios import get_launches

data = Inputs.from_file()
launches = get_launches("B Only")
result = run_financing("B Only", launches, data, FinancingTerms(uptake=2/3))
print(result.summary)
```

`run_financing` accepts `Overrides` so the later landlord acquisition model
can affect program contribution and loan repayment. The Deferred Program Fee
model should add separate franchisee fee outflows and HQ fee receipts, with
its **contractual operating-investment payback trigger** independent of the
loan balance. Never add standalone lever NPVs together as a substitute for
an integrated cash-flow evaluation.

## Interpretation cautions

The financing uptake scenarios are interventions, not Case facts. Case account
midpoints do not establish signed contracts. No lease, loan default,
credit-loss, tax, opportunity-cost or liquidity-facility assumptions have
been invented. This schedule identifies cash exposure and arrears so those
risks can be stressed explicitly in the later robustness analysis.
