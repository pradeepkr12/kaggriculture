# sol6 Plan: Demand-Sized, Contest-Aware Farm

*Planned by Fable 5.1 on 2026-09-16 from (a) the rank-1 replay `109564916` (Majkel1337 95,542 vs M & M & P & Q 91,465), (b) nine live sol5 episodes downloaded from `kaggleusercontent.com/episodes/<id>.json`, (c) a forced-shop-schedule experiment on sol5, and (d) the engine source. Implementation target: Opus, in `sol6/`.*

## 0. Where we are

| Fact | Number |
|---|---|
| sol5 leaderboard rating / rank (2026-09-16) | 704.6 / **5029** of 9200 (leader 3192.6) |
| sol5 live scores (9 episodes) | 26k, 41k, 51k, 67k, 69k, 77k, 90k, 113k, 113k — 4 wins |
| sol5 local numbers that misled us | 138k vs pass, 100k mirror |
| Top-player scores in the same games | 77k-116k; leaders average ~95k |

sol5 is not broken mechanically (100% fed, 0 escapes, empty shed every night). It loses because its **production is open-loop**: every game it makes ~234 milk, ~127 wool, ~155 strawberry, and the value of those units is decided by two things it ignores: **which shops the town drew** and **what the opponent floods**.

## 1. The two facts that decide a game

### 1a. Shop draws set the price of every fragile product

