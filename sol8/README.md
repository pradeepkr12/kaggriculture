# sol8: sol7's planner without the two self-inflicted losses

sol8 is sol7's model-based daily planner (`sol7/RESEARCH.md` §4.3/§5) rebuilt on the same
sol5 mechanics layer, with five changes (A-E, below) aimed at sol7's own failure list: 7-14
escapes per loss, milk/strawberry given away late-game, and two negative-margin schedules.
The code lives in `research/planner/{farmlib_ph.py, planner.py}` and is baked into a single
`main.py` by `make_main.py` (same pattern as every prior solN).

## What changed vs sol7

**A. Graduated animal throttle instead of hard culling.** Per animal type, an EMA
(half-life 2 days) of the planner's keep-value and of realized price/base picks a feeding
rung: `full` (FEED+CARE), `feed_only` (FEED, no CARE bonus), or `alt_feed` (feed only when
needed to avoid escape or to catch a production night). The real cull/escape rung is gated
shut for cows/sheep in almost all conditions (`day>=12`, 3+ consecutive alt_feed days, no
shop for the product, no future draw, price < 40% base) because sol7's post-mortem showed
prices recover late-season and irreversible culling was the single largest loss driver.

**B. Contested-sink purchase floors.** Buy up to `FLOOR_FAC * sink / yield` (cow 0.60, sheep
0.55, goose 0.50) of each animal as soon as its sink is observed, plus a 4-cow floor to day 6
when milk is the dominant sink and the symmetric day-0 prior (2 cows + 3 sheep before melon
seeds, ramping from day 2).

**C. EMA-controlled reversible crop production.** Strawberry planted through day 19 with an
EMA target driven by sink + realized price/base (unchanged from the inherited draft: see
"what we tried and reverted" below). Wheat filler scaled by the EMA of idle unit-turns.

**D. Geese as idle-labor filler**, capped at 10, contested-sink floor via the same formula
as cows/sheep (their product is EGG), plus an idle-EMA top-up.

**E. Carrot filler is now sink-bounded (new in this pass), not an uncapped 999-tile catch-all.**
This is the one substantive code change made in this implementation pass; see REPORT.md
for the diagnosis and the matrix with/without it.

## Files

- `research/planner/farmlib_ph.py` — mechanics layer (sol5 semantics + hooks: `animal_targets`,
  cull set, feeding rung, sell override, Hungarian crop-crew assignment). One line changed:
  `crop_target["CARROT"]` now reads `P.get("carrot_tiles", 999)` instead of a hardcoded 999.
- `research/planner/planner.py` — the daily planner (EMA throttle, purchase floors, crop
  targets, sell override). Added `CARROT_FILLER_FLOOR`/`CARROT_FILLER_MAX` constants and the
  `carrot_t` computation; everything else is unchanged from the inherited draft.
- `research/harness.py`, `arena.py`, `research/diag.py` — unchanged, used for validation.
- `main.py` — baked submission; verified bit-identical to the module agent (2 schedules, seed
  1000), Kaggle-style `env.run([path, "pass"])` both seats (DONE/DONE), p99 < 5 ms, max < 300 ms.
- `results/` — every matrix run kept: `sol7.json` (sol7 baseline), `sol8.json` /
  `step1_baseline.json` (inherited draft, bit-identical reproduction), `sol8_step2.json` /
  `sol8_final.json` (this pass's result, after the carrot fix).

## Known limitations (see REPORT.md for numbers)

- `yarn_x3` and `random_b` vs sol7 are now near break-even (+0.9k and -1.4k) rather than
  clearly negative (-3.9k / -1.4k inherited), but neither clears the plan's +2k-per-schedule
  gate. Root cause for both is a close, roughly symmetric matchup (comparable animal/crop
  counts to sol7 in the diagnosed games), not a lopsided misallocation — see REPORT.md.
- Worst schedule vs sol7 (`milk_starved`, 71.6k min / 72.8k mean) is still short of the 75k
  floor gate.
- Days 22-29 earnings average ~44.3k (sampled seed 1000, all 7 schedules, both seats),
  just under the 45k gate.
- fed% (86-95% depending on schedule) is below the literal 98% reading of G1; this reflects
  the intentional `alt_feed`/`feed_only` rungs (by design, not daily FEED) plus normal labor
  contention, not unattended animals — the more meaningful escape count is 4 unplanned
  escapes across 14 seed-1000 games (7 schedules x 2 seats), concentrated in `milk_rich` and
  `random_b`.
