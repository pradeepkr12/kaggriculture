# sol3 — Melon + Strawberry Hybrid (throttled shop-sink selling)

The submission-ready agent is **`main.py`** (`agent(obs)` at module top level).

## TL;DR

sol1 was a melon monoculture. Its low leaderboard score (451.8) turned out to be
a **sell-ordering bug** (it queued HIRE before SELL, so its melons sold into a
price the opponent had already crashed), *not* a melon problem. Once selling is
put first, melon is very strong. But the strongest strategy is a **hybrid**:

- **~20% melon** — highest base ($250), no shop consumes it, so uncontested it
  is a huge pie and contested it merely *splits* (which neutralizes a melon rival
  rather than losing to them).
- **~77% strawberry** — base $120, demanded by 4 shop types, sold **throttled**:
  each turn we sell only as many units as keep the price ≥ `0.71×base`, computed
  from the live shared market inventory. Town shops drain the market every 4
  turns, reopening room, so we ride a near-base price all season instead of
  crashing it.

This beats a strong sell-first melon opponent **16–0** on held-out seeds and
nets ~32k even in the worst case (self-mirror).

## Results (held-out seeds, both seats)

| Opponent | My score | Opp | Margin | W/L/T |
|---|---|---|---|---|
| sell-first melon | 31,915 | 20,855 | **+11,060** | 16/0/0 |
| melon+straw hybrid | 34,335 | 22,006 | +12,329 | 15/1/0 |
| strawberry-flooder | 37,603 | 15,534 | **+22,069** | 16/0/0 |
| aggressive melon+land | 31,210 | 13,939 | +17,271 | 16/0/0 |
| starter / pass / random | ~42k | ~3k/0 | ~+38k | 16/0/0 |
| **self-mirror** | 35,416 | 35,416 | +0 | fair |

## How it was built (RL / black-box optimization)

1. **`farmlib.py`** — a parametrized policy: a 9-dim strategy vector
   `[w_MELON, w_CARROT, w_TOMATO, w_WHEAT, w_STRAWBERRY, hands, land, tile_budget,
   sell_thresh]` decoded into per-turn actions by a fixed greedy multi-unit task
   assignment. Includes a port of the engine's `market_price` so the throttle can
   compute the exact sellable quantity.
2. **`arena.py`** — self-play harness. The optimization signal (the RL "return")
   is the average coin **margin** vs an opponent pool, played on both seats and
   several seeds to cancel first-mover and RNG noise.
3. **`optimize.py`** — Cross-Entropy Method over the strategy vector, maximizing
   margin vs a pool of {sell-first melon, melon+straw hybrid}. Converged to the
   strawberry-heavy hybrid baked into `main.py`.
4. **`validate.py` / `validate2.py`** — re-checked the winner on **held-out**
   seeds and adversarial opponents (flooders, aggressive melon, mirror).

## Files

| File | Purpose |
|---|---|
| `main.py` | **Submission** — self-contained hybrid agent |
| `farmlib.py` | Parametrized policy + decoder + market model (optimization target) |
| `arena.py` | Self-play margin evaluator (parallel, both seats) |
| `optimize.py` | CEM optimizer |
| `exp1.py` | shop-sink-only vs melon (showed melon is not weak) |
| `exp2.py` | how to beat melon (found the hybrid) |
| `validate.py`, `validate2.py` | held-out + adversarial validation |
| `REPORT.md` | Full write-up |

## Reproduce

```bash
python exp2.py       # find the hybrid
python optimize.py   # CEM (~7 min on 14 cores)
python validate.py   # held-out check
python validate2.py  # adversarial check
```
