# sol8 Plan: sol7 planner without the self-inflicted losses

*Planned by Fable 5.1 on 2026-09-16 from sol7's 14 live episodes (8-6, rating 750, rank 4834; top-50 cutoff 2887), the exact money-delta loss dissection, and the first two sol8 iterations already on disk (`sol8/research/planner/planner.py`, `results/sol8_run.log`). Implementation: Sonnet. The code base is sol7's (`farmlib_ph.py` = sol5 mechanics + Hungarian; `planner.py` = daily planner) with the sol8 changes A-E already drafted by the previous implementer; this plan says what is left, how to judge it, and where to stop.*

## 0. Where the code stands (do not redo)

`results/sol8_run.log` (7 schedules × both seats × seeds 1000/2000):

| vs | sol8 now | wins | worst | negative schedules |
|---|---|---|---|---|
| sol7 | **+10.7k** | 21/28 | 71.4k | yarn_x3 −3.9k, random_b −1.4k |
| sol6 | +18.2k | 28/28 | 66.8k | none |
| sol5 | +26.9k | 28/28 | 72.3k | none |
| gideon | +29.2k | 28/28 | 64.2k | none |
| pass | 145.0k | 28/28 | 108.5k | — |
| mirror | 87.4k | — | 67.6k | — |

Already in `planner.py`: EMA (half-life 2 d) of keep value and price ratio; feeding rungs full / feed_only / alt_feed with the cull rung gated shut for cows and sheep; purchase floors `FLOOR_FAC × sink ÷ yield` (cow 0.60, sheep 0.55, goose 0.50) plus a 4-cow floor to day 6 when milk is the dominant sink; slot clamping by value-per-slot; geese as idle filler (≤4 from idle, cap 10); strawberry planting to day 19 with an EMA target; day-0 opening 2 cows + 3 sheep, melon seeds first. `late_milk` (the 58k game's draw) went from 60k to 102k against sol7. `main.py` was rebuilt at 17:00; treat it as unverified until step 1 below.

## 1. What is left, in order

**Step 1 — Verify the baseline you inherit (30 min).** Rebuild `main.py` with `make_main.py`; confirm bit-identical scores to the module agent on seed 1000 for two schedules; Kaggle-style `env.run([path, "pass"])` on both seats, statuses DONE; p99 latency < 5 ms, max < 300 ms. Re-run the full matrix once so every later number has a same-code baseline (`results/step1_baseline.json`).

**Step 2 — Fix the two negative schedules against sol7.**
- *yarn_x3 (−3.9k).* sol7 holds 5 cows / 13 sheep here and wins on wool; the stopped implementer's last change flipped sol8 to 2 cows / 16 sheep, which floods the 36 wool/day sink when the opponent also runs sheep and forfeits milk. Rule: the sheep floor is `0.55 × wool_sink ÷ 1.33` but capped at `slot_cap − cow_floor` with cow_floor never below 3 when ≥1 milk shop exists or when the day-0 symmetric prior is active; above the floors, slots go by realized value per slot (`ema_pr × base × yield`), recomputed daily, and no animal type may exceed 60% of slots before day 12. Check with the diag script that sol8 lands near 4-5 cows / 12-13 sheep in yarn_x3 and that wool realized price stays ≥ $200.
- *random_b (−1.4k).* Diagnose from `research/diag.py` (animals per day, per-product revenue, days 22-29 earnings) before touching code; the likely causes are the same slot allocation or the strawberry EMA under-planting. Fix the cause, not the schedule.
- Gate: margin vs sol7 ≥ +2k on every schedule; total ≥ 22/28.

**Step 3 — Lift the floor to ≥ 75k against sol7 (currently 71.4k).** The worst schedules are milk_starved (72.8k) and yarnless (84.7k is fine). In milk_starved the field averages ~95k with 30+ wheat tiles and geese. Implement the wheat filler properly: idle unit-turns (EMA) → wheat tiles planted in the outer ring, fertilized at plant-age 2, harvested at age 4, replanted through day 25; geese to 8 when egg sink ≥ 12/day and idle > 12. Gate: milk_starved ≥ 75k vs sol7, idle (PASS) share < 8%, no loss elsewhere.

**Step 4 — Endgame.** Days 22-29 earnings ≥ 45k mean across schedules (sol7 losses: 18-38k). Keep every strawberry tile watered and harvested to day 29, feed animals through day 28 at the current rung, liquidate on day 29 with the existing taper; verify zero inventory at the end and zero unintended escapes.

**Step 5 — Bake, document, hand back.** `make_main.py` → `main.py`; verification as in step 1; `README.md` (what changed vs sol7 and why), `REPORT.md` (sol7 vs sol8 table for every schedule × opponent, gates, per-schedule animal counts on days 12/16/20/24/28, known limitations). No commit, no submission.

## 2. Gates (report every number; never lower a bar — report a miss)

- G1 mechanics: 0 unintended escapes (an escape counts as intended only if the planner logged that animal for cull), fed% ≥ 98% for kept animals, ≤ 10 orders/turn, 0 exceptions, p99 < 5 ms, max < 300 ms.
- G2 head-to-head: vs sol7 ≥ 22/28 with margin ≥ +2k on every schedule; vs sol6 ≥ 24/28; vs sol5 and gideon ≥ 26/28.
- G3 floor: worst schedule ≥ 75k vs sol7; days 22-29 earnings ≥ 45k mean.
- G4 stability: mirror asymmetry ≤ 3k; vs pass ≥ 150k mean.

## 3. Rules of engagement for the implementer

- Work only in `sol8/`. Never modify sol1-sol7. Read `sol7/RESEARCH.md` §4.3 and §5 and `sol8/research/planner/planner.py` fully before editing.
- Every change is judged on the full matrix (`sol8/arena.py`, 14 workers, ~40 s per opponent). Keep the previous JSON so regressions are visible. Keep individual tool calls under ~8 minutes; run arenas in the background and poll.
- No CEM, no tuned vectors. Constants stay engine-derived; if you must add a constant, name it, justify it in REPORT.md, and show the matrix with and without it.
- If a gate cannot be met, stop tuning and report the per-schedule tables so the plan can be revised.

## 4. Evidence this plan rests on

- sol7 losses summed: opponent +$90k on milk, +$74k on strawberry; we had 7-14 escapes per loss, opponents 0-2; all 3 wins had 0 escapes.
- Late prices recover: milk $66 → $152-190 and wool $66 → $196-227 over days 14-28 once 3 shops drain the market; days 24-29 gains were +10k for us, +39k for the opponent in the 58k game.
- Wool realized $238/unit with a yarn store; strong opponents hold 8-11 cows and 2-6 sheep to the end, 38-53 strawberry tiles to day 26, buy land on days 4-7, and never let melon flood (256 → $22 when both dumped).
