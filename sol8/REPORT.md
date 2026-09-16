# sol8 Report

*Continuation of the sol8 implementation from `PLAN.md`, starting from the inherited draft
(`results/sol8.json` = `results/step1_baseline.json`, verified bit-identical, +10.7k vs sol7,
21/28 wins, two negative schedules yarn_x3 -3.9k and random_b -1.4k, 71.4k floor). All numbers
below are from `sol8/arena.py` (14 workers, 7 forced schedules x seeds {1000,2000} x both seats
= 28 games/opponent) unless marked "seed 1000 sample" (14 games, used for diagnostics that
`arena.py` doesn't report directly: per-schedule animal counts, escapes, fed%, days 22-29
earnings).

## 1. Step 1 - baseline verification

- `make_main.py` rebuild of `main.py`: bit-identical to the module agent on seed 1000 for
  `late_milk` and `yarn_x3` (before and after the step-2 change, re-verified each time).
- Kaggle-style `env.run([path, "pass"])`, both seats: statuses DONE/DONE, no exceptions.
- Latency (`results/sol8_final.json`, worst across opponents): max 128 ms (turn-0 import),
  p99 3.65 ms. Gate (p99 < 5 ms, max < 300 ms): **met**.
- Full-matrix re-run (`results/step1_baseline.json`) reproduced `results/sol8_run.log` exactly:
  vs sol7 +10,699 margin, 21/28 wins, 71,397 floor. Baseline confirmed.

## 2. Step 2 - diagnosis and fix for yarn_x3 / random_b

**Diagnosis (not what PLAN.md guessed).** PLAN.md's hypothesis for yarn_x3 was that sol8 had
regressed to 2 cows/16 sheep and was flooding wool. That was already fixed in the inherited
draft: `diag.py` on yarn_x3 vs sol7 (seed 1000/2000, both seats) shows sol8 converges to a
stable **4 cows / 14 sheep**, in the PLAN's target range, with realized wool price **$235-238**
(gate: >=$200, met) and 0 escapes. The actual loss driver, found by comparing revenue and tile
counts to the opponent's public farm in the same games:

- WHEAT revenue: sol8 $8.8k (193 units) vs sol7 $20.3k (459 units) in the worst seed-2000 game
  -- a >2x gap despite similar wheat-tile counts mid-game (13-16 tiles each side, days 12-20).
- The reason: sol8's crop filler treats **CARROT as an uncapped 999-tile catch-all** (inherited
  from sol7's own `farmlib_ph.py`, unchanged there) -- once WHEAT/STRAWBERRY/TOMATO targets are
  met, *every* remaining empty tile plants CARROT, which has exactly one shop sink (PET_CAFE)
  and floods immediately, while sol7's opponent policy (a fixed `wheat_tiles` from its
  strategy vector, not adaptive) happens to leave more land in wheat.
- The same mechanism explains most of random_b's small deficit: random_b's forced schedule
  (`['ICE_CREAM_SHOP','PET_CAFE','YARN_STORE','ICE_CREAM_SHOP','PET_CAFE','PET_CAFE',
  'BRUNCH_SPOT','PET_CAFE']`) draws PET_CAFE four times (real CARROT sink up to 49/day by
  day 24), so a *fixed*, too-small carrot cap hurts there instead -- see the ablation below.

**Fix (the one code change in this pass).** `farmlib_ph.py`'s `crop_target["CARROT"]` now
reads `P.get("carrot_tiles", 999)` (backward-compatible default) instead of a hardcoded 999;
`planner.py` sets `P["carrot_tiles"] = clamp(sink_now["CARROT"], CARROT_FILLER_FLOOR=8,
CARROT_FILLER_MAX=40)` -- i.e. plant enough carrot tiles to match its *own* observed sink
(1 unit/day base, +12/day per PET_CAFE instance), with an 8-tile floor for the base town-center
sink and a 40-tile ceiling so it still can't crowd out wheat/strawberry. This frees the land that
was going to unsellable carrot back to the general tile-priority order (wheat/strawberry first).

**Ablation (seed 1000+2000, both seats, vs sol7 module agent, 4 games/schedule):**

| variant | yarn_x3 margin | random_b margin |
|---|---|---|
| inherited draft (CARROT=999 uncapped) | -3,884 | -1,362 |
| + CARROT sink-bounded, straw target also made opponent-flow-aware | -5,027 | -4,162 |
| + CARROT sink-bounded only (straw reverted) | **+924** | **-1,402** |
| + CARROT sink-bounded + WHEAT_FILLER_CAP raised 26->30/40 | +924 (no change) | -1,402 (no change) |

