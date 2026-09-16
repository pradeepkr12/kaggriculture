"""planner+Hungarian and sol5 vs the submitted sol6 (read-only), 6 schedules, both seats."""
import os, sys, time, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
import harness
SOL6 = os.path.join(harness.ROOT, "sol6", "main.py")
if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    vec = json.loads(open(SOL6).read().split("\nVEC = ")[1].split("\n")[0])
    sol6 = ("file", SOL6, "build_agent", [vec])
    for label, cand in (("planner+hungarian", ("file", os.path.join(HERE, "planner_hung.py"), "build_agent", [])),
                        ("sol5", ("sol5", None))):
        t = time.time()
        r = harness.run_matrix(cand, {"sol6": sol6}, seeds=[1000], workers=workers,
                               out=os.path.join(harness.RESULTS, f"vs_sol6_{label.replace('+','_')}.json"), label=label + " vs sol6")
        harness.print_summary(r)
        print("  margin by schedule: " + "  ".join(f"{k}={v:+.0f}" for k, v in r["summary"]["sol6"]["by_schedule_margin"].items()), f"({time.time()-t:.0f}s)")
