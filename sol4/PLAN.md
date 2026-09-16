# sol4 Plan: Animal-Core + Throttled Multi-Market Farm (target ≥ 99k)

*Planned by Fable 5.1 (Plan agent) on 2026-09-10 from the engine source, sol3, and the #1-vs-#2 replay (`/private/tmp/107518137.json`, SpaTaro 95,811 vs Otter Vibe 92,263). Implemented by Opus 4.8.*

## 0. Engine rules relied on (`kaggriculture.py`)

| Rule | Lines |
|---|---|
| CROPS / ANIMALS / MARKET_PARAMS / SHOPS | 11-51, 103-112 |
| `market_price` (glut/scarcity shapes, floor 1) | 192-206 |
| Shed-access tiles (4,4),(5,4),(4,5),(5,5); farmer spawns (4,4); hands spawn on least-occupied access tile (may be LOCKED; movement onto LOCKED allowed) | 132-139, 161-166, 533-541, 323-332 |
| DROP dumps whole inventory (overflow past 100 discarded); PICKUP n; PLACE animal on empty matching structure while carrying it | 343-410 |
| PLANT needs empty tile + seed; WATER bonus window `(myd+1)//2..myd` (+2 if fertilized); HARVEST; FERTILIZE covers day..day+2; BUILD_* free on empty tile; FEED consumes 1 WHEAT from the unit's inventory; COLLECT_FERTILIZER; CARE | 417-530 |
| Market ≤10 orders/turn; HIRE/BUY_LAND atomic per index; SELL/BUY lockstep by index across both players; BUY_PRODUCT only WHEAT/FERTILIZER; BUY_ANIMAL/BUY_PRODUCT fail if shed full | 544-687 |
| Shops consume at `step%4==0` (single-product ×2); town centre 1 of each non-fertilizer product at `step%24==0` | 728-749 |
| Plants: 2 consecutive unwatered end-of-days → WEED (planting day counts) → **water on planting day**; ongoing +1 (+2 watered & fertilized) | 769-802 |
| Animals: unfed 2 days → escapes; production `1 + pending_care_bonus` (bonus only if fed that day); pending accumulates every fed+cared day; `fertilizer_available=True` every day | 805-833 |
| End of day: auto-drop inventories to shed (cap 100), hands removed, farmer → (4,4); shop unlock when `next_day%3==0`, cap 8 | 843-891 |
| Atomic PLANT rule; DONE at step ≥ 718 → **last acted observation is day 29 hour 22** | 921-933, 960 |

Consequences: **CARE ~doubles/triples animal output** (cow 3 milk/2 days, sheep 4 wool/3 days, goose 2 eggs/day; first production = `min(max_held, 1+days_cared)`). Fertilizer 1/animal/day for one action. EGG/WHEAT glut curves are logarithmic (unlimited labor sinks); WOOL/MILK/STRAWBERRY crash to ~$1 at excess 75-100 → must throttle to sink rate.

## 1. What the replay shows

Shops drawn: ICE_CREAM×2, PET_CAFE×2, BAKERY, SMOOTHIE, YARN, FARMERS_MARKET.

**SpaTaro (95,811)**: 7 hands day 0, 5-8 days 1-7, 10-11 days 8-28 (~$1,240 hire cost total). 2 cows + 2 sheep day 0 → 10 cows + 4 sheep by day 12 (+2 sheep day 21), zero geese; all pastures within distance ≤2 of the shed. NE day 6, SW day 8, never SE. 9-12 melon tiles days 0-4, 19-22 strawberry, 20-30 wheat + 20-25 carrot rotating. Money ~$0-60 through day 9, $1k day 10 → $11k day 11 (43 melons sold @ $250-272), then +$4-8k/day. Realized revenue ≈ $128k gross: WHEAT 696u $25.4k, MILK 225u $23.9k (avg $106 — oversold), STRAWBERRY 152u $22.8k, CARROT 388u $17.8k, MELON 72u $16.0k, FERTILIZER 226u $12.1k, WOOL 69u $10.3k (avg $149). Spend ≈ $33k incl **$16.2k BUY_PRODUCT WHEAT**. Labor day 15: 38% moves, animals only **75% fed** (50% on some days). Sold milk to 0.16×base, wool to 0.09×base; ~30% of order slots wasted on invalid orders.