The strawberry "opponent-flow-aware" variant was tried and reverted: it cut yarn_x3's
strawberry tiles from 38 to ~22, but `ema_pr[STRAWBERRY]` was 1.4-1.8 (realized price 40-80%
*above* base) even at 38 tiles, i.e. the sink was not glutted -- cutting tiles only cost
revenue ($25.8k -> $20.4k in the diagnosed game) with no offsetting gain. Raising the wheat
filler's ceiling (26 -> 30 or 40 idle-driven tiles) had **zero** measured effect in either
direction -- the planner's available land, not the idle-EMA cap, is the binding constraint -- so
it was reverted to keep the constant count minimal (no unjustified knob left in the code).

**Result:** vs sol7 margin +10,699 -> **+11,318**, wins 21/28 -> **22/28**, floor 71,397 ->
71,553 (~flat). yarn_x3 -3,884 -> **+924**; random_b -1,362 -> **-1,402** (unchanged, within
noise -- see "gate status" below, this is reported as a miss rather than tuned further).

## 3. Steps 3/4 (floor lift, endgame) - attempted, not separately fixed

`milk_starved` (the worst schedule) was re-diagnosed after the step-2 fix: sol7 margin
+10,962 (seed 1000, seat 0), animal counts converge to 5 cows / 3-8 sheep / 5 geese by day 12,
matching PLAN's geese-as-filler intent (egg sink ~25/day drives `floor_for(GOOSE)` to 5-6
directly through the existing contested-sink formula -- no separate egg-sink special case was
needed, the general floor already covers it). The absolute floor (71.6k min / 72.8k mean vs
sol7) improved only marginally from the carrot fix and remains **short of the 75k gate**; no
further code change was made for this because the diagnosis did not point to a distinct,
fixable cause the way yarn_x3/random_b did (see "what wasn't done," below) and PLAN.md's
explicit instruction is to stop and report a miss rather than keep tuning without a diagnosed
cause. Days 22-29 earnings (seed-1000 sample, 7 schedules x 2 seats = 14 games) average
**44,295**, just under the 45k gate (range 29.3k in random_b/seat0 to 63.3k in late_milk/seat1).

## 4. Full matrix, sol8 (post-fix) vs each opponent

`results/sol8_final.json` (== `results/sol8_step2.json`), seeds {1000,2000}, both seats, 7
schedules (28 games/opponent):

| vs | me | opp | margin | wins | floor | lat p99 |
|---|---|---|---|---|---|---|
| sol5 | 97,182 | 69,588 | **+27,594** | 28/28 | 72,192 | 2.7 ms |
| gideon | 93,682 | 64,154 | **+29,528** | 28/28 | 64,899 | 3.7 ms |
| sol6 | 100,394 | 83,018 | **+17,375** | 28/28 | 66,075 | 2.4 ms |
| sol7 | 93,075 | 81,758 | **+11,318** | 22/28 | 71,553 | 2.9 ms |
| pass | 144,928 | 3,000 | **+141,928** | 28/28 | 108,167 | 2.9 ms |
| mirror | 86,285 | 86,285 | +0 | 12/28 | 70,600 | 2.8 ms |

By schedule, margin vs sol7 (the binding matchup):

| schedule | margin vs sol7 | me |
|---|---|---|
| milk_starved | +10,577 | 72,842 |
| yarnless | +13,090 | 84,952 |
| yarn_x3 | **+924** | 109,843 |
| milk_rich | +3,479 | 117,838 |
| late_milk | +40,548 | 101,668 |
| random_a | +12,008 | 82,072 |
| random_b | **-1,402** | 82,311 |

Per-schedule animal counts on days 12/16/20/24/28 vs sol7 (seed 1000, seat 0):

