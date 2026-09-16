# Kaggriculture sol4 — Report

**Date:** 2026-09-10 · **Submission:** `56148629` (`sol4/main.py`, hand-seeded vector)
**Planned by** Fable 5.1 (`PLAN.md`) from the engine source and the #1-vs-#2 replay; **implemented by** Opus 4.8.
**Successor:** sol5 = same code, CEM-tuned vector (`56148891`).

---

## 1. Why a new architecture

sol3 (melon + throttled strawberry, ~35k) beat every melon-style opponent locally
yet scored 449.7 on the leaderboard, next to sol1's 469. The replay of the top two
(SpaTaro 95,811 vs Otter Vibe 92,263) explained it: the field earns ~3× our score
by running **animals** (9–10 cows, 3–4 sheep, up to 8 geese: fed with wheat, cared
daily, fertilizer collected and sold), **3 quadrants**, **10–14 hands/day**, and
selling **7–9 products at once** so no single market gluts. Revenue is additive
across independent markets; a two-product agent is capped near 35k.

## 2. Design (from `PLAN.md`)

**Economy:** day 0 = 3 sheep + 1 cow + 10 melon + hires; fertilizer from day 1
(~$400/day) funds feed; wool from day 6; NE at $1.2k, SW at $2.6k; melon harvest
dumped day 11 (~$15k) funds 8 cows / 5 sheep / 4 geese, 34 strawberry, tomato,
rolling wheat; 12 hands/day from day 10.

**Labor (the part that mattered most):**
- *Animal crews.* Each day animals are partitioned into fixed routes (≈4 per
  feeder). A feeder picks up wheat at the shed, then at each animal does FEED →
  CARE → HARVEST → COLLECT_FERTILIZER before moving on, drops at the shed, then
  joins the crop crew.
- *Crop crew.* Unit-centric sweep: each unit takes the best `priority×K − distance`
  task near it (K=1 before hour 16, 3 after, so survival watering/harvest never
  slips), with commitment to its current target.

**Market:** SELL first (index 0). Fragile products (wool/milk/strawberry) throttled
to ≥0.87×base from the live market inventory, cap 6/turn, plus a **pressure valve**
(stock above 10 is sold down over 4 turns regardless); melon/egg/wheat-surplus
dumped; fertilizer sold above a small reserve; taper from day 27; final dump day 29
h19–22. Feed cash is reserved before hires; the first 1–3 hands ($1–3) always hired.

## 3. What the diagnostics found (17k → 127k in one session)

| Step | Symptom (diag/hist) | Cause | Fix | vs pass |
|---|---|---|---|---|
| 0 | fed 0% day 1–2, animals escaped, crops died | day-1 cash $23: fertilizer never dropped/sold; hires ate feed money | drop fertilizer promptly; reserve feed cash before hires | 17.8k |
| 1 | still $30 on day 1 | `fert_reserve=6` blocked selling 4 fertilizer; feed reserve blocked even $1 hires | reserve fertilizer only when crops can use it; cheap hires always | **84.7k** |
| 2 | milk 71u sold of ~240 made; shed hit 73; ~280 items lost | wool with no yarn shop piled up under the throttle → nightly shed overflow silently discarded everything | pressure valve; overflow guard at 80 | 86.8k |
| 3 | 210 moves vs 80 actions/day; feeding finished at hour 18; PLANT ≈ 0 | per-turn global greedy scattered animal chores across units | animal crews with fixed routes | **109.1k** |
| 4 | crop crew 145 moves / 40 actions; units sent 5–8 tiles away | task-centric "nearest unit per task" | unit-centric sweep | **124.4k** |

## 4. Validation (held-out seeds 200–207, both seats)

| Opponent | sol4 | Opp | W/L/T |
|---|---|---|---|
| pass | **127,157** | 3,000 | 16/0/0 |
| starter | 127,568 | 3,482 | 16/0/0 |
| sol3 | 110,332 | 33,549 | 16/0/0 |
| sell-first melon | 116,552 | 17,840 | 16/0/0 |
| self-mirror | 70,029 | 70,029 | 5/5/6 |

Seed-1 diagnostic: 100% fed on 26/29 feeding days (min 88%), 0 escapes, ~4 items
overflow, melon 60u @ $251, milk 193u @ 191% base, strawberry 88u @ 222% base —
the last two flagged milk and strawberry as under-supplied, which drove sol5's CEM.
Contested mirror diagnostic: wool 21% of base, fertilizer 46%, milk 144%,
strawberry 179% → fewer sheep/geese, more cows (sol5).

`main.py` verified bit-for-bit vs `build_agent(VEC)` (seeds 200/201) and
error-free standalone (138.5k vs starter).

## 5. Files

`main.py` (submission), `farmlib.py` (policy), `arena.py`, `diag.py`, `hist.py`,
`validate.py`, `optimize.py`, `make_main.py`, `compare.py`, `PLAN.md`, `README.md`,
`cem_*.json/.log` (the three CEM runs + joint refinement that produced sol5).