**Otter Vibe (92,263)**: 8 cows, 8 geese, 3-4 sheep; 12-14 hands late; 100% fed from day 7 but CARE 40-70%; lost ~30 items to shed overflow on 3 days; wool sold to $1.

**Edges left on the table**: 100% fed+cared; hold milk/wool/strawberry ≥0.85×base and taper; geese (eggs never crash); tomato unused (sink 228u ≈ $13.7k); no SE despite idle labor; wasted order slots; end-game dump to $1.

## 2. Analytical strategy layer

**Sink per shop instance per day**: WHEAT 3.75, CARROT 2.25, TOMATO 1.5, STRAWBERRY 3.0, EGG 1.5, MILK 2.25, WOOL 1.5, MELON 0, FERTILIZER 0. Instances on day d = `min(8, d//3)`; 132 shop-days/season + 30 town-centre per product. Expected season sink (units): WHEAT 525, CARROT 327, TOMATO 228, STRAWBERRY 426, EGG 228, MILK 327, WOOL 228, MELON 30.

**Glut prices at excess x**: WOOL 194@10 177@20 148@30 55@50 1@75 · MILK 139@10 118@20 97@30 55@50 · STRAWBERRY 101@10 82@20 62@30 24@50 · MELON 246@20 225@50 194@75 150@100 25@150 · FERTILIZER 90@50 80@100 60@200 · TOMATO 46@30 · CARROT 27@50 · EGG 43@50 38@1000 · WHEAT 22@30 19@1000. Dump revenue: MELON 60→$14.3k, 120→$24.3k; FERTILIZER 300→$16k; EGG 1000→$20.5k.

**$/action**: MELON ~$105, SHEEP/day ~$68, COW/day ~$62, STRAWBERRY(fert) ~$48, GOOSE/day ~$31, TOMATO ~$25, CARROT ~$15, WHEAT ~$14 (+feed). Hands worth hiring to 13-14 while ≥$20/action work exists.

**Steady-state mix (seed)**: 8 cows, 5 sheep, 4 geese (all within d≤2 of the shed); 34 strawberry (fertilized, 8u each), 8 tomato ×2 rounds, 10 melon day 0, 20 wheat rolling, carrot fills. ~220 actions/day → 12 hands.

**Build order**: Day 0: HIRE×6, 3 SHEEP + 1 COW, 10 melon seeds, wheat/carrot seeds, 4 wheat feed (~$40 left); build 4 pastures around the shed, place/feed/care same day; plant 21 crop tiles. Days 1-5: fertilizer (~$380/day) + carrot/wheat; NE at $1.2k (~day 5). Days 6-7: 18 wool; +2 cows +1 sheep; 15 strawberry seeds. Day 8: SW at $2.6k. Day 10-11: harvest+dump 60 melons (~$14k) → 12 hands, +5 cows +4 geese, 19 strawberry, 8 tomato, SE if `buy_SE`. Days 12-26 steady. Days 27-29 taper; day 29: hire 8, no FEED/CARE, all DROP by h21, dump h19-22.

**Revenue budget vs pass**: MILK $28.9k, WOOL $29.0k, STRAWBERRY $32.5k, MELON $14.3k, FERTILIZER $15.5k, TOMATO $7.7k, EGG $6.2k, WHEAT $5.2k, CARROT $6.6k → gross ~$146k; spend ~$29.5k → **net ≈ $119k** (99k = 83% realization). Vs a SpaTaro-class opponent, fragile sinks halve → ~$90-95k; our edges tip it.

## 3. Decoder (`sol4/farmlib.py`)

Layout: constants + `market_price`/`sellable_qty`; PARAM_SPEC; geometry (`SHED_TILES`, `dist_to_shed`, `animal_slots`); day plan; task generation; assignment; market policy; `build_agent` (exposes `agent.stats`).

