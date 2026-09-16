"""Experiment 2: how to BEAT a strong sell-first melon opponent (the meta).

Two ideas:
  (a) contest melon harder (more tiles/hands/land) -> take more of shared pie
  (b) hybrid: melon + uncontested shop-sink crops -> extra income opp can't touch

Vector = [w_MELON, w_CARROT, w_TOMATO, w_WHEAT, w_STRAWBERRY, hands, land, tile_budget, sell_thresh]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena import duel

SEEDS = [1, 2, 3, 4, 5]
melon_sf = [6, 0, 0, 0, 0, 3, 0, 16, 0.30]

candidates = {
    "melon_sf(ref)":  [6, 0, 0, 0, 0, 3, 0, 16, 0.30],
    "melon_tiles25":  [6, 0, 0, 0, 0, 3, 0, 25, 0.30],
    "melon_hands5":   [6, 0, 0, 0, 0, 5, 0, 25, 0.30],
    "melon_land1":    [6, 0, 0, 0, 0, 4, 1, 40, 0.30],
    "melon_land2":    [6, 0, 0, 0, 0, 5, 2, 55, 0.30],
    # hybrids: melon weight dominant but crops get a slice via softmax
    "hyb_m_straw":    [4.0, 0, 0, 0, 3.0, 4, 1, 40, 0.80],
    "hyb_m_tom_str":  [4.0, 0, 3.0, 0, 3.0, 4, 1, 40, 0.80],
    "hyb_m_all":      [3.5, 2.5, 2.5, 2.0, 3.0, 5, 1, 45, 0.80],
    "hyb_melheavy":   [5.0, 0, 2.0, 0, 3.0, 4, 1, 36, 0.80],
}


def main():
    print("=== vs sell-first MELON (both seats, 5 seeds = 10 games) ===")
    rows = []
    for name, vec in candidates.items():
        d = duel(vec, melon_sf, SEEDS)
        rows.append((d["margin"], name, d))
        print(f"{name:16s} | me={d['a_mean']:8.0f}  opp={d['b_mean']:8.0f}  "
              f"margin={d['margin']:+8.0f}  W/L/T={d['wins']}/{d['losses']}/{d['ties']}")
    print("\n-- ranked by margin vs melon_sf --")
    for margin, name, d in sorted(rows, reverse=True):
        print(f"  {name:16s} margin={margin:+8.0f}  W/L/T={d['wins']}/{d['losses']}/{d['ties']}")


if __name__ == "__main__":
    main()
