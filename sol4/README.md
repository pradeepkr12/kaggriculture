# sol4 — Animal-core, throttled multi-market farm (target 99k+)

Submission: **`main.py`** (submission `56148629`, 2026-09-10). Planned by Fable 5.1
(`PLAN.md`), implemented by Opus 4.8.

## Why sol4

sol3 (melon + strawberry, ~35k) beat every melon-style opponent but scored 449.7
on the leaderboard: the field is ~90k-class agents. The #1-vs-#2 replay
(SpaTaro 95.8k vs Otter Vibe 92.3k) showed how: **animals** (cows/sheep/geese
fed on wheat, cared daily, fertilizer collected and sold), **3 quadrants**,
**10–14 hands/day**, and **7–9 products sold at once** so no single market is
glutted. Revenue is additive across independent markets.

## Strategy (hand-seeded vector; CEM refinement in progress)

| Stream | Setup | Notes |
|---|---|---|
| Cows ×8 | pastures within 2 tiles of the shed | milk $160 base; fed+cared → 3 milk / 2 days |
| Sheep ×5 | day-0 batch of 3 for early wool + fertilizer cash | wool $200 base; crashes if no yarn shop → pressure valve |
| Geese ×4 | from day 10 | eggs never crash (log curve) — labor sink |
| Melon ×10 | day 0, dumped day 11 (~$15k) | funds the day-10 expansion |
| Strawberry ~34 | days 5–15, fertilized | throttled to ≥0.87×base |
| Wheat ~20, tomato 8, carrot filler | wheat feeds animals; surplus sold | |
| Hands 6 → 8 → 12/day; land NE ~day 5, SW ~day 8 | | |

**Labor is role-based:** each day the animals are partitioned into fixed routes,
one per feeder unit (pick up wheat → FEED/CARE/HARVEST/COLLECT at each animal →
drop → join crop crew). The crop crew uses a unit-centric "sweep" (each unit
takes the best priority-weighted *nearby* task; strict priority after hour 16).

**Selling** reads the live shared market inventory: fragile products (wool,
milk, strawberry) throttled to a price floor with a pressure valve so stock never
piles up (shed cap 100 — overflow is silently discarded); melon/egg/wheat surplus
dumped; fertilizer sold above a small reserve; taper from day 27 to a final dump
at day 29 h19–22.

## Results (held-out seeds 200–207, both seats)

| Opponent | sol4 | Opp | W/L/T |
|---|---|---|---|
| pass | **127,157** | 3,000 | 16/0/0 |
| starter | 127,568 | 3,482 | 16/0/0 |
| sol3 | 110,332 | 33,549 | 16/0/0 |
| sell-first melon | 116,552 | 17,840 | 16/0/0 |
| self-mirror | 70,029 | 70,029 | 5/5/6 |

Diagnostics on seed 1: 100% fed every day, 0 escapes, ~0 shed overflow.

## Files

| File | Purpose |
|---|---|
| `main.py` | Submission (farmlib inlined + baked vector; built by `make_main.py`) |
| `farmlib.py` | Parametrized policy: engine mirrors, market model, crews, market policy |
| `arena.py` | Parallel self-play duel/fitness (opponents: builtins, `sol3`, `melon`, vectors) |
| `diag.py` | Per-day fed%/cared%/money, escapes, overflow, revenue by product |
| `hist.py` | Per-day action/crop histogram (labor efficiency) |
| `validate.py` | Milestones on held-out seeds (`quick` / `full`) |
| `optimize.py` | CEM with `--dims` subsets and `--workers` for parallel runs |
| `make_main.py` | Bake a vector into `main.py` and verify equivalence |
| `PLAN.md` | Fable 5.1 plan (analysis of engine + replay, build order, budgets) |
| `REPORT.md` | Write-up |

## Reproduce

```bash
python diag.py 1 pass            # one game with diagnostics
python validate.py full          # held-out milestones
python optimize.py --dims n_cows,n_sheep --pop 12 --gens 6 --workers 12 --pool pass,seed
python make_main.py '[...vec...]'
```