Spatial: animal zone = unlocked tiles with d≤2 (6 per quadrant), pastures first, coops last; crops d∈[3,4] strawberry/tomato, d≥5 wheat/carrot/melon.

Tasks (prio high→low): P9 FEED (need WHEAT) / PICKUP WHEAT at shed (qty ≤8, `ceil(n_animals/6)` feeders); P8 survival WATER; P8 animal HARVEST (near cap / day 29); P7 BUILD / PICKUP animal / PLACE; P7 crop HARVEST; P6 CARE, COLLECT_FERTILIZER, mid-yield HARVEST; P5 FERTILIZE (strawberry age 9 & 13, tomato 7 & 10) and bonus WATER; P4 PLANT (band deficits, atomic seed cap, deadlines straw≤13, tomato≤18, wheat≤25, carrot≤26); P4 DROP; P3 PICKUP FERTILIZER; P2 DIG; P1 idle → toward shed.

Assignment: sort by prio; nearest eligible free unit with stickiness bonus (−2); de-dup per (tile, op); `need` item must be in the unit's inventory (`private.inventories[ui]`).

Feeding guarantee: hour-0 wheat need vs have → `BUY_PRODUCT WHEAT`; hour ≥16 escalate unfed to P10; never let `consecutive_unfed` reach 2.

## 4. Market policy (≤10 orders, SELL first)

Fragile (WOOL, MILK, STRAWBERRY): `sellable_qty(thr_fragile=0.87)` cap 6/turn. Elastic (TOMATO, CARROT): thr_elastic 0.75. Log (WHEAT above feed reserve, EGG): sell all. FERTILIZER: sell above `fert_reserve` at ≥0.15×base (first-mover). MELON: sell all on harvest days. End-game taper from `taper_start_day`: per-turn quota `max(k, ceil(R/N))`, threshold decays to 0.25 over the last 48 turns, final 4 turns dump. Overflow guard at projected shed >90. Hires: hands_early/mid/late/final=8, cash-gated. Land: NE ≥$1200 (day≥4), SW ≥$2600 (day≥8), SE if `buy_SE` ≥$5500 day≤16. Animals in 3 batches; deadlines cows ≤19, sheep ≤21, geese ≤24.

## 5. CEM vector (19 dims: lo, hi, seed)

```
melon_tiles 6 16 10 · n_cows 3 10 8 · n_sheep 2 8 5 · n_geese 0 8 4 · straw_tiles 15 45 34
tomato_tiles 0 16 8 · wheat_tiles 8 30 20 · hands_early 3 8 6 · hands_mid 5 12 8 · hands_late 8 15 12
buy_SE 0 1 0.7 · thr_fragile .60 .97 .87 · thr_elastic .40 .95 .75 · fert_reserve 0 12 6
taper_start_day 25 29 27 · wheat_buy_buffer 0 10 3 · drop_threshold 4 20 8 · animal_day2 4 12 6 · straw_deadline 11 15 13
```

## 6. Validation & parallel plan

Opponents: pass, starter, sol3 hybrid, sell-first melon, self-mirror, replay-mimic (sol4 with SpaTaro-like params). Optimization seeds 1-8; held-out 200-215.
Milestones: **M1** fed%=100% days 0-28, cared ≥98%, 0 escapes, 0 overflow loss, 0 PLANT-blocked, ≤10 orders. **M2** ≥60k vs pass. **M3** ≥99k vs pass (held-out). **M4** 16-0 vs sol3 & melon; ≥+20k vs mimic; mirror ±1k.
Parallel subagents (coordinate-partitioned CEM): A animals+melon (5 workers), B labor/land/crops (4), C market thresholds vs {sol3, mimic} (4) → merge → joint CEM → held-out → bake `main.py`.

## 7. Risks

Starvation (P9 + purchase + escalation), shed overflow (guard), labor thrash (stickiness, idle% <5%), atomic PLANT (seed cap), order cap (fixed composition), contested fragile markets (live-inventory throttle; egg/wheat/carrot/tomato filler), end-game dump (taper; last sell day 29 h22), early cash starvation (fertilizer from day 1).
