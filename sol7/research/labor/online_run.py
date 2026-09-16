"""Task 3: online control vs Hungarian, harness.run_matrix (both seats, 6 schedules,
seed 1000) vs {sol5, pass}; plus walking share on the same 24 games per variant.
Reproduce: /opt/miniconda3/envs/env2/bin/python online_run.py
"""
import json, os, sys, time, statistics as S
from concurrent.futures import ProcessPoolExecutor
from labrun import play_full, walk_summary, RESULTS, LABOR
import harness
FILE = os.path.join(LABOR, "farmlib_labor.py")
CANDS = {"control": ("file", FILE, "build_agent", []),
         "hungarian": ("file", FILE, "build_agent_hungarian", [])}
LOCAL = {"control": ("labor", {"hungarian": False}), "hungarian": ("labor", {"hungarian": True})}
OPPS = {"sol5": harness.STD_OPPONENTS["sol5"], "pass": "pass"}


def _walk_job(args):
    name, oname, sched, swap = args
    me = LOCAL[name]
    opp = OPPS[oname]
    r = play_full(opp, me, sched, 1000) if swap else play_full(me, opp, sched, 1000)
    seat = 1 if swap else 0
    st = r["stats"][seat]
    return {"cand": name, "opp": oname, "schedule": sched, "seat": seat, "me": r["rewards"][seat],
            "walk": walk_summary(st)["total"], "lat": r["latency"][seat],
            "hung_ncols_max": st.get("hung_ncols_max")}


if __name__ == "__main__":
    t0 = time.time()
    out = {"command": "cd sol7/research/labor && /opt/miniconda3/envs/env2/bin/python online_run.py",
           "seed": 1000, "schedules": harness.SCHEDULE_NAMES, "opponents": {k: repr(v) for k, v in OPPS.items()},
           "matrix": {}, "walking": {}}
    for name, cand in CANDS.items():
        res = harness.run_matrix(cand, OPPS, harness.SCHEDULE_NAMES, (1000,), workers=4, out=None, label=name)
        harness.print_summary(res)
        out["matrix"][name] = res
    jobs = [(n, o, s, sw) for n in CANDS for o in OPPS for s in harness.SCHEDULE_NAMES for sw in (False, True)]
    with ProcessPoolExecutor(max_workers=4) as ex:
        wr = list(ex.map(_walk_job, jobs))
    for name in CANDS:
        for oname in OPPS:
            rs = [w for w in wr if w["cand"] == name and w["opp"] == oname]
            mv = sum(w["walk"]["moves"] for w in rs); ut = sum(w["walk"]["unit_turns"] for w in rs)
            ac = sum(w["walk"]["actions"] for w in rs); idl = sum(w["walk"]["idle"] for w in rs)
            out["walking"][f"{name}_vs_{oname}"] = {
                "games": len(rs), "moves": mv, "actions": ac, "idle": idl, "unit_turns": ut,
                "walk_share": mv / ut, "action_share": ac / ut, "idle_share": idl / ut,
                "crew_walk_share": sum(w["walk"]["crew_moves"] + w["walk"]["home_moves"] for w in rs) / max(1, sum(w["walk"]["crew_turns"] for w in rs)),
                "feeder_walk_share": sum(w["walk"]["feeder_moves"] for w in rs) / max(1, sum(w["walk"]["feeder_turns"] for w in rs)),
                "actions_per_game": ac / len(rs), "moves_per_game": mv / len(rs),
                "lat_max_ms": max(w["lat"]["max"] for w in rs) * 1000,
                "lat_p99_ms_max": max(w["lat"]["p99"] for w in rs) * 1000,
                "lat_mean_ms": S.mean(w["lat"]["mean"] for w in rs) * 1000,
                "hung_ncols_max": max((w["hung_ncols_max"] or 0) for w in rs),
                "me_mean_check": S.mean(w["me"] for w in rs)}
            w = out["walking"][f"{name}_vs_{oname}"]
            print(f"{name:9s} vs {oname:5s}: walk={w['walk_share']:.3f} crew_walk={w['crew_walk_share']:.3f} feeder_walk={w['feeder_walk_share']:.3f} "
                  f"actions/game={w['actions_per_game']:.0f} moves/game={w['moves_per_game']:.0f} idle={w['idle_share']:.3f} "
                  f"lat mean={w['lat_mean_ms']:.2f}ms p99max={w['lat_p99_ms_max']:.1f}ms max={w['lat_max_ms']:.0f}ms  me_mean={w['me_mean_check']:.0f}")
    # compact comparison table
    table = {}
    for oname in OPPS:
        c = out["matrix"]["control"]["summary"][oname]; h = out["matrix"]["hungarian"]["summary"][oname]
        table[oname] = {"control": {"me_mean": c["me_mean"], "margin": c["margin"], "wins": c["wins"], "lat_max_ms": c["lat_max"] * 1000, "lat_p99_ms": c["lat_p99"] * 1000,
                                    "by_schedule": c["by_schedule"]},
                        "hungarian": {"me_mean": h["me_mean"], "margin": h["margin"], "wins": h["wins"], "lat_max_ms": h["lat_max"] * 1000, "lat_p99_ms": h["lat_p99"] * 1000,
                                      "by_schedule": h["by_schedule"]},
                        "delta_me_mean": h["me_mean"] - c["me_mean"], "delta_margin": h["margin"] - c["margin"]}
        # paired per-game deltas
        cg = {(g["schedule"], g["seat"]): g["me"] for g in out["matrix"]["control"]["games"][oname]}
        hg = {(g["schedule"], g["seat"]): g["me"] for g in out["matrix"]["hungarian"]["games"][oname]}
        d = [hg[k] - cg[k] for k in cg]
        table[oname]["paired_delta"] = {"mean": S.mean(d), "min": min(d), "max": max(d), "wins": sum(1 for x in d if x > 0), "n": len(d),
                                        "stdev": S.stdev(d) if len(d) > 1 else 0.0}
    out["table"] = table
    print(json.dumps(table, indent=1))
    out["elapsed_s"] = time.time() - t0
    p = os.path.join(RESULTS, "labor_hungarian.json")
    with open(p, "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("saved", p, f"({out['elapsed_s']:.0f}s)")
