"""Oracle upper bound for adaptive production: for each forced schedule, sweep sol5's
animal/strawberry counts (with knowledge of the schedule) vs the fixed sol5 opponent,
both seats. The best per-schedule config bounds what an online planner could gain by
adapting production to the observed shop draw."""
import os, sys, json, time, itertools, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness
from concurrent.futures import ProcessPoolExecutor

GRID = {
    "n_cows": [2, 4, 6, 10],
    "n_sheep": [2, 4, 7, 10],
    "n_geese": [1, 4, 8],
    "straw_tiles": [20, 32],
}

def job(args):
    cfg, sched, seed, swap = args
    cand = ("sol5p", cfg)
    opp = ("sol5", None)
    if swap:
        r = harness.play(opp, cand, sched, seed); me, op = 1, 0
    else:
        r = harness.play(cand, opp, sched, seed); me, op = 0, 1
    return {"cfg": cfg, "schedule": sched, "seat": me, "me": r["rewards"][me], "opp": r["rewards"][op],
            "me_rev": r["players"][me]["rev"]}

if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    seed = 1000
    cfgs = [dict(zip(GRID, vals)) for vals in itertools.product(*GRID.values())]
    jobs = [(c, s, seed, sw) for c in cfgs for s in harness.SCHEDULE_NAMES for sw in (False, True)]
    print(len(jobs), "games")
    t = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(job, jobs, chunksize=4))
    # aggregate: per (cfg, schedule) mean over seats
    agg = {}
    for r in res:
        k = (json.dumps(r["cfg"], sort_keys=True), r["schedule"])
        agg.setdefault(k, []).append(r)
    rows = []
    for (ck, s), rs in agg.items():
        rows.append({"cfg": json.loads(ck), "schedule": s,
                     "me": statistics.mean(x["me"] for x in rs),
                     "opp": statistics.mean(x["opp"] for x in rs),
                     "margin": statistics.mean(x["me"] - x["opp"] for x in rs)})
    best = {}
    for s in harness.SCHEDULE_NAMES:
        rs = [r for r in rows if r["schedule"] == s]
        rs.sort(key=lambda r: -r["margin"])
        best[s] = rs[:5]
    # also best single fixed config across schedules (what CEM could reach)
    by_cfg = {}
    for r in rows:
        by_cfg.setdefault(json.dumps(r["cfg"], sort_keys=True), []).append(r)
    fixed = sorted(((statistics.mean(x["margin"] for x in rs), statistics.mean(x["me"] for x in rs), ck)
                    for ck, rs in by_cfg.items()), reverse=True)
    out = {"seed": seed, "grid": GRID, "rows": rows, "best_per_schedule": best,
           "best_fixed": [{"margin": m, "me": me, "cfg": json.loads(ck)} for m, me, ck in fixed[:10]],
           "elapsed_s": time.time() - t,
           "cmd": "python sol7/research/planner/oracle_grid.py 6"}
    os.makedirs(harness.RESULTS, exist_ok=True)
    with open(os.path.join(harness.RESULTS, "oracle_grid.json"), "w") as f:
        json.dump(out, f)
    print(f"elapsed {time.time()-t:.0f}s")
    for s in harness.SCHEDULE_NAMES:
        b = best[s][0]
        print(f"{s:13s} best cfg={b['cfg']} me={b['me']:.0f} opp={b['opp']:.0f} margin={b['margin']:+.0f}")
    print("best fixed:", fixed[0][:2], json.loads(fixed[0][2]))
    print("oracle mean margin:", statistics.mean(best[s][0]["margin"] for s in harness.SCHEDULE_NAMES),
          " fixed-best mean margin:", fixed[0][0])
