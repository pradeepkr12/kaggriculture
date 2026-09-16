"""sol8 validation arena. Runs the candidate (sol7 or sol8) over the full opponent x
schedule x seat x seed matrix using research/harness.py and writes results/<cand>.json.

Usage:
  python arena.py --cand sol8 --seeds 1000,2000 --workers 14 --out results/sol8.json
  python arena.py --cand sol7 ...
"""
import os, sys, time, json, argparse, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "research"))
sys.path.insert(0, os.path.join(HERE, "research", "planner"))
import harness

SOL8_MAIN = os.path.join(HERE, "main.py")
SOL7_MAIN = os.path.join(ROOT, "sol7", "main.py")
SOL6_MAIN = os.path.join(ROOT, "sol6", "main.py")
SOL6_VEC = [14, 2, 3, 10, 12, 4, 10, 24, 32, 30, 6, 5, 8, 11, 0.5, 0.9, 0.65, 0.25, 27, 0, 9, 3, 4, 15]

CANDS = {
    "sol8": ("file", SOL8_MAIN, "build_agent", []),
    "sol7": ("file", SOL7_MAIN, "build_agent", []),
}


def opponents(exclude_self_file=None):
    return {
        "sol5":   ("sol5", None),
        "gideon": ("sol5p", {"n_cows": 6, "n_sheep": 10}),
        "sol6":   ("file", SOL6_MAIN, "build_agent", [SOL6_VEC]),
        "sol7":   ("file", SOL7_MAIN, "build_agent", []),
        "pass":   "pass",
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="sol8")
    ap.add_argument("--seeds", default="1000,2000")
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cand = CANDS[a.cand]
    opps = opponents()
    opps["mirror"] = cand
    seeds = [int(x) for x in a.seeds.split(",")]
    scheds = harness.SCHEDULE_NAMES
    out = a.out or os.path.join(HERE, "results", f"{a.cand}.json")
    t = time.time()
    r = harness.run_matrix(cand, opps, schedules=scheds, seeds=seeds, workers=a.workers, out=out, label=a.cand)
    harness.print_summary(r)
    print(f"saved {out} ({time.time()-t:.0f}s)")
