# Kaggriculture sol5 — Report

**Date:** 2026-09-10 · **Submission:** `56148891` (`sol5/main.py`) · **Status:** pending at time of writing
**Lineage:** sol4 code (animal-core farm, Fable-planned / Opus-implemented) + CEM-tuned strategy vector.

---

## 1. Where we were

| Solution | Strategy | Local (vs pass) | Contested mirror | Leaderboard |
|---|---|---|---|---|
| sol1 | melon monoculture, hire-first ordering | 31.6k | 15k | 469 |
| sol3 | melon + strawberry, sell-first, throttled | 35k | 35k | 450 |
| sol4 | animals + melon + multi-market, hand-seeded | 127k | 70k | `56148629` pending |
| **sol5** | **sol4 + CEM-tuned vector** | **138k** | **100k** | `56148891` pending |

sol1 and sol3 landing in the same ~450 band showed the field is ~90k-class agents
(the #1 vs #2 replay: 95.8k vs 92.3k). Beating melon-style opponents was never the
bar; competing for shared shop demand at 90k+ is.

## 2. What sol5 is

The sol4 decoder unchanged: role-based labor (animal crews on fixed daily routes;
crop crew on a unit-centric sweep), live-inventory sell throttle with a pressure
valve, cash-flow rules (feed reserved before hires, fertilizer sold from day 1),
melon day-0 → day-11 cash spike, strawberry fertilized. See `sol4/REPORT.md` for
how each of those was found.

What changed is the 19-number strategy vector, found by CEM against a pool of
`{pass, sol4}` — i.e. fitness rewards both absolute score and margin in a
contested market:

- **10 cows / 4 sheep / 1 goose** (was 8/5/4). In the sol4 mirror diagnostics, milk
  still sold at 144% of base and strawberry at 179% even with two farms supplying
  them, while wool crashed to 21% (two farms × 5 sheep into a sink that may have no
  yarn store) and eggs were the lowest $/action. The optimizer reallocated labor
  accordingly.
- **14 melon tiles** (was 10): the day-11 dump (~$20k) funds the animal expansion.
- **No SE quadrant**: $4k + longer walks not repaid within the season.
- Fewer tomato/wheat tiles, slightly lower sell thresholds, smaller fertilizer
  reserve.

## 3. Optimization procedure

Three coordinate-group CEM runs in parallel (cores split 5/4/4), pop 12, elite 4,
6 generations, seeds 1–3 both seats, pool `{pass, sol4-seed}`:

| Group | Margin (baseline +58.5k) | Key moves |
|---|---|---|
| A animals + melon | **+76.1k** | cows 10, sheep 4, geese 1, melon 14 |
| B labor / land / crops | +74.5k | no SE, straw 32, tomato 4, wheat 17, hands 6/7/12 |
| C market policy | +65.2k | thr 0.86/0.71, fert reserve 2, drop 9 |

Merged per-group winners → **sol5 vector**. A joint refinement over all 19 dims
reached +79.2k on the training seeds but scored **121k vs pass on held-out seeds
(vs 138k for the merged vector)** and only +1k head-to-head — an over-fit toward
the contested pool. Not used; recorded in `cem/cem_joint.json`.

## 4. Validation (held-out seeds 200–207, both seats)

| Opponent | sol5 | Opp | Margin | W/L/T |
|---|---|---|---|---|
| pass | **138,134** | 3,000 | +135,134 | 16/0/0 |
| sol3 | 120,959 | 33,269 | +87,690 | 16/0/0 |
| **sol4 (previous submission)** | **88,991** | 75,774 | **+13,217** | **16/0/0** |
| self-mirror | 100,426 | 100,426 | 0 | even |

Diagnostic game (seed 200 vs pass, 152.6k): revenue MILK $70.1k (234u @ 187% base),
STRAWBERRY $38.7k (148u @ 218%), FERTILIZER $21.3k, WOOL $20.7k (85% base), MELON
$20.4k (83u), wheat/tomato/egg/carrot ~$9k. Animals 100% fed on 27 of 29 feeding
days (min 93%), 0 escapes, ~6 items lost to shed overflow, 0 plant-blocked events.

Checks: `main.py` reproduces `build_agent(VEC)` bit-for-bit on seeds 200/201;
error-free standalone on both seats (152k vs starter, 92k vs random); ≤10 market
orders/turn by construction.

## 5. Limitations / risks

- **Untested vs a SpaTaro-mimic.** The pool was `{pass, sol4}`; a leaderboard
  opponent with 10 cows and aggressive fertilizer/milk dumping will compress milk
  and fertilizer prices further than the mirror shows. Adding a mimic opponent to
  the pool is the first thing to do tomorrow.
- **Shop draw variance.** Shops unlock randomly (every 3 days, max 8). Wool and
  strawberry sinks depend on which shops appear; the pressure valve limits the
  damage but the fixed sheep count is not adaptive.
- **Late-game weeds / idle tiles.** 30–40 tiles end as weeds or empty; a rolling
  wheat/carrot filler with a dedicated planter could add several k.
- **Random opponent noise.** vs `random` the score dropped to 92k on one seed
  (random SELL/BUY orders perturb the shared market) — still a win, but shows
  sensitivity to erratic market behaviour.

## 6. Plan for tomorrow's submissions

1. Add a SpaTaro-mimic (sol5 code with 10 cows / 4 sheep / 0 geese / thr 0.5 /
   SE) and the sol5 vector itself to the CEM pool; re-tune with held-out gating on
   *both* absolute score and contested margin (reject over-fits like the joint run).
2. Adaptive sheep count from `town.unlocked_shops` (YARN present → keep sheep).
3. Planter role for end-of-day filler crops; day-29 harvest/dump audit.
4. Read the ranked episodes of `56148629` / `56148891` (kaggle episodes API) to see
   the real opponents' revenue mixes and tune against them.
