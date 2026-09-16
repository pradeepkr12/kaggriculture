"""Final robustness check for cem_best: contested strawberry + aggressive melon."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena import duel

HELDOUT = [300, 301, 302, 303, 304, 305, 306, 307]
CEM_BEST = [3.25, 0, 0, 0.56, 4.62, 4.52, 1.28, 42, 0.71]

opponents = {
    "self_mirror":  [3.25, 0, 0, 0.56, 4.62, 4.52, 1.28, 42, 0.71],
    "straw_flood":  [0, 0, 0, 0, 6.0, 5, 1, 48, 0.55],   # opponent floods strawberry
    "melon_agro":   [6, 0, 0, 0, 0, 5, 2, 55, 0.30],       # aggressive melon+land
    "random":       "random",
}


def main():
    print(f"cem_best = {CEM_BEST}")
    for oname, ovec in opponents.items():
        d = duel(CEM_BEST, ovec, HELDOUT)
        print(f"  vs {oname:12s} | me={d['a_mean']:8.0f}  opp={d['b_mean']:8.0f}  "
              f"margin={d['margin']:+8.0f}  W/L/T={d['wins']}/{d['losses']}/{d['ties']}")


if __name__ == "__main__":
    main()
