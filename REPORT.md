# Kaggriculture — Submission Report

**Date:** 2026-09-10
**Submission ID:** `56146676` (`main.py`)
**Goal:** an agent that reliably finishes a season with **9,000+ coins** (start money is $3,000, so net **+6,000**).
**Outcome:** target cleared with large margin — **~31.6k** vs baselines, **~15.1k** in the contested-market worst case.

---

## 1. The Problem

Kaggriculture is a **two-player competitive farming sim** on the `kaggle-environments` framework. You write an `agent(obs)` function; the winner is whoever holds the **most coins at the end of the season**. Unsold inventory is worth nothing — only banked cash counts.

Key parameters (defaults):

- **Season:** 30 days × 24 turns/day = **720 turns**. Start with **$3,000**.
- **Farm:** 10×10 grid = four 5×5 quadrants. Only NW (25 tiles) is unlocked; the rest cost $1k / $2k / $4k via `BUY_LAND`.
- **Labor:** 1 permanent farmer + hireable day-hands. Each unit takes **one action per turn**. Up to 10 market orders per turn.
- **Maintenance:** every plant must be watered (and every animal fed) at least every other day or it dies. The planting day itself counts as the first unwatered day.
- **Market:** shared between both players. Sale price moves with market inventory — falls as supply grows (gluts), rises as it drains.

### The two binding constraints

1. **Labor.** Each unit does one thing per turn, and *moving between tiles costs a turn*. Watering N scattered tiles daily can exceed a single farmer's 24 actions. Labor — not money — is the real bottleneck.
2. **Market gluts.** Selling too much of one product crashes its price. Premium goods (strawberry, melon, milk, wool) crash hardest.

---

## 2. Strategy

The whole design follows from reading the engine source (`kaggriculture.py`) rather than the docs, to get the exact formulas.

### Why melon

| Property | Value | Why it matters |
| --- | --- | --- |
| Base sale price | **$250** | Highest of any product |
| Seed cost | $80 | Cheap relative to yield |
| Units per tile | up to **6** | 6 × ~$250 ≈ $1,500/tile/cycle |
| Shop demand | **none** | No town *shop* consumes melon — only the town center (1/day). No competing demand, and its glut curve starts very high |

Melon's glut curve is `sq` shape with a tiny amplitude (`amp = 3.60·250/300² ≈ 0.01`), so the marginal sell price is roughly:

```
price ≈ 250 − 0.01 · (net_melons_sold)²
```

That stays above ~$215 for the first ~100 melons and only floors ($1) past ~158. **Selling ~100 melons ≈ $20k revenue** — comfortably past target on a single product.

Melon is also the most **labor-efficient** crop: ~10 unit-actions (1 plant + ~8 waters + 1 harvest) produce 6 melons ≈ $1,500, i.e. **~$140 per action** — far above carrot (~$21/action) or wheat.

### Why hire hands

Hire cost is `fib(n)` for the n-th hire of the day: **1, 1, 2, 3, 5, 8…** So 3 hands/day costs just **$4/day** (~$120/season) and triples labor. Since labor is the bottleneck, this is the single highest-ROI spend in the game. The agent hires **3 hands every morning**.

### The greedy engine

Each turn, every unit (farmer + hands) is assigned the highest-value nearby task:

| Priority | Task | Reason |
| --- | --- | --- |
| 5 | **Survival water** (`consecutive_unwatered ≥ 1`, unwatered) | Plant dies tonight if skipped |
| 4 | **Harvest** (age ≥ 10, yield ripe) | Bank the melons |
| 3 | **Bonus water** (in day-6→12 window, yield < 6) | Adds +1 yield/watered day |
| 2 | **Plant** (empty tile, under cap) | Grow more |
| 1 | **Dig weed** | Reclaim land |

Tasks are sorted by priority and assigned to the nearest free unit (Manhattan distance); a unit on its target tile performs the action, otherwise it steps one tile toward it. The engine also respects the game's *atomic-plant* rule (if more units try to plant than there are seeds, all those plants would be dropped) by capping plant actions to available seed count.

A nice emergent property: because `consecutive_unwatered` resets to 0 when a plant is watered, the priority rules automatically produce **water-on-planting-day, then every-other-day survival watering, then daily watering during the yield window** — the optimal watering cadence, with no special-casing.

