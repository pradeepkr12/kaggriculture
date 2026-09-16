"""Milestone validation for a sol4 vector on held-out seeds (both seats).

Usage: python validate.py [quick|full] [vec as JSON list]
  quick: 4 seeds vs pass + sol3 + melon
  full : 8 seeds vs pass, starter, sol3, melon, self-mirror
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena import duel, DEFAULT_WORKERS
from farmlib import SEED_VEC

HELDOUT = [200, 201, 202, 203, 204, 205, 206, 207]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    vec = json.loads(sys.argv[2]) if len(sys.argv) > 2 else SEED_VEC
    seeds = HELDOUT[:4] if mode == "quick" else HELDOUT
    opps = {"pass": "pass", "sol3": "sol3", "melon": "melon"}
    if mode == "full":
        opps.update({"starter": "starter", "mirror": list(vec)})
    print(f"vec={vec}\nseeds={seeds}")
    t0 = time.time()
    for name, opp in opps.items():
        d = duel(vec, opp, seeds, workers=DEFAULT_WORKERS)
        print(f"  vs {name:8s} | me={d['a_mean']:8.0f}  opp={d['b_mean']:8.0f}  margin={d['margin']:+8.0f}  "
              f"W/L/T={d['wins']}/{d['losses']}/{d['ties']}  (n={d['n']})")
    print(f"  [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main()
