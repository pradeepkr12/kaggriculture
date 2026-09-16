# sol7 Research: a structurally different agent, validated by simulation

*2026-09-16. Fable 5.1 research agent. All numbers below come from local simulations under `sol7/research/` (forced shop schedules, both seats, seed 1000). Nothing in sol1-sol6 was modified; nothing was submitted.*

## 1. Verdict

**Build sol7 as a model-based planner on top of sol5's mechanics layer: (a) a daily re-solved production plan that prices each product's remaining season with the engine's own price curve under the observed shop sinks and an exact model of the opponent's visible farm, choosing animal/strawberry counts by marginal *margin* value (my revenue minus what my flow costs the opponent) and culling animals whose remaining value is negative; (b) a stdlib Hungarian assignment for the crop crew; (c) an inventory-targeting sell rule.** The prototype (`sol7/research/planner/planner_hung.py`, ~450 new lines, zero tuned strategy vector) was validated on 6 forced shop schedules x both seats: **+26.4k mean margin vs sol5 (12/12 wins, mean 97.7k, worst schedule 73.4k), +30.0k vs a Gideon-like 6-cow/10-sheep flooder (12/12), +14.7k vs the submitted sol6 (10/12), 142.6k vs pass**, with p99 per-turn latency 1-2 ms (max 93 ms = first-turn import). For reference, no *fixed* strategy vector can do this: an exhaustive 96-config grid of sol5's animal/strawberry counts found that the best fixed config beats sol5 by +18 (eighteen dollars) mean margin, while choosing the config per schedule with oracle knowledge is worth +8.8k — the whole gain is in adapting, and the online planner recovers more than the oracle grid because it also culls, re-times purchases, and stacks with the labor fix. Online full-engine rollouts (direction 1) are feasible (a bit-exact stdlib simulator runs a full game in 10 ms) but are not needed for the core decisions; they are recommended only as a later add-on for the day-0 cash split and end-game liquidation. Learned components (direction 4) are dropped: the top replays' sell behaviour is "sell as produced" and prices are set by the shop draw, so there is nothing to clone from 10 games.

## 2. Feasibility table

