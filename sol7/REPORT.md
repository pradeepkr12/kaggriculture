# sol7 — Report

**Date:** 2026-09-16. **Submission:** `56275780` (`sol7/main.py`). **Design:** `RESEARCH.md`.
**Status:** the research prototype was submitted as-is at the user's request; the research
build plan (M2 filler/cow-floor fix, M3 day-0 rollout, M4 territory routing) is not yet done.

## Why a new design

The oracle grid (1,152 games over sol5's cows/sheep/geese/strawberry counts) showed the best
*fixed* configuration beats sol5 by $18 — the CEM vector was already the fixed optimum —
while choosing the configuration per shop draw with oracle knowledge is worth +8.8k mean
margin. All remaining value is in adapting during the game; the planner recovers more than
the oracle (+11.9k plan-only, +17.1k with the sell rule, +26.4k with Hungarian) because it
also culls, re-times purchases and stacks with the labor fix.

## Results

See README table. Per-schedule margin vs sol6 (seed 3000, fresh): milk_starved −3.7k ·
yarnless +21.0k · yarn_x3 +16.0k · milk_rich +33.3k · random_a +15.7k · random_b +2.1k.

Revenue mix vs sol5 (mean/game): STRAW 35.5k vs 30.9k, WOOL 24.6k vs 14.5k, MILK 28.9k (140u)
vs 24.0k (225u), MELON 11.5k vs 15.0k, WHEAT 11.0k vs 6.1k, EGG 0.9k vs 1.7k.

## Known weaknesses (next iteration)

1. **Low-value draws** (milk_starved, bakery-heavy): 60-73k, loses to sol6 by ~4-5k. The
   goose valuation is too pessimistic (oracle: 8 geese optimal there) and idle labor is not
   converted to wheat/eggs aggressively enough; the field averages ~95k in these draws mostly
   through labor efficiency (walk share 46% vs our 56%).
2. **Day-0 cash split** unplanned: melon revenue 15.0k → 11.5k. Candidate for a fastsim
   rollout (10 budgets × 12-day rollouts at step 0).
3. **Cull-then-rebuy churn** (~$1.5k) when a yarn store appears after sheep were culled.
4. **Mirror flooding** in milk_rich (113.6k vs sol5 mirror 119k).
5. Adaptation errors are asymmetric (grid: 2 cows in milk_rich = −46k); keep the symmetric
   day-0 prior and add a cow floor until day 6.

## Validation performed before submission

- Baked `main.py` reproduces the prototype to the dollar on all 6 schedules × 2 seats.
- Kaggle-style loading (`env.run([path, "pass"])`) both seats: DONE/DONE, 171k / 168k.
- Fresh-seed matrices vs sol6: seeds 2000 and 3000, +13.8k / +14.1k, 10/12 each.
- Latency: p99 2 ms, max 110 ms (import) vs the 1 s actTimeout.
