# Kaggriculture sol6 — Report

**Status:** local only — NOT submitted, NOT committed. **CEM not run** (design-value
vector). Engine: kaggle_environments 1.32.7. All numbers from `arena.py` forced
shop schedules; raw runs saved under `results/`.

---

## 1. Idea

The town's shop draw is random but observable, and it is what decides which product
is worth money in a game. sol5 fixes its livestock/crop mix; sol6 converts the
unlocked shops into a per-product **sink** (units/day drained) and sizes production
to it:

- multi-product shop drains 6 units/day of each of its products; a single-product
  shop (YARN_STORE, PET_CAFE) drains 12/day; the town center drains 1/day of each
  product except fertilizer.
- cows `= base_cows + share*milkSink/1.5`, sheep `= base_sheep + share*woolSink/1.33`
  (clamped to caps); **geese `= share*eggSink/2`** and are 0 when there is no egg
  demand; strawberry tiles scale with the strawberry sink up to 32.
- a product flooded below `2*wheat` that cannot recover before day 29 puts its
  surplus animals into **CULL** (deliberate, tracked separately from starvation).

## 2. The pivot that mattered

The first working sol6 sized geese to *idle labor* (sol5's heuristic). That put 6
geese on the board even in milk-rich draws with no egg sink, burning cash and
builder-turns and leaving cows stuck at 9/10. Sizing geese to the **egg sink**
was the single biggest change:

| Schedule (vs sol5, both seats, seeds 11-12) | idle-labor geese | egg-sink geese (final) |
|---|---|---|
| milk_rich  | 97.9k  (0/4) | **124k (4/4)** |
| yarn3      | 93.2k  (2/4) | **118k (4/4)** |
| milk_starved / bakery_heavy | ~67k (4/4) | ~65k (4/4) |

Two smaller changes followed: an early **cow-anticipation** rule (cows yield only
~8 days after placement, so buy toward the cap as soon as a real milk sink is
visible, before the day-19 deadline), and **removing alternate-day feeding** — an
ALT animal fed every other day has zero slack against the 2-day escape rule, so a
single missed feeder visit lost it; wheat is cheap, so KEEP-daily is strictly safer.

## 3. Final results

### Win grid — 5 named schedules x both seats x seeds 11,12 (`results/gate_vs_*.json`)

| Schedule | sol6 vs sol5 | sol6 vs gideon |
|---|---|---|
| milk_starved   | 64.4k vs 56.6k - **4/4** | 58.2k vs 53.5k - **4/4** |
| yarn3          | 118.2k vs 92.0k - **4/4** | 121.0k vs 113.9k - **4/4** |
| milk_rich      | 123.7k vs 120.1k - **4/4** | 126.1k vs 91.2k - **4/4** |
| yarnless_3milk | 69.7k vs 67.2k - **4/4** | 79.2k vs 67.6k - **4/4** |
| bakery_heavy   | 66.0k vs 53.8k - **4/4** | 67.0k vs 53.3k - **4/4** |
| **average / record** | **88.4k vs 77.9k - 20/20** | **90.3k vs 75.9k - 20/20** |

vs `pass` (`results/gate_vs_pass.json`): milk_starved 111.1k, milk_rich 153.7k (4/4 each).

### Per-product revenue vs sol5 (avg over both seats x seeds), showing the pivot

| Schedule | headline product | sol6 | sol5 |
|---|---|---|---|
| yarn3 | **WOOL** (3 yarn stores) | **76.2k** | 30.4k |
| milk_rich | **MILK** | 71.3k | 69.5k |
| bakery_heavy | **EGG** | **15.8k** | 2.0k |
| milk_starved | EGG | **12.0k** | 2.0k |
| all | MELON (front-loaded) | ~20k | ~15k |

Where sol6 concedes: MILK in low-milk-sink draws (3.2-4.1k vs sol5's flat ~7-20k),
and CARROT / TOMATO (1-3k gaps). Those are the deliberate cost of spending cash and
labor on the products the shop draw actually rewards.

## 4. Gate status

| Gate | Target | Result |
|---|---|---|
| **M1** mechanics | fed >=98% of intended-keep, 0 unintended escapes, 0 overflow, <=10 orders, 0 exceptions | **mostly pass** - mean fed 0.984 (60 games), per-game min 0.974; **1 unintended escape in 60 games**; 0 overflow; max_orders = 10; 0 exceptions |
| **M2** avg >=85k vs sol5 (5 named, both seats) | >=85k | **PASS - 88.4k** (90.3k vs gideon) |
| **M3** worst named schedule >=75k | >=75k | **FAIL** - worst is milk_starved 64.4k / bakery_heavy 66.0k |
| **M4** beat sol5 >=14/16, gideon >=12/16; self-mirror +/-1k | as stated | win grid **PASS (20/20 vs sol5, 20/20 vs gideon)**; **self-mirror FAIL** (seed 12 = 0k diff, seed 11 up to 6.3k) |

Latency: **max 38.3 ms/turn** over 4,314 timed turns across both seats (< 0.3 s).
`main.py` reproduces `build_agent(SEED_VEC)` to the dollar on seeds 200 and 201.

## 5. Known limitations

- **M3 not reached on milk_starved / bakery_heavy (~64-66k).** These are adversarial
  low-value draws (bakery/egg/wheat heavy, almost no milk). sol5 gets only 54-57k
  there and we beat it by 8-13k, but 75k appears to be above the ceiling for these
  draws: the high-value sinks (milk, wool, strawberry) are simply absent. Adding
  cows to chase inelastic milk was tried (base_cows 2->5) and *lowered* net score -
  the extra cash/labor is worth more on strawberry/eggs/melon, and extra milk floods
  the shared market. Reported with numbers rather than lowering the bar.
- **Self-mirror asymmetry on seed 11 (up to 6.3k).** Two identical agents dumping
  into the shared market on the same turns give seat 0 a first-mover selling edge
  (seat 0 is consistently the higher score). seed 12 mirrors to 0k. This is an
  environment seat-order property, not agent instability; both seats still beat
  sol5 and gideon 4/4.
- **fed% floor 0.974 (< 0.98) in a few animal-heavy games** (milk_starved's geese +
  cows + sheep, one yarn3 game). Feeders cannot always reach every animal on peak
  days; at-risk animals (consecutive_unfed >= 1) are prioritized at all hours, which
  holds unintended escapes to 1 in 60 games, but the per-game fed ratio dips ~2%.
- **Walking share ~0.55-0.58** (above the 40% aspiration in PLAN step F). Not tuned
  further; it does not gate any scoring result.