| # | Direction | Upside estimate (evidence) | Cost | Risk | Verdict |
|---|---|---|---|---|---|
| 1 | Online model-based planning with the engine as simulator | Feasible: bit-exact stdlib re-implementation `sim/fastsim.py` validated step-for-step on the rank-1 replay (0 divergent steps of 719) and fresh engine games; 74.7k steps/s realistic load = full game 9.6 ms local (~20 ms Kaggle); ~138 five-day rollouts or ~25 full-game rollouts per 0.4 s turn; market-only 5-day rollouts 17k/s. The value of lookahead itself was not measured end-to-end. | High: needs a rollout policy + plan enumeration; 2-4x rollout cost for action generation | Medium: weeds/shop draws/opponent private state must be modelled; timeouts on slow CPUs | **Feasible; defer** to a second phase (day-0 budget split, end-game liquidation). Core decisions are captured analytically by (2b). |
| 2a | Exact labor assignment / routing | Hungarian assignment (70 lines, <0.2 ms/turn) on the existing score matrix: **+7.5k margin vs sol5, 24/24 paired wins**, walk share 0.589 -> 0.559; sol5 walks 59% of unit-turns (crop crew 67-72%), NN-tour bound says 39% of moves (1,674/game) are structurally avoidable (walk share floor ~0.36) | Low (assignment) / Medium (territory routing) | Low | **Build** (assignment now; territory routing as milestone 3, ceiling +10-20k only if the strategy layer absorbs the labor) |
| 2b | Production planning as a daily-resolved optimization | Oracle per-schedule grid: +8.8k mean margin available vs sol5 (range +1.7k to +22.9k), best fixed vector +18. Online planner (no oracle): **+11.9k** plan-only, **+17.1k** with the sell rule, **+26.4k** with Hungarian | Medium (done as prototype) | Medium: wrong adaptation is catastrophic (2 cows in milk-rich = -46k in the grid), so the planner must stay conservative when information is missing; it under-buys cows in milk-rich draws when run without the sell rule (110k vs sol5's 119k) | **Build** (core of sol7) |
| 3 | Opponent-aware market policy | Information basis verified on the rank-1 replay: opponent per-turn sales are exactly recoverable from market inventory deltas for 7 of 9 products (mismatch 0-12 turns of 719; wheat/fertilizer confounded by their unobservable buys), and their animals/crop tiles with placed_day/planted_day are public. As a *standalone* sell rule: **-0.4k** vs sol5 (worthless); as the opponent model inside the planner's marginal-margin objective + inventory targeting: +5.2k on top of plan-only (17.1k vs 11.9k), mostly in milk-rich (+20k) | Low | Low | **Build as part of 2b**, not as a separate policy |
| 4 | Learned components (BC / value net) | Top players hold 1-10 units mean at hour 12 and realized price/base is 0.2-1.8 depending on the shop draw, not on timing; 10 replays, hidden shed state; unverifiable | Medium | High | **Drop** |

## 3. Setup shared by every experiment

`sol7/research/harness.py` monkeypatches `kaggriculture._end_of_day` to force the town's shop sequence (draws at end of days 2,5,...,23) and `_commit_unit`/`_process_market` to record per-player per-product SELL revenue/units; it also times every agent call. Schedules (8 draws each):

| name | draws |
|---|---|
| milk_starved | BAKERY, BAKERY, BRUNCH_SPOT, FARMERS_MARKET, YARN_STORE, BAKERY, SMOOTHIE_SHOP, PET_CAFE (= rank-1 replay) |
| yarnless | PIZZA_SHOP, BAKERY, FARMERS_MARKET, BRUNCH_SPOT, ICE_CREAM_SHOP, PET_CAFE, BAKERY, SMOOTHIE_SHOP |
| yarn_x3 | FARMERS_MARKET, YARN_STORE, YARN_STORE, YARN_STORE, SMOOTHIE_SHOP, SMOOTHIE_SHOP, PET_CAFE, FARMERS_MARKET |
| milk_rich | PIZZA_SHOP, ICE_CREAM_SHOP, SMOOTHIE_SHOP, PIZZA_SHOP, ICE_CREAM_SHOP, SMOOTHIE_SHOP, PIZZA_SHOP, ICE_CREAM_SHOP |
| random_a / random_b | `random.Random(7)` / `random.Random(11)` `.choices(sorted(SHOPS), k=8)` |

Opponents: `sol5` = `sol5/farmlib.build_agent(SEED_VEC)`; `gideon` = sol5 with `n_cows=6, n_sheep=10`; `pass`; `mirror` = candidate vs itself; `sol6` = `sol6/main.py build_agent(VEC)` (read-only). Every matrix cell = 6 schedules x 2 seats = 12 games, seed 1000 (weeds only; the shop draw is forced).

### 3.1 Baseline: sol5 on the matrix (`results/baseline_sol5.json`)

| sol5 vs | me | opp | margin | wins | worst | milk_starved | yarnless | yarn_x3 | milk_rich | random_a | random_b |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sol5 (mirror) | 79,195 | 79,195 | 0 | 6/12 | 55,522 | 55,597 | 68,766 | 80,252 | 118,978 | 60,152 | 91,427 |
| gideon | 77,850 | 70,966 | +6,884 | 9/12 | 45,568 | 45,985 | 78,374 | 80,416 | 111,769 | 58,775 | 91,778 |
| pass | 121,207 | 3,000 | +118,207 | 12/12 | 90,401 | 91,216 | 125,795 | 118,356 | 148,162 | 101,223 | 142,491 |
| sol6 | 85,839 | 92,112 | -6,273 | 2/12 | 55,177 | 56,499 | 85,908 | 91,243 | 118,376 | 68,042 | 94,965 |

The mirror already spans 55.6k-119k purely from the shop draw. sol5 loses to the Gideon-like variant in yarn_x3 (-15.5k) and to sol6 everywhere except yarnless.

### 3.2 Oracle grid: how much is adaptation worth? (`results/oracle_grid.json`, 1,152 games)

Sweep of sol5's `n_cows` {2,4,6,10} x `n_sheep` {2,4,7,10} x `n_geese` {1,4,8} x `straw_tiles` {20,32} vs fixed sol5, per schedule, both seats.

| schedule | oracle best cfg (cows/sheep/geese) | me | margin vs sol5 | 2nd best |
|---|---|---|---|---|
| milk_starved | 2 / 4 / 8 | 70,592 | **+11,515** | 4/7/4 +11,055 |
| yarnless | 10 / 4 / 4 | 69,369 | +1,676 | 10/4/1 (= sol5) 0 |
| yarn_x3 | 2 / 10 / 1 | 109,556 | **+22,919** | 4/10/1 +21,534 |
| milk_rich | 10 / 2 / 1 | 121,654 | +1,915 | 10/4/1 (= sol5) 0 |
| random_a | 4 / 2 / 4 | 74,917 | **+9,826** | 6/2/1 +5,799 |
| random_b | 10 / 7 / 1 | 94,751 | +4,828 | 6/7/1 +1,008 |
| **mean** | | 90,140 | **+8,780** | |

Best *fixed* config over all schedules: 6/7/1 at **+18** mean margin (per schedule +5.1k, -4.8k, +14.6k, -14.8k, -0.9k, +1.0k); sol5's own 10/4/1 is second at 0. So CEM has already found the fixed optimum; the remaining value is only reachable by adapting per draw. Adaptation errors are asymmetric: 2 cows in milk_rich costs -46k, 10 sheep in milk_rich -26k, 8 geese in milk_rich -24k; straw 20 instead of 32 costs -1.4k to -7.3k everywhere.

## 4. Prototypes

### 4.1 Direction 1: fast simulator (`research/sim/`, `results/sim_feasibility.json`)

What: `fastsim.py`, a pure-stdlib re-implementation of the full transition (tiles, units, shed/inventories, lockstep market, town consumption, daily refresh, decay, weeds via the engine's RNG or injectable forced shops). Validation: replaying the rank-1 game's 719 recorded action pairs and comparing farms (all tile fields, money, positions, quadrants), market inventory/prices, town and both privates after every step: **exact match, 0 divergences**; cross-validated on fresh engine games (seed 1) with PASS and busy policies (exact in rng mode; 4-5 weed tiles patched in no-weed mode).

| workload | engine `interpreter()` steps/s | `env.step()` steps/s | fastsim steps/s | fastsim full game |
|---|---|---|---|---|
| both PASS | 61,400 | 2,230 | 800,000 | 0.9 ms |
| busy (~10 units/farm) | 35,200 | 1,500 | 160,000 | 4.5 ms |
| rank-1 replay actions | 21,000 | 740 | 74,700 | 9.6 ms |

Budget at 0.4 s/turn Kaggle-time (2x slowdown) + 60 s overage/720 turns: ~575 one-day rollouts, ~138 five-day rollouts, ~25 full-game rollouts per turn with real actions (divide by 2-4 for the rollout policy's own cost); market-only 24-step rollouts 21,500/turn. Verdict: feasible, but the experiments below show the core decisions do not need it.

### 4.2 Direction 2a: labor assignment (`research/labor/`, `results/labor_*.json`)

What: `farmlib_labor.py` = sol5 + stdlib Hungarian (O(n^3), n <= 12 units x <= 40 tasks) replacing the greedy unit-centric sweep; feeders, "finish where you stand" pre-pass, eligibility and the commitment bonus are unchanged. Flag off reproduces sol5 exactly.

Measurements: sol5 walks **58.9%** of unit-turns (feeders 23-29%, crop crew 67-72%; the top player walks 46%). Offline on ~650 logged turns/game the greedy assignment is suboptimal on 57-60% of turns (mean +5 score, 0.4-0.8 moves saved, and 13-14% of turns leave a unit unassigned that Hungarian assigns). Route bound: per-unit nearest-neighbour tours over the tiles actually visited would cut 4,327 moves/game to 2,653 (walk share 0.58 -> 0.36); 17% of tile visits are duplicated across units.

| opponent | variant | me | opp | margin | wins | worst | walk share | lat p99 / max |
|---|---|---|---|---|---|---|---|---|
| sol5 | control | 79,195 | 79,195 | 0 | 6/12 | 55,522 | 0.589 | 0.98 / 78 ms |
| sol5 | **Hungarian** | **86,718** | 76,568 | **+10,150** | **12/12** | 62,343 | 0.559 | 0.93 / 80 ms |
| pass | control | 121,207 | 3,000 | +118,207 | 12/12 | 90,401 | 0.587 | 1.0 / 52 ms |
| pass | **Hungarian** | **128,531** | 3,000 | +125,531 | 12/12 | 97,319 | 0.561 | 0.72 / 57 ms |

Paired per-game delta +7,523 vs sol5 (min +193, 12/12 positive) and +7,324 vs pass; the extra ~130 actions/game go almost entirely into strawberry (+30 units, +$5.0k). Hungarian cost 0.04 ms mean, 0.2 ms max per turn. Failure cases: none observed; idle share rises to ~9%, i.e. the strategy layer, not labor, becomes the binding constraint.

### 4.3 Directions 2b + 3: daily production planner + opponent model (`research/planner/`, `results/planner_*.json`)

What (`planner.py`, on `farmlib_p.py` = sol5 + 4 hooks: dynamic animal targets, cull set, sell override, hands schedule):
1. Sink model: `1 + 6 x (multi-product shop instances containing p) + 12 x (single-product instances)` units/day per product from `obs.town.unlocked_shops`, plus the expectation of the remaining draws (E per draw: wheat 3.75, strawberry 3.0, milk 2.25, egg/carrot/tomato 1.5, wool 1.5 units/day).
2. Opponent model: production capacity per future day from their public tiles (`placed_day + first_yield_day` per animal at 1.5 milk / 1.33 wool / 2 eggs per day; `planted_day + 10` per strawberry tile), calibrated by their observed sales (market delta + town consumption - my committed sales, rolling 3 days, factor clipped to [0.5, 1.3]); on day 0-1 with nothing visible, a symmetric prior (the opponent builds what I build).
3. Value: for one more cow/sheep/goose/strawberry tile, simulate that product's inventory trajectory to day 29 (`inv += mine + theirs + extra - sink`), price every extra unit with `market_price`, add fertilizer value, subtract purchase + wheat + labor at $25/action, **and add the revenue the price drop removes from the opponent's flow** (2-player rating game: the objective is the margin). Buy while positive (<= 6/day, <= 24 animal slots, engine deadlines cow d19 / sheep d21 / goose d24); stop feeding (cull, escape after 2 days) one animal/day of any type whose remaining value is negative (days 10-27).
4. Sell override for STRAWBERRY/MILK/WOOL/TOMATO/CARROT: if the opponent's forecast flow >= 0.9 x sink, sell everything now; else sell down to I0 (scarcity side is free), plus one consumption tick of the residual sink, plus a reservation fraction decaying 0.9 -> 0.25 from day 10; liquidate if the excess cannot drain before the end; hold cap 1.5 days of residual sink. MELON/EGG/WHEAT/FERTILIZER keep sol5's rules.
5. Hands: 6 (d0-3), 9 (d4-7), 11 (d8-28), 8 (d29) — the winners' schedule.

Constants are engine-derived (yields, deadlines, price curve) plus one opportunity-cost constant ($25/action) and the reservation decay; no CEM.

Ablation, margin vs sol5 (12 games each; `results/planner_ablation.log`):

| variant | me | margin vs sol5 | wins | milk_starved | yarnless | yarn_x3 | milk_rich | random_a | random_b | vs gideon | vs pass | mirror |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sell_only (sol5 production + new sell rule) | 78,780 | -356 | 5/12 | -1,119 | -2,344 | -4,412 | +4,272 | -854 | +2,318 | +6,699 | 124,958 | 79,344 |
| plan_only (planner + sol5 selling) | 87,388 | **+11,941** | 12/12 | +8,260 | +10,444 | +14,832 | +6,638 | +15,311 | +16,162 | +16,246 | 136,594 | 84,825 |
| both | 91,901 | **+17,145** | 12/12 | +11,061 | +13,305 | +16,962 | +27,026 | +15,488 | +19,027 | +21,596 | 134,795 | 80,942 |
| **both + Hungarian** (`planner_hung.py`) | **97,746** | **+26,380** | **12/12** | +17,237 | +19,078 | +43,509 | +35,972 | +18,734 | +23,750 | **+29,968** | **142,625** | 83,329 |

Full table for the recommended variant (`results/planner_hung.json`, `results/vs_sol6_planner_hungarian.json`):

| planner+Hungarian vs | me | opp | margin | wins | worst | milk_starved | yarnless | yarn_x3 | milk_rich | random_a | random_b |
|---|---|---|---|---|---|---|---|---|---|---|---|
| sol5 | 97,746 | 71,366 | +26,380 | 12/12 | 73,379 | 73,485 | 82,738 | 117,398 | 136,767 | 77,492 | 98,598 |
| gideon (6 cows/10 sheep) | 96,760 | 66,793 | +29,968 | 12/12 | 60,704 | 61,456 | 91,103 | 112,008 | 139,472 | 79,420 | 97,102 |
| pass | 142,625 | 3,000 | +139,625 | 12/12 | 90,641 | 92,326 | 133,876 | 165,579 | 185,109 | 113,106 | 165,754 |
| mirror | 83,329 | 83,329 | 0 | — | 59,764 | 59,932 | 73,600 | 95,811 | 113,620 | 70,730 | 86,280 |
| **sol6 (submitted)** | 100,704 | 86,025 | **+14,678** | **10/12** | 64,793 | 64,850 (-5,076) | 92,214 (+23,868) | 115,668 (+13,430) | 152,458 (+35,926) | 84,396 (+14,790) | 94,636 (+5,132) |

Revenue mix vs sol5 (mean per game, $ / units): sol5 baseline STRAW 30.9k/144, WOOL 14.5k/127, MILK 24.0k/225, MELON 15.0k/84, FERT 12.6k/298, WHEAT 6.1k/127, EGG 1.7k/31 (total 108.2k); planner+Hungarian STRAW 35.5k/172, WOOL 24.6k/135, MILK 28.9k/140, MELON 11.5k/54, FERT 12.5k/245, WHEAT 11.0k/238, EGG 0.9k/13 (total 128.9k). The planner sells 85 fewer milk units for $4.8k more, 8 more wool units for $10.1k more, and converts idle labor into wheat.

Latency (this machine, 96 games): mean 0.2-0.3 ms/turn, p99 <= 2 ms, max 93 ms on turn 0 (module import). Against the 1 s actTimeout at an assumed 2x slower Kaggle CPU the steady-state margin is >200x; the day-0 import must stay under ~0.4 s (currently ~0.2 s).

Failure cases seen:
- Milk-starved draw vs sol6: -5.1k (64.9k vs 69.9k). Both agents shrink livestock; sol6's cows-by-milk-sink rule is more aggressive early and its geese-by-egg-sink rule out-earns the planner's goose valuation (the planner buys 1-2 geese; the oracle grid says 8 geese is the milk-starved optimum).
- plan_only in milk_rich: 110.5k < sol5's 119.0k. The symmetric day-0 prior makes the planner buy 5 cows instead of 10 and it does not catch up fast enough after the day-3 PIZZA_SHOP; the sell rule (selling down to I0 on the scarcity side) recovers it to 134-137k.
- Cull-then-rebuy: in milk_starved the planner culls 3 sheep on days 10-13 (wool at 0 yarn stores) and buys 5 on day 15 when YARN_STORE appears — correct given the information, but ~$1.5k of churn.
- Melon revenue falls 15.0k -> 11.5k (84 -> 54 units): day-0 cash goes to 5 cows + 4 sheep (~$4k) and melon seeds are bought later; the day-0 cash split is not planned (candidate for a fastsim rollout).
- Mirror milk_rich 113.6k < sol5 mirror 119.0k: two planners both see the milk sink and both flood it; the symmetric prior only applies on days 0-1.
- The standalone sell rule is worthless (-356) and the "opponent floods -> sell now" branch triggers almost permanently for strawberry (their flow ~6/day vs sink 7); its value comes only in combination with production that matches the sink.

## 5. Recommended sol7 architecture

```
obs ──> FlowTracker (per turn) ── market delta + town consumption − my committed sales ──> opponent sales history
   ──> DailyPlanner (hour 0) ── shops → sink/day; opponent tiles → capacity/day; price-curve season sim
   │                            → targets {cows, sheep, geese, strawberry tiles}, cull set, hands target
   ├──> Mechanics layer (sol5 farmlib, unchanged semantics): tile scan, feeder routes, task generation,
   │        feeding guarantee, shed/drop logistics, atomic-plant rule, SELL-first ordering, ≤10 orders
   │        + Hungarian assignment for the crop crew (replaces the greedy sweep)
   └──> SellPolicy (per turn) ── inventory targeting vs sink, opponent-flood exit, decaying reservation,
                                  end-game liquidation; sol5 rules for MELON/EGG/WHEAT/FERTILIZER
```

Stays from sol5 (proven): everything in `farmlib.py` except the three hook points (`animal_targets`, `animal_pending`, `sell_qty`) and the assignment loop; `main.py` baking via `make_main.py`. New: `planner.py` (~330 lines), Hungarian (~70 lines), the 4 hooks (~40 lines). All stdlib. No strategy vector: `SEED_VEC` remains only as the source of the untouched mechanical knobs (drop threshold, wheat buffer, taper day, melon tiles).

Risks and mitigations:
- **Adaptation errors are asymmetric** (grid: -46k for 2 cows in milk_rich). Keep the symmetric day-0 prior, keep the purchase cap of 6/day, and add a floor of 4 cows until day 6 (the planner's plan_only milk_rich result shows the cost of under-buying when the sink arrives early).
- **Low-value draws still score 60-73k** (milk_starved 73.5k vs sol5, 64.9k vs sol6) while the field averages ~95k. The oracle grid says 8 geese is the milk_starved optimum; the planner's goose valuation (labor $25/action, egg base $50) is too pessimistic. Validate a lower labor opportunity cost or an explicit "filler" rule (geese while projected idle unit-turns > 12/day).
- **Mirror/self-similar opponents** (two planners flood the same sink): margin 0 by symmetry, but absolute 83k; acceptable.
- **Day-0 cash split** (animals vs melon seeds) is not optimized; melon revenue dropped $3.5k. This is the one place a fastsim rollout (Section 4.1) is cheap and well-defined: enumerate ~10 day-0 budgets, roll out 12 days with the default policy.
- **Timeout:** steady-state <2 ms p99; keep imports minimal in `main.py`; guard the planner with a try/except that falls back to the previous day's targets.

Build / validation plan (milestones gated on the schedule matrix, both seats, opponents {sol5, gideon, sol6, mirror, pass}):
1. **M1 (1 day):** port `planner_hung.py` + `farmlib_ph.py` into `sol7/farmlib.py`, bake `main.py`, verify bit-identical scores to the prototype on seed 1000 and error-free standalone both seats. Gate: reproduce +26.4k vs sol5, +14.7k vs sol6.
2. **M2 (1 day):** fix the two known weaknesses — goose/filler valuation and the cow floor — and add sol6 to the standard matrix. Gate: >= 0 margin vs sol6 on every schedule including milk_starved; worst absolute >= 70k vs sol6.
3. **M3 (1-2 days):** day-0 budget rollout with `fastsim` (10 candidates x 12-day rollouts, run once at step 0 inside the 60 s overage). Gate: melon revenue back to >= 15k without losing animal margin.
4. **M4 (2 days, optional):** territory routing for the crop crew (per-unit tile sets, water-then-harvest sequencing) toward the NN bound (walk share 0.56 -> ~0.4). Gate: +5k vs M2 on the matrix with the same strategy.
5. **Validation before submission:** 3 seeds x 6 schedules x 5 opponents x 2 seats (360 games, ~2 min on 12 workers); latency histogram; Kaggle-style run via `env.run(["main.py", ...])`.

## 6. Reproduction (python = `/opt/miniconda3/envs/env2/bin/python`, cwd = `sol7/research`)

| result | command | output |
|---|---|---|
| sol5 baseline matrix (Section 3.1) | `python harness.py --cand sol5 --opps sol5,gideon,pass,mirror --workers 6 --out results/baseline_sol5.json` | `results/baseline_sol5.json` (25 s) |
| oracle grid (3.2) | `python planner/oracle_grid.py 6` | `results/oracle_grid.json` (512 s) |
| fastsim validation + throughput (4.1) | `cd sim && python run_all.py` | `results/sim_feasibility.json`, `bench_engine.json`, `bench_fastsim.json`, `validate_replay.json` (~8 s) |
| labor: walking share, offline Hungarian, online matrix, route bound (4.2) | commands listed in `results/labor_index.json` (`cd labor && python measure_walk.py; python offline_assign.py; python online_run.py; python route_bound.py`) | `results/labor_walking.json`, `labor_offline_assign.json`, `labor_hungarian.json`, `labor_route_bound.json` |
| replay: opponent-sales inference, tile visibility (Dir. 3 basis) | `python planner/replay_obs.py /private/tmp/109564916.json` | `results/replay_obs.txt` |
| replay: top players' holding behaviour (Dir. 4) | `python planner/replay_sellpolicy.py` | `results/replay_sellpolicy.json` |
| planner ablation (4.3) | `python planner/run_ablation.py 8 both,plan_only,sell_only` | `results/planner_{both,plan_only,sell_only}.json`, `planner_ablation.log` (45 s) |
| planner + Hungarian matrix (4.3) | `python planner/_patch_hooks.py labor/farmlib_labor.py planner/farmlib_ph.py && python planner/run_hung.py 10` | `results/planner_hung.json`, `planner_hung.log` (14 s) |
| vs submitted sol6 (4.3) | `python planner/run_vs_sol6.py 12` | `results/vs_sol6_planner_hungarian.json`, `vs_sol6_sol5.json`, `vs_sol6.log` (10 s) |
| single verbose planner game (daily plan log) | `python planner/planner.py milk_starved sol5` | stdout |

Files: `harness.py` (forced schedules, instrumentation, latency, ProcessPool matrix); `planner/farmlib_p.py` (sol5 + hooks), `planner/farmlib_ph.py` (labor copy + hooks, generated), `planner/planner.py` (planner, sell rule, builders), `planner/planner_hung.py` (recommended variant); `labor/farmlib_labor.py` (sol5 + Hungarian + instrumentation); `sim/fastsim.py` (validated simulator).