### Selling & spending

- **Sell all shed melons every turn.** Melon price only recovers via town consumption (~1/day, negligible), so holding never helps; selling every turn also keeps the shed under its 100-item cap.
- **Seed buffer:** keep ~5 melon seeds in stock, buying ahead (market orders resolve after unit actions, so seeds bought this turn are usable next turn).
- **Money buffer:** keep $200 cash before discretionary spend.
- **Caps:** at most **16 active melon tiles**; stop planting after **day 18** (a melon needs 10 days to mature before the day-29 finish). These bound total production so we don't waste labor growing melons that would only sell near the $1 floor.

*(Land expansion was evaluated and left off: NW's 25 tiles already exceed what farmer + 3 hands can water daily, so buying land adds cost without adding throughput at this scale.)*

---

## 3. Validation

Two harnesses were used, both running full 720-turn seasons on the real `kaggle-environments` engine (`kaggle-environments 1.32.7`, Python 3.13).

### 3a. Against built-in baselines — `eval.py`

6 seeded games per opponent, alternating player seat (0/1) for fairness:

| Opponent | My avg score | Min / Max | Opponent avg | Win rate |
| --- | --- | --- | --- | --- |
| `random` | **31,644** | 31,644 / 31,644 | 0 | 6/6 |
| `starter` | **31,644** | 31,644 / 31,644 | 3,542 | 6/6 |
| `pass` | **31,644** | 31,644 / 31,644 | 3,000 | 6/6 |

Scores are identical across seeds because melon revenue dominates and the only RNG (weed spawns at 0.5%/tile) is negligible, and these opponents never touch the melon market.

### 3b. Contested market — self-play

The real risk is the **shared market**: an opponent also dumping melons splits the melon revenue pie. Worst realistic case = my agent vs. an identical copy of itself:

```
SELF-PLAY (contested melon market), seed 7:
  P0 reward: 15,135
  P1 reward: 15,135
  melon market: inv=10,150  price=$25   (≈150 melons sold combined, price driven down)
  P0: money=15,135   P1: money=15,135
```

Even when a mirror opponent is flooding the same market and the price has crashed from $250 to $25, **each player still nets +$12,135** — well above the 9,000 target.

### What was checked

- ✅ Beats all three built-in baselines every game.
- ✅ Survives a contested market (identical melon-dumping opponent) with score ≥ 15k.
- ✅ Money in the final state equals real melon sales through the normal market mechanics — **not an exploit or engine bug** (verified by inspecting market inventory/price and farm state at game end).
- ✅ Runs without errors across 18 baseline games + self-play, on both player seats.
- ✅ Submission format correct: `main.py` at root with an `agent(obs)` function.

### Known limitations / risk

- **Single-product dependency.** All revenue is melon. A strong leaderboard opponent that rushes melon harder/earlier could take more of the ~$26k melon pie than a mirror match does. Self-play (~15k each) is the estimated floor, not a guarantee against an adversary optimized to starve us.
- **No diversification.** Days 0–9 (before melons mature) leave labor idle. Adding a fast early crop (carrots/tomatoes — separate markets) or an animal line would hedge market risk and use idle early turns. Deferred because it isn't needed for the 9,000 target.

---

## 4. Submission

```bash
kaggle competitions submit kaggriculture -f main.py \
  -m "Melon monoculture, 3 hands/day, greedy multi-unit task assignment"
```

- **Submission ID:** `56146676`
- **Status at submit time:** PENDING (Kaggle validates, then plays ranked episodes)
- Rules were accepted on the site before submitting.

### Monitoring

```bash
kaggle competitions submissions kaggriculture      # status + score
kaggle competitions episodes 56146676              # games it has played
kaggle competitions leaderboard kaggriculture -s   # standing
```

---

## 5. Files

| File | Purpose |
| --- | --- |
| `main.py` | The agent (submission-ready; `agent(obs)` at root) |
| `eval.py` | Seeded evaluation harness vs baselines |
| `README.md` / `AGENTS.md` | Competition-provided game rules and getting-started guide |
| `REPORT.md` | This report |

### Possible next steps

1. **Monitor** the submission's leaderboard score.
2. **Harden** if needed: add early carrots/tomatoes and/or an animal line to diversify away from a single market (4 submissions/day remain).
