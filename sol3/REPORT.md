# Kaggriculture sol3 — Report

**Date:** 2026-09-10
**Agent:** `sol3/main.py` — melon + strawberry hybrid, sell-first, throttled shop-sink selling
**Status:** submitted — submission `56147680` (2026-09-10). sol1 = submission `56146676` (public score fell to 433.1, confirming the sell-ordering bug).

---

## 1. Why sol3 exists

sol1 (melon monoculture) scored **451.8** on the leaderboard — far below its local
strength (~15k in a self-mirror, ~31k vs baselines). The working hypothesis was
"melon is structurally bad." Building a local self-play validation engine let us
test that directly, and it turned out to be **wrong twice over**:

1. **The real bug was sell ordering.** The market processes orders by index across
   *both* players, finishing each index before the next. sol1 queued `HIRE` before
   `SELL`, so its melon `SELL` landed at a later index — i.e. it sold *after* a
   sell-first opponent had already pushed the melon price down. Moving `SELL` to
   the front (index 0) flips this: we sell into the fresh, high price. In a direct
   test, sell-first beat hire-first **8–0** with identical production.
2. **Melon is not weak.** Played sell-first, melon monoculture scores **32,116**
   vs baselines and beats *every* shop-sink-only crop mix **10–0** (see `exp1.py`).
   A pure shop-sink crop strategy tops out at ~13k — well above the 9k target, but
   far below melon.

So the pivot was not "drop melon" but **"fix the ordering, then find what beats a
*strong* melon opponent."**

## 2. The market mechanic that everything hinges on

Read from the engine (`kaggriculture.py`):

- Every product's market starts at inventory `I0 = 10000`, where `price == base`.
- Selling **adds** inventory → price **falls** (glut). The premium products fall
  fast; melon's curve (`sq`, tiny amplitude) is unusually shallow.
- **Town shops consume inventory every 4 turns** (6×/day/instance) and the town
  center once/day. This **removes** inventory → pushes price **above** base.
- Melon is demanded by **no shop** (only the town center, 1/day). Wheat/carrot/
  tomato/strawberry/egg/milk/wool each have real shop demand.

**Consequence:** if you sell a shop-demanded product *only up to the rate the shops
drain it*, market inventory stays near `I0` and you sell all season near the high
base price. If you *dump* it, you crash your own price. The agent observation
exposes the live shared `market.inventory`, so we can compute the exact number of
units sellable this turn while keeping price ≥ a threshold — no estimation.

## 3. The strategy (found by optimization, not hand-tuning)

The winning agent runs **two revenue streams an opponent cannot both contest**:

| Stream | Share of tiles | Why |
|---|---|---|
| **Melon** | ~20% | Highest base ($250), no shop sink. Uncontested → huge pie; contested → *splits evenly*, which neutralizes a melon rival instead of ceding the pie. Melon is dumped (throttle is a no-op on its shallow curve). |
| **Strawberry** | ~77% | Base $120, demanded by 4 shop types (brunch, icecream, smoothie, farmers-market). Sold **throttled** to `0.71×base` so its price stays high all season. An opponent who *dumps* strawberry crashes their own price while ours holds — so contesting strawberry only helps us. |

Plus: hire **5 hands** each morning (fib cost 1,1,2,3,5 = $12/day; labor is the
binding constraint) and buy **1 extra quadrant** (NE) for the ~42-tile footprint.
A greedy multi-unit assignment sends each unit to the highest-value nearby task:
survival-water > harvest > bonus-water > plant > dig.

### How it was optimized (RL framing)

The strategy is a compact **9-dim vector** (crop-mix weights, #hands, land,
tile-budget, sell-threshold). Because the market is shared, an agent's value only
means something *relative to an opponent*, so the optimization signal (the RL
"return") is the **average coin margin** vs an opponent pool, played on both seats
over several seeds. A **Cross-Entropy Method** (`optimize.py`) sampled a population
each generation, kept the top-5 elite by margin, and refit the sampling Gaussian.
It converged from a hand-seeded hybrid to the strawberry-heavy hybrid used here.

```
resolved params: melon 20% / strawberry 77% / (carrot, tomato, wheat ~1% each)
                 hands=5, land=1 (NE), tile_budget=42, sell_thresh=0.71
```

## 4. Validation (held-out seeds, both seats)

Optimization used seeds 1–4. Validation uses **disjoint** seeds (200–307) so the
numbers reflect generalization, not memorized RNG.

| Opponent | My score | Opp score | Margin | W/L/T |
|---|---|---|---|---|
| sell-first melon | 31,915 | 20,855 | **+11,060** | 16/0/0 |
| melon+strawberry hybrid | 34,335 | 22,006 | +12,329 | 15/1/0 |
| starter | 42,173 | 3,540 | +38,633 | 16/0/0 |
| pass | 41,850 | 3,000 | +38,850 | 16/0/0 |
| strawberry-flooder | 37,603 | 15,534 | **+22,069** | 16/0/0 |
| aggressive melon + 2 land | 31,210 | 13,939 | +17,271 | 16/0/0 |
| random | 38,334 | 0 | +38,334 | 16/0/0 |
| **self-mirror** | 35,416 | 35,416 | **+0** | 8/8 (fair) |

### What this shows

- ✅ Beats the strong sell-first melon meta **16–0** — the matchup sol1 could only tie.
- ✅ Beats an equally-hybrid rival and an adversarial strawberry-flooder decisively;
  the throttle is exactly what wins the flooder matchup (they crash the price, we don't).
- ✅ **Self-mirror is perfectly even** (35,416 each) — the score comes from real
  market sales, not an engine exploit.
- ✅ Worst realistic case (identical opponent) still nets **+32k**, vs sol1's +12k.
- ✅ `main.py` (self-contained) reproduces the parametrized policy's results bit-for-bit.

## 5. Known limitations / risk

- **Strawberry contest.** If a leaderboard opponent *also* throttles strawberry
  (rather than dumping it), the strawberry pie splits like melon does. The melon
  stream is the hedge for that case; the mirror result (+0, 35k each) is the floor.
- **Late strawberry ramp.** Strawberry first yields on day 10, so days 0–9 lean on
  melon setup and early wheat/carrot. An animal line (goose eggs from day 4, daily)
  is the natural next increment to fill the early game — deferred; not needed to win.
- **Opponent model.** Optimized against melon/hybrid opponents. If the true meta is
  something exotic, re-running `optimize.py` with that opponent added is cheap (~7 min).

## 6. Files

See `README.md`. Optimization: `farmlib.py` (policy) → `arena.py` (self-play margin)
→ `optimize.py` (CEM) → `validate.py`/`validate2.py` (held-out + adversarial).
Submission: `main.py`.

## 7. Suggested next step

Submit `main.py` (4 submissions/day available). If it under-performs, the two
levers are (a) add the goose-egg animal line for early-game income, and (b) re-run
CEM against a pool that includes whatever the leaderboard meta turns out to be.
