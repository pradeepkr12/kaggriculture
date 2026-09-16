"""Run planner+Hungarian on the standard matrix. Usage: python planner/run_hung.py [workers]"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import harness
if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    cand = ("file", os.path.join(HERE, "planner_hung.py"), "build_agent", [])
    opps = dict(harness.STD_OPPONENTS); opps["mirror"] = cand
    t = time.time()
    r = harness.run_matrix(cand, opps, seeds=[1000], workers=workers,
                           out=os.path.join(harness.RESULTS, "planner_hung.json"), label="planner+hungarian")
    harness.print_summary(r)
    for o in ("sol5", "gideon"):
        print(f"  margin by schedule vs {o}: " + "  ".join(f"{k}={v:+.0f}" for k, v in r["summary"][o]["by_schedule_margin"].items()))
    print(f"{time.time()-t:.0f}s")
