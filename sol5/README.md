# sol5 — CEM-tuned animal-core farm (submission `56148891`)

sol5 is **sol4's code with the strategy vector re-tuned by CEM self-play**. Same
decoder (`farmlib.py` is identical to sol4's except the default vector); the 19
strategy numbers were optimized in three parallel coordinate-group runs and
merged. Submitted 2026-09-10 as `main.py`.

## The vector (what changed vs sol4)

| Knob | sol4 (hand seed) | **sol5 (CEM)** | Why it moved |
|---|---|---|---|
| cows / sheep / geese | 8 / 5 / 4 | **10 / 4 / 1** | milk stays scarce even under contest; wool floods its tiny sink; geese have the lowest $/action |
| melon tiles (day 0) | 10 | **14** | bigger day-11 cash spike funds the expansion |
| strawberry / tomato / wheat tiles | 34 / 8 / 20 | **32 / 4 / 17** | labor rebalanced toward cows |
| hands early / mid / late | 6 / 8 / 12 | 6 / **7** / 12 | |
| buy SE quadrant | yes | **no** | $4k and extra walking not repaid |
| thr_fragile / thr_elastic | 0.87 / 0.75 | **0.862 / 0.709** | |
| fertilizer reserve / drop threshold | 6 / 8 | **2 / 9** | |

`VEC = [14, 10, 4, 1, 32, 4, 17, 6, 7, 12, 0.43, 0.862, 0.709, 2, 27, 3, 9, 6, 15]`

## Results (held-out seeds 200–207, both seats, 16 games each)

| Opponent | sol5 | Opp | W/L/T |
|---|---|---|---|
| pass | **138,134** | 3,000 | 16/0/0 |
| sol3 (our 35k hybrid) | 120,959 | 33,269 | 16/0/0 |
| **sol4 (submitted 56148629)** | **88,991** | 75,774 | **16/0/0** |
| self-mirror (contested) | 100,426 | 100,426 | even |

sol4's mirror was 70k; sol5's is 100k — the contested game (what the leaderboard
is) improved most. Diagnostic game (seed 200 vs pass): 152.6k; milk $70k,
strawberry $39k, fertilizer $21k, wool $21k, melon $20k; 100% fed, 0 escapes.

## How it was tuned

`optimize.py` runs CEM on a subset of dimensions (`--dims`) with a capped worker
count, so three runs shared the 14 cores (5/4/4) concurrently. Fitness = mean coin
margin vs pool `{pass, sol4-seed}` on seeds 1–3, both seats (pop 12, elite 4, 6
generations). Results in `cem/`:

| Run | Dims | Margin (baseline +58.5k) |
|---|---|---|
| A `cem_A_animals.json` | cows, sheep, geese, animal_day2, melon_tiles | **+76.1k** |
| B `cem_B_labor.json` | hands ×3, buy_SE, wheat/straw/tomato tiles, straw_deadline | +74.5k |
| C `cem_C_market.json` | thr_fragile, thr_elastic, fert_reserve, taper, wheat buffer, drop | +65.2k |
| joint `cem_joint.json` | all 19 around the merged vector (std 8% of range) | +79.2k on training seeds, but **121k vs pass on held-out (worse than merged's 138k)** → not used |

The joint run over-fit toward the contested pool (sheep→3), trading absolute score
for a +1k head-to-head edge; the merged vector was kept.

## Files

Same tooling as sol4 (`farmlib.py`, `arena.py`, `diag.py`, `hist.py`,
`validate.py`, `optimize.py`, `compare.py`, `make_main.py`, `PLAN.md`) plus
`cem/` (optimizer outputs and logs) and `main.py` (submission; verified bit-for-bit
against `build_agent(VEC)` on seeds 200/201 and error-free standalone on both seats).

```bash
python compare.py '<cand vec>' '<ref vec>'   # head-to-head on held-out seeds
python make_main.py                          # bake SEED_VEC (= sol5 vector) into main.py
```
