"""Experiment 1: does throttled shop-sink crop selling beat sell-first melon?

Vector = [w_MELON, w_CARROT, w_TOMATO, w_WHEAT, w_STRAWBERRY, hands, land, tile_budget, sell_thresh]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena import duel, fitness

SEEDS = [1, 2, 3, 4, 5]

# reference opponents
melon_sf   = [6, 0, 0, 0, 0, 3, 0, 16, 0.30]   # sell-first melon monoculture

# shop-sink candidates (no melon)
candidates = {
    "ss_balanced": [0, 3, 3, 2, 4, 3, 1, 40, 0.75],
    "ss_straw":    [0, 2, 3, 1, 5, 3, 1, 40, 0.80],
    "ss_fast":     [0, 4, 3, 3, 2, 3, 0, 24, 0.70],
    "ss_highthr":  [0, 3, 3, 2, 4, 3, 1, 40, 0.90],
    "ss_lowthr":   [0, 3, 3, 2, 4, 3, 1, 40, 0.55],
}


def main():
    print("=== vs sell-first MELON (both seats, 5 seeds = 10 games) ===")
    for name, vec in candidates.items():
        d = duel(vec, melon_sf, SEEDS)
        print(f"{name:12s} | me={d['a_mean']:8.0f}  melon={d['b_mean']:8.0f}  "
              f"margin={d['margin']:+8.0f}  W/L/T={d['wins']}/{d['losses']}/{d['ties']}")

    print("\n=== absolute score vs baselines (pass, starter) ===")
    for name, vec in candidates.items():
        f = fitness(vec, ["pass", "starter"], SEEDS)
        print(f"{name:12s} | my_mean={f['my_mean']:8.0f}  margin={f['margin']:+8.0f}  winrate={f['winrate']:.2f}")

    f = fitness(melon_sf, ["pass", "starter"], SEEDS)
    print(f"{'melon_sf':12s} | my_mean={f['my_mean']:8.0f}  margin={f['margin']:+8.0f}  winrate={f['winrate']:.2f}")


if __name__ == "__main__":
    main()