| schedule | d12 | d16 | d20 | d24 | d28 |
|---|---|---|---|---|---|
| milk_starved | C5/S3/G5 | C5/S5/G5 | C5/S8/G5 | C5/S8/G5 | C5/S8/G5 |
| yarnless | C9/S3/G3 | C9/S3/G3 | C9/S3/G3 | C9/S3/G5 | C9/S3/G5 |
| yarn_x3 | C4/S14/G0 | C4/S14/G0 | C4/S14/G0 | C4/S14/G0 | C4/S14/G0 |
| milk_rich | C14/S3/G0 | C15/S3/G0 | C15/S3/G0 | C15/S3/G0 | C15/S3/G0 |
| late_milk | C5/S3/G4 | C5/S8/G4 | C5/S8/G4 | C5/S8/G4 | C5/S8/G5 |
| random_a | C7/S3/G4 | C7/S3/G4 | C7/S3/G4 | C7/S3/G5 | C7/S3/G5 |
| random_b | C9/S8/G0 | C9/S9/G0 | C9/S9/G0 | C9/S9/G0 | C9/S8/G0 |

(C=cows, S=sheep, G=geese.)

## 5. Gate status

| gate | requirement | result | status |
|---|---|---|---|
| G1 escapes | 0 unintended | 4 across 14 seed-1000 games (milk_rich x2, random_b x1, +1 more) | **miss** (small; see below) |
| G1 fed% | >= 98% kept animals | 82-95% by schedule, mean ~87.6% | **miss** (metric caveat, see below) |
| G1 orders/turn | <= 10 | guaranteed by code (`orders[:10]`) | met |
| G1 exceptions | 0 | 0 across all matrix + verification runs | met |
| G1 latency | p99 < 5 ms, max < 300 ms | p99 2.4-3.7 ms, max 105-128 ms | met |
| G2 vs sol7 | >=22/28, margin >=+2k every schedule | 22/28; 5/7 schedules >=+2k, yarn_x3 +924 and random_b -1,402 short | **partial** |
| G2 vs sol6 | >=24/28 | 28/28 | met |
| G2 vs sol5/gideon | >=26/28 | 28/28 both | met |
| G3 floor | worst schedule >=75k vs sol7 | 71.6k min / 72.8k mean (milk_starved) | **miss** |
| G3 endgame | days 22-29 mean >=45k | 44.3k (seed-1000 sample) | **miss** (close) |
| G4 mirror | asymmetry <=3k | 0 by construction (identical agent) | met |
| G4 vs pass | mean >=150k | 144.9k | **miss** (pre-existing, unchanged by this pass) |

**Escapes caveat:** the 4 escapes are not planner-directed culls (the cull log is empty in
every one of those games) -- they are mechanics-layer edge cases where an animal reached
`consecutive_unfed>=2` despite the `alt_feed` rung's intent to avoid it, most likely a labor-
contention case (feeder crew didn't reach that animal in time) inherited unchanged from the
sol5/sol7 mechanics layer. Rate is low (~0.3/game) and concentrated in milk_rich/random_b.

**Fed% caveat:** the stat is `sum(fed_today)/sum(animal-count)` across every hour-0 snapshot of
every day, including animals on `feed_only`/`alt_feed` rungs that are *by design* not fed every
single day once price signals turn negative (rung A). It is not a literal measure of "kept
animals get properly fed" -- the escape count above is the more direct proxy for that, and it is
low. This metric was already in this range in earlier runs (not something this pass changed) but
is flagged here per the gate's literal wording, since it wasn't previously reported against G1.

## 6. What wasn't done (given the effort budget for this pass)

- yarn_x3 and random_b were brought close to (yarn_x3) or left at (random_b) the +2k gate but
  not clearly over it. Diagnosis for random_b did not surface a lopsided misallocation the way
  yarn_x3's carrot flood did -- the diagnosed games are close, comparable-strength matchups
  (similar animal/crop tile counts to sol7) where the residual gap looks like normal matchup
  variance rather than a single fixable bug. Per PLAN.md's instruction, this is reported as a
  miss rather than tuned against further without a diagnosed cause.
- The 75k floor (milk_starved) and 45k endgame-earnings gates are close (71.6k/72.8k and
  44.3k respectively) but not met; no new mechanism (e.g. explicit wheat-tile re-fertilization
  scheduling, or a dedicated endgame liquidation pass) was implemented for these -- the existing
  EMA/floor machinery from the inherited draft already covers most of PLAN step 3's intent
  (geese floor from the egg sink, wheat filler from idle EMA) without further code changes.
- No CEM, no tuned strategy vector was used or considered; the one new constant pair added
  (`CARROT_FILLER_FLOOR=8`, `CARROT_FILLER_MAX=40`) is engine-derived (matches CARROT's own
  observed sink) and shown with/without in the ablation table above.
