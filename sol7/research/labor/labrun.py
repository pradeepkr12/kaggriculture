"""Local game runner that keeps a handle on the agents (stats / log / trace).
Mirrors harness.play but returns agent.stats and optional per-turn logs.

Spec forms: "pass" | ("sol5", None) | ("labor", {"hungarian": bool})
"""
import os, sys, json, time
LABOR = os.path.dirname(os.path.abspath(__file__))
RESEARCH = os.path.dirname(LABOR)
RESULTS = os.path.join(RESEARCH, "results")
sys.path.insert(0, RESEARCH)
sys.path.insert(0, LABOR)
import harness                      # noqa: E402
from kaggle_environments import make  # noqa: E402
import farmlib_labor as FL          # noqa: E402


def build_local(spec, log=None, trace=None):
    if isinstance(spec, tuple) and spec[0] == "labor":
        return FL.build_agent(hungarian=spec[1].get("hungarian", False), log=log, trace=trace)
    return harness.build(spec)


def play_full(spec0, spec1, schedule_name="milk_starved", seed=1000, log_seat=None, trace_seat=None):
    schedule = harness.SCHEDULES[schedule_name]
    sales, restore = harness._patch(schedule)
    log, trace = [], []
    agents, raw = [], []
    try:
        for i, sp in enumerate((spec0, spec1)):
            a = build_local(sp, log=log if i == log_seat else None, trace=trace if i == trace_seat else None)
            raw.append(a if callable(a) else None)
            agents.append(harness.timed(a) if callable(a) else a)
        env = make("kaggriculture", configuration={"seed": seed}, debug=False)
        env.run(agents)
    finally:
        restore()
    final = env.steps[-1]
    out = {"seed": seed, "schedule": schedule_name, "specs": [repr(spec0), repr(spec1)],
           "rewards": [float(final[0]["reward"]), float(final[1]["reward"])],
           "stats": [getattr(a, "stats", None) if a is not None else None for a in raw],
           "latency": [harness._lat(a.times) if hasattr(a, "times") else None for a in agents],
           "rev": [sales.get(p, {}).get("rev", {}) for p in range(2)],
           "log": log, "trace": trace}
    return out


BANDS = [("d00_09", 0, 9), ("d10_19", 10, 19), ("d20_29", 20, 29)]


def walk_summary(stats):
    """Totals + by-band walking share from agent.stats['days']."""
    days = stats["days"]
    def agg(lo, hi):
        keys = ["moves", "actions", "idle", "unit_turns", "feeder_turns", "feeder_moves",
                "crew_turns", "crew_moves", "home_moves"]
        t = {k: 0 for k in keys}
        for d, ds in days.items():
            d = int(d)
            if lo <= d <= hi:
                for k in keys:
                    t[k] += ds.get(k, 0)
        if not t["unit_turns"]:
            t["unit_turns"] = t["moves"] + t["actions"] + t["idle"]   # plain sol5 stats
        ut = max(1, t["unit_turns"])
        t["walk_share"] = t["moves"] / ut
        t["action_share"] = t["actions"] / ut
        t["idle_share"] = t["idle"] / ut
        if t["feeder_turns"]:
            t["feeder_walk_share"] = t["feeder_moves"] / t["feeder_turns"]
        if t["crew_turns"]:
            t["crew_walk_share"] = (t["crew_moves"] + t["home_moves"]) / t["crew_turns"]
            t["crew_task_walk_share"] = t["crew_moves"] / t["crew_turns"]
        return t
    out = {"total": agg(0, 29)}
    for name, lo, hi in BANDS:
        out[name] = agg(lo, hi)
    return out
