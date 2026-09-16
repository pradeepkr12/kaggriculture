"""Validate candidate strategies on HELD-OUT seeds (not used in optimization)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena import duel

HELDOUT = [200, 201, 202, 203, 204, 205, 206, 207]

MELON_SF  = [6, 0, 0, 0, 0, 3, 0, 16, 0.30]
HYB_STRAW = [4.0, 0, 0, 0, 3.0, 4, 1, 40, 0.80]

candidates = {
    "cem_best":   [3.25, 0, 0, 0.56, 4.62, 4.52, 1.28, 42, 0.71],
    "cem_mean":   [3.68, 0.24, 0.29, 0.35, 3.39, 5, 1, 42, 0.69],
    "straw_heavy":[3.0, 0, 0, 0, 5.0, 5, 1, 42, 0.72],
    "hyb_straw0": [4.0, 0, 0, 0, 3.0, 4, 1, 40, 0.80],
}

opponents = {"melon_sf": MELON_SF, "hyb_straw": HYB_STRAW, "starter": "starter", "pass": "pass"}


def main():
    for cname, cvec in candidates.items():
        print(f"\n### {cname} = {cvec}")
        for oname, ovec in opponents.items():
            d = duel(cvec, ovec, HELDOUT)
            print(f"  vs {oname:10s} | me={d['a_mean']:8.0f}  opp={d['b_mean']:8.0f}  "
                  f"margin={d['margin']:+8.0f}  W/L/T={d['wins']}/{d['losses']}/{d['ties']}")


if __name__ == "__main__":
    main()
