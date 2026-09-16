"""Per-game diagnostics for sol8: animal counts by day, fed%, idle%, escapes,
latency, revenue. Uses the module agent so agent.planner.log / agent.stats are live.

Usage: python diag.py <schedule> <opp> <seat0|seat1> [seed]
"""
import os, sys, time, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "planner"))
import harness, planner_hung
from kaggle_environments import make
import farmlib_ph as F


def animals_on(farm):
    c = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t, dict) and "animal" in t:
                c[t["animal"]] += 1
    return c


def run(sched, opp, seat, seed=1000):
    times = []
    ag = planner_hung.build_agent()
    def timed(obs):
        t0 = time.perf_counter()
        try:
            return ag(obs)
        finally:
            times.append(time.perf_counter() - t0)
    opp_ag = harness.build(harness.STD_OPPONENTS.get(opp) if opp in harness.STD_OPPONENTS else opp)
    sales, restore = harness._patch(harness.SCHEDULES[sched])
    env = make("kaggriculture", configuration={"seed": seed}, debug=True)
    me = seat
    agents = [None, None]
    agents[seat] = timed
    agents[1 - seat] = opp_ag
    try:
        env.run(agents)
    finally:
        restore()
    # per-day animal counts at end of each day (from steps at hour 0 of next day)
    day_counts = {}
    for st in env.steps:
        obs = st[me]["observation"]
        d = obs["day"]
        if obs["hour"] == 0:
            day_counts[d] = animals_on(obs["farms"][me])
    final = env.steps[-1]
    rew = [float(final[0]["reward"]), float(final[1]["reward"])]
    # escapes: planner never culls cows/sheep; any unplanned drop in owned counts = escape
    log = ag.planner.log
    culls = {}
    for rec in log:
        for a, n in (rec.get("cull") or {}).items():
            culls[a] = max(culls.get(a, 0), n)
    escapes = 0
    prev = None
    for d in sorted(day_counts):
        cur = day_counts[d]
        if prev is not None:
            for a in cur:
                drop = prev[a] - cur[a]
                if drop > 0:
                    # allowed drop = newly planned culls this transition (rare)
                    escapes += max(0, drop)
        prev = cur
    # fed% for kept animals + idle share from mechanics stats
    days = ag.stats["days"]
    fed_num = fed_den = idle = uturns = 0
    for d, s in days.items():
        fed_num += s.get("fed", 0)
        fed_den += s.get("animals", 0)
        idle += s.get("idle", 0)
        uturns += s.get("unit_turns", 0)
    fedpct = 100.0 * fed_num / max(1, fed_den)
    idlepct = 100.0 * idle / max(1, uturns)
    lat = harness._lat(times)
    return {"sched": sched, "opp": opp, "seat": seat, "seed": seed, "rew": rew,
            "margin": rew[me] - rew[1 - me],
            "day_counts": day_counts, "escapes": escapes, "planned_culls": culls,
            "fed_pct": round(fedpct, 1), "idle_pct": round(idlepct, 1),
            "lat_ms": {k: round(v * 1000, 2) for k, v in lat.items() if k != "n"},
            "my_rev": {k: int(v) for k, v in sorted(sales.get(me, {}).get("rev", {}).items(), key=lambda x: -x[1])}}


if __name__ == "__main__":
    sched = sys.argv[1] if len(sys.argv) > 1 else "late_milk"
    opp = sys.argv[2] if len(sys.argv) > 2 else "sol5"
    seat = 1 if (len(sys.argv) > 3 and sys.argv[3] == "seat1") else 0
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
    r = run(sched, opp, seat, seed)
    print(f"{sched} vs {opp} seat{seat} seed{seed}: rew={r['rew']} margin={r['margin']:+.0f}")
    print(f"  escapes={r['escapes']} planned_culls={r['planned_culls']} fed%={r['fed_pct']} idle%={r['idle_pct']} lat_ms={r['lat_ms']}")
    print("  animal counts by day:")
    for d in (10, 12, 16, 20, 24, 26, 28):
        if d in r["day_counts"]:
            c = r["day_counts"][d]
            print(f"    d{d}: COW={c['COW']} SHEEP={c['SHEEP']} GOOSE={c['GOOSE']}")
    print("  revenue:", r["my_rev"])