Shops unlock at the end of days 2,5,...,23 (8 draws with replacement from 8 shops). Each instance drains its products 1 unit per 4 turns (6/day; 12/day for single-product shops YARN_STORE and PET_CAFE). The draw is **not reproducible from the seed** (the shop RNG is shared with weed spawns, so it depends on both farms' empty-tile counts) but it **is observable** every turn in `obs.town.unlocked_shops`.

Realized average sell price in the nine live games, by number of relevant shop instances:

| Product | 0 shops | 1 shop | 2 shops | 3 shops | 4-5 shops |
|---|---|---|---|---|---|
| WOOL (base 200) | $32-61 | $160-223 | $186-243 | $240-246 | — |
| MILK (base 160) | — | $8-42 | $15-72 | $46-156 | $238-256 |
| STRAWBERRY (base 120) | — | — | $117-219 | $39-131 | $120-221 |

Forced-schedule test (sol5 vs pass, same seed): milk-starved draw **92k**, milk-rich draw **148k**. Milk revenue $10k vs $75k. Same cows, same labor, same feed.

Draw probabilities: P(no yarn store by day 15) = **51%**, P(no milk shop by day 12) = **15%**, P(no milk shop by day 15) = 9.5%. Expected instances by day 24: wheat 5, strawberry 4, milk 3, carrot 2, tomato 2, egg 2, wool 1.

### 1b. Glut shape decides what can be scaled

| Product | Glut curve above I0 | Units to $1 (no sink) | Verdict |
|---|---|---|---|
| EGG | log, target 0.2 | never (still $38 at +1000) | **unlimited** |
| WHEAT | log, target 0.2 | never (still $19 at +1000) | **unlimited**; sits at $35-39 with bakeries (scarcity side) |
| FERTILIZER | linear 0.4 | 500 | finite shared pie ~$25k, no sink, race |
| MELON | sq 3.6 | 158 | finite pie ~$26k, no sink, race |
| CARROT | sqrt 0.7 | 450 | elastic; fine with PET_CAFE/FARMERS |
| TOMATO | sqrt 0.6 | 200 | elastic, small |
| STRAWBERRY | linear 1.6 | 62 | fragile; needs sinks |
| MILK | linear 1.6 | 76 | fragile; needs sinks |
| WOOL | sq 3.2 | 59 | fragile; needs YARN_STORE |

In the rank-1 game the combined field sold 543 eggs at $51-57 and 994 wheat at $21-39. Those two markets are the labor sink that never punishes you.

## 2. What the winners actually do (replay 109564916)

**Majkel1337 (95.5k):** revenue STRAWBERRY $26.8k (183u @161), WOOL $21.5k (140u @179), WHEAT $19.4k (571u @35), MELON $17.1k (72u @247, sold days 10-13 only), FERTILIZER $11.4k (215u), EGG $8.7k, MILK $3.8k (139u, most at $1-7), CARROT $3.3k, TOMATO $2.9k. Hires 4→11 by day 10, 11/day after. Land NE day 6, SW day 9, never SE. Fertilizes wheat at age 2 (6 units/tile) and strawberry every production cycle. Bought 3 sheep the day YARN_STORE unlocked (day 15). Stopped feeding 2 cows once milk crashed (they escaped day 20). Stopped all feeding day 28. Zero inventory at the end. Weaknesses: 46% of unit-turns are walking; 7 cows in a milk-starved draw returned $3.8k.

**M & M & P & Q (91.5k):** 13 geese → 381 eggs @ $54 ($20.2k) with only 70% fed/cared (1.26 eggs/goose-day; perfect care gives 2). Fed cows **every other day** (escape needs 2 consecutive unfed days) and let all 5 escape days 13-18 once milk was $1. 304 idle PASS turns, mostly hours 0-2 and 21-23.

**Gideon Oba (111.7k vs our 69k):** 6 cows, **10 sheep**, 33 strawberry; 211 wool @ $246 in a 3-yarn-store draw; 244 strawberries harvested vs our 151 from the same tile count.

**Aru Ohta / RiyaSoni20 (99k, 77k vs our 41k, 26k):** 8 cows / 6 sheep / 3 geese, 33 strawberry, floods everything (sells 258 milk, 188-270 strawberry) and crashes the fragile markets we depend on.

## 3. The new approach

**Principle: size each fragile product to the observed sink, shared with the opponent; put all remaining labor into products that cannot crash; race the finite pies.**

### 3a. Demand-sized livestock (re-evaluated every day at hour 0)

Yields with daily FEED+CARE: cow 1.5 milk/day, sheep 1.33 wool/day, goose 2 eggs/day; every animal 1 fertilizer/day.

```
milk_sink  = 6 * (#PIZZA + #ICE_CREAM + #SMOOTHIE)      units/day
wool_sink  = 12 * #YARN_STORE
share      = 0.5                                        # assume the opponent takes half
cows_target  = clamp(2 + round(share*milk_sink/1.5), 2, 10)   # 2 base cows for fertilizer + the ~76u pie
sheep_target = clamp(3 + round(share*wool_sink/1.33), 3, 12)  # 3 base sheep for the ~59u pie
geese_target = labor_filler (see 3c), typically 4-10
```

Purchase gates: cows only while `day <= 19` (8 days to first milk), sheep while `day <= 22`, geese while `day <= 25`. Buy when a new shop appears (Majkel bought sheep on the YARN_STORE day). Pastures/coops in the 6x6 core around the shed, including the shed-access tiles (shed ops work while standing on a structure).

**Culling:** if `price(product) < 2 * price(WHEAT)` and the sink cannot recover it within the days left, stop FEED/CARE on the surplus animals (keep the base count for fertilizer). Two unfed days → escape → labor freed. Alternate-day feeding (FEED+CARE only on production days) for animals whose product is below 0.5×base but above cull level: halves wheat and labor, loses only the care bonus.

### 3b. Crops

| Crop | Plan | Why |
|---|---|---|
| MELON | 12-14 tiles day 0-1, harvest day 10-11, sell all immediately | first-mover on a 158-unit shared pie; Majkel got $247 avg by finishing by day 13 |
| STRAWBERRY | 20-24 tiles days 2-6; FERTILIZE on each production day (ages 10,12,14 → 8 units/plant); sell as produced | best $/action when sinks exist; sell into the scarcity premium before the opponent floods |
| WHEAT | rolling 25-35 tiles from day 0; FERTILIZE at age 2; harvest age 4 | feed + $35/unit uncrashable cash; 6 units/tile/5 days ≈ $210 per 6 actions |
| CARROT | days 22-27 only | 2-3 day crop for the tail when nothing else can mature |
| TOMATO | 4-8 tiles only if FARMERS_MARKET or PIZZA_SHOP present | small elastic market |

Strawberry tile count scales with `straw_sink` (6/day per BRUNCH/ICE_CREAM/SMOOTHIE/FARMERS): a fertilized tile yields ~1 unit/day over its window, so tiles ≈ `10 + share*straw_sink` capped at 30.

### 3c. Labor

- Hire to 11 hands by day 8 (fib cost for 11 hires = $232/day, trivial). Hire at hour 0 with SELL orders ahead of HIRE in the same list.
- Geese are the labor filler: each goose is 4 actions/day (FEED, CARE, HARVEST, COLLECT) + 1 wheat for 2 eggs (~$108) + 1 fertilizer. Add geese while projected idle unit-turns > 12/day, up to 10.
- Wheat is the other filler: any idle unit plants/waters/harvests wheat.
- Target walking share < 35% (Majkel 46%): animals in the core, strawberry in the ring at distance 3-4, wheat/carrot outside.
- Day 28: stop FEED/CARE; day 29: no planting; everything DROPped by hour 21.

### 3d. Selling (per turn, SELL orders first in the market list)

1. **Uncrashable (EGG, WHEAT above feed reserve):** sell everything every turn.
2. **Finite pies (MELON, FERTILIZER):** sell everything every turn from the first unit. Keep fertilizer only for scheduled FERTILIZE actions (strawberry cycles, wheat age 2); 1 fertilizer on strawberry is worth ~$300, on wheat ~$70, on the market $15-100 and falling.
3. **Sink products (STRAWBERRY, MILK, WOOL, TOMATO, CARROT):** sell while `market inventory < I0` (scarcity premium; holding only lets the opponent take it). Above I0, sell up to the units the sink will drain before the next decision plus a **reservation price that decays with days left**:
   `reserve(item, day) = base * max(0.25, 0.9 - 0.65 * (day - 10) / 19)`, and always sell if projected recovery time `(inventory - I0) / sink_rate` exceeds days left. This replaces the fixed 0.862×base gate that made sol5 hold milk for a $138 that never came, then dump at $1.
4. Never end a day with more than the next day's sink volume in stock for a fragile product; final 6 hours liquidate everything.

### 3e. Cash and land

Day 0: hire 4-5, buy 2 cows + 3 sheep (fertilizer + early wool/milk pie), 12 melon seeds, 8-10 wheat seeds; money ≈ $0 (Majkel's line). Fertilizer sold from day 1 funds hires. NE at $1,000 as soon as affordable after day 4 (day 5-6), SW at $2,000 around day 9 (after the first wool/milk sales, before melon). SE never.

## 4. Why this should beat the field

| Lever | Evidence | Expected gain vs sol5 in live games |
|---|---|---|
| Cows sized to milk shops (2-10 instead of 10) | forced test 92k→148k swing; live milk avg $8-42 with ≤1 shop | +15-25k in ~50% of draws, no loss in milk-rich draws |
| Sheep sized to yarn stores (3-12 instead of 4) | Gideon +$21k wool with 10 sheep and 3 yarn stores; our 127 wool @ $32-61 when 0 yarn stores | +10-20k when ≥2 yarn stores; +5k saved when 0 |
| Geese + wheat as labor filler | 543 eggs @ $54 and 994 wheat @ $35 absorbed in one game | +8-15k, zero market risk |
| Decaying reservation + scarcity selling | our strawberry avg $39-131 in losses vs opponents' $91-221 selling earlier | +5-10k |
| Culling / alternate-day feeding | winners do both; sol5 fed 10 worthless cows to the end | +2-4k labor and wheat |

Target: **≥ 95k average across forced shop schedules against flooder-class opponents**, worst draw ≥ 75k.

## 5. Validation harness (the part sol5 got wrong)

Do not evaluate on seeds; evaluate on **forced shop schedules × opponent archetypes**. Reuse the monkeypatch from `/tmp/kag_A/forced.py` (override the drawn shop in `_end_of_day`) inside `sol6/arena.py`:

- Schedules: milk-starved (replay 109564916), yarn-less, yarn×3 (Gideon game), milk-rich (5 milk shops), bakery-heavy, uniform-random ×6.
- Opponents: sol5 (open-loop flooder, closest to Aru Ohta), sol5 with 6 cows/10 sheep (Gideon-like), pass (absolute ceiling only), self-mirror.
- Milestones: M1 mechanics (fed ≥ 98% of animals we intend to keep, 0 unintended escapes, 0 overflow, ≤ 10 orders); M2 ≥ 85k average over schedules vs sol5; M3 worst-schedule ≥ 75k; M4 beats sol5 ≥ 14/16 and Gideon-like ≥ 12/16; M5 mirror even.
- CEM only on the few continuous knobs (share, reserve decay, straw tile scale, goose cap); gate on the schedule-averaged margin, never on a seed set.
- Parallel: 14 cores; split schedules across 3 concurrent jobs of 4 workers.

## 6. Risks

- **Late shop information.** A yarn store on day 21 is worth little (sheep first yield day 6 after placement). The gates in 3a already cap purchases by day; the fallback is geese/wheat.
- **Opponent takes more than half the sink.** The reservation decay ensures we still liquidate; the base counts (2 cows, 3 sheep) keep exposure small when the estimate is wrong.
- **Order cap (10/turn).** Sell orders for 5-7 products + hires can exceed 10 at hour 0: hires spill to hour 1 (sol5 already does this).
- **Walking share.** Adding geese in the core competes with pasture slots; cap animals in the core at 24 tiles and put extra coops at distance 3.
