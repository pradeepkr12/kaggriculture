"""Planner prototype ablation over forced schedules x opponents, both seats.
Variants: plan_only (daily production planner + sol5 selling), sell_only (sol5 production +
opponent-aware selling), both. Usage: python run_ablation.py <workers> [variant,...]"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import harness

PL = os.path.join(HERE, "planner.py")
VARIANTS = {
    "plan_only": ("file", PL, "build_agent_plan_only", []),
    "sell_only": ("file", PL, "build_agent_sell_only", []),
    "both":      ("file", PL, "build_agent", []),
}

if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    names = sys.argv[2].split(",") if len(sys.argv) > 2 else list(VARIANTS)
    seeds = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else [1000]
    for name in names:
        cand = VARIANTS[name]
        opps = dict(harness.STD_OPPONENTS)
        opps["mirror"] = cand
        t = time.time()
        out = os.path.join(harness.RESULTS, f"planner_{name}.json")
        r = harness.run_matrix(cand, opps, seeds=seeds, workers=workers, out=out, label=f"planner:{name}")
        harness.print_summary(r)
        print(f"saved {out} ({time.time()-t:.0f}s)\n")
