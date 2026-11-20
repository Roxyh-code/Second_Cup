# Strategy B baseline and independent Lever attribution

This is the **presentation / decision** view of the existing integrated model.

## Correct question

**Strategy B only** vs **Strategy B plus L1**, **plus L2**, **plus L3**.

The $40,000 one-time Corporate HQ setup and full $90,000 annual HQ
Corporate Sales Coordination cost are part of adopting Strategy B and
are present in *all eight* active Strategy B scenarios. They belong to
**no single lever**. A lever's benefit is its difference relative to
the identical Strategy B cost base:

```
NPV(Strategy B only) = B
Standalone L1 impact = NPV(B + L1) - NPV(B)
Standalone L2 impact = NPV(B + L2) - NPV(B)
Standalone L3 impact = NPV(B + L3) - NPV(B)
```

The fact that NPV(B + L1) might be slightly negative does **not** mean
L1 has negative value. It means the entire B business still struggles
to pay for its common fixed expense under the chosen participation
assumptions.

With dynamic franchise participation, default BASELINE assumes all 20
*informally interested* cafes eventually consent without financing,
although **the Case confirms no signed consent**. L1 adds 27 hypothetical
financing-unlocked cafes (two-thirds of the remaining 40 candidate cafes,
rounded). Their newly generated annual Corporate Sales contribute 7.5%
royalty to HQ; loan advances and repayments appear only in L1 cash flows.

L2 adds incremental landlord-introduced accounts to *actually participating*
cafes, net of CAC, additional $5,000 setup and $10,000/year HQ management.
L3 adds 5% of eligible Corporate Accounts sales after each participating
cafe recovers its **original program CAPEX**. This 5% is a transfer from
franchisees to HQ, **not** new coffee sales.

## Three complementary attribution views

1. **Standalone:** Each L1/L2/L3 added alone to B. Useful for evaluating
   whether an individual intervention adds HQ NPV to the same baseline.
2. **Waterfall:** B → B+L1 → B+L1+L2 → B+L1+L2+L3. The *incremental
   step contributions* sum exactly to the full incremental HQ NPV.
   Different sequencing can produce different step values.
3. **Shapley:** Average each lever's marginal HQ NPV across all six
   possible introduction orders; these values allocate the interaction
   benefits fairly without order bias. The Shapley values sum to the
   same total uplift from B to B+L1+L2+L3.

The standalone figures should **not** be summed as if they were an
integrated result. The incremental marginal L2 and L3 effects are much
larger **after L1 unlocks more cafes**. Synergies are quantified separately.

**Project viability is a different question from lever incrementality:**
always report total NPV, four-year HQ cash payback, 2027–2029 gross budget,
franchisee NPV, and separate $500k reserve diagnostics.

## Run

```bash
python strategy_b_attribution.py
python strategy_b_attribution.py --interest-conversion .5 --financing-conversion .25
python integrated_levers.py --participation-uplift
python -m unittest discover -s tests -v
```

Outputs in `outputs/strategy_b_attribution/`:

- `scenario_matrix.csv`: all 8 combinations, total HQ NPV, incremental
  HQ NPV vs B, separate common fixed HQ cost columns, and budget indicators.
- `isolated_lever_effects.csv`: three standalone effects.
- `cumulative_waterfall.csv`: business-oriented L1→L2→L3 increment bridge.
- `shapley_attribution.csv`: fair allocation of interactions.
- `lever_interactions.csv`: pairwise and three-way interactions.
- `hq_quarters.csv`, `owner_cohorts.csv`, `fee_schedule.csv`.
- `summary.json`, `assumptions.json`.

Original source Case drivers and the pre-existing fixed-60 legacy comparison
remain unchanged.

**Scope:** This is an NPV attribution model, not a causal estimate.
Franchisee consent, landlord conversion, fee acceptability and liquidity
should be validated by pilot interviews and contracts.
