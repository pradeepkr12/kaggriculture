"""Head-to-head comparison of candidate vectors on held-out seeds.

Usage: python compare.py '<cand vec json>' ['<ref vec json>']   (ref default: SEED_VEC)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena import duel
from farmlib import SEED_VEC, vec_to_params

HELDOUT = [200, 201, 202, 203, 204, 205, 206, 207]


def main():
    cand = json.loads(sys.argv[1])
    ref = json.loads(sys.argv[2]) if len(sys.argv) > 2 else list(SEED_VEC)
    print("cand params:", vec_to_params(cand))
    d = duel(cand, ref, HELDOUT)
    print(f"cand vs REF  : me={d['a_mean']:8.0f} opp={d['b_mean']:8.0f} margin={d['margin']:+8.0f} W/L/T={d['wins']}/{d['losses']}/{d['ties']}")
    d = duel(cand, "pass", HELDOUT)
    print(f"cand vs pass : me={d['a_mean']:8.0f}                margin={d['margin']:+8.0f} W/L/T={d['wins']}/{d['losses']}/{d['ties']}")
    d = duel(cand, "sol3", HELDOUT)
    print(f"cand vs sol3 : me={d['a_mean']:8.0f} opp={d['b_mean']:8.0f} margin={d['margin']:+8.0f} W/L/T={d['wins']}/{d['losses']}/{d['ties']}")
    d = duel(cand, cand, HELDOUT[:4])
    print(f"cand mirror  : {d['a_mean']:8.0f} each")


if __name__ == "__main__":
    main()
