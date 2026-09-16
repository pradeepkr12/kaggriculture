"""Shared research harness for sol7.

* Forced shop schedules (monkeypatch of kaggriculture._end_of_day) so that
  experiments are reproducible across the town's random shop draw.
* Instrumentation of _commit_unit -> per-player per-product SELL revenue/units.
* Per-turn agent latency (max / p99 / mean) for each seat.
* Picklable agent specs so games can run in a ProcessPool.

Agent spec forms:
  "pass" | "random" | "starter"                      builtin engine agents
  ("sol5", None)                                      sol5 SEED_VEC
  ("sol5", [vec])                                     sol5 code with a vector
  ("sol5p", {"n_cows": 6, "n_sheep": 10})             sol5 SEED_VEC with param overrides
  ("file", "/abs/path.py", "build_agent", [args...])  any module exposing a builder
  ("file", "/abs/path.py", "agent", None)             module exposing agent(obs) directly
"""
import os, sys, json, time, random, statistics, importlib.util
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOL5 = os.path.join(ROOT, "sol5")
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

import kaggle_environments.envs.kaggriculture.kaggriculture as K
from kaggle_environments import make

SHOP_NAMES = sorted(K.SHOPS)

SCHEDULES = {
    "milk_starved": ["BAKERY", "BAKERY", "BRUNCH_SPOT", "FARMERS_MARKET", "YARN_STORE", "BAKERY", "SMOOTHIE_SHOP", "PET_CAFE"],
    "yarnless":     ["PIZZA_SHOP", "BAKERY", "FARMERS_MARKET", "BRUNCH_SPOT", "ICE_CREAM_SHOP", "PET_CAFE", "BAKERY", "SMOOTHIE_SHOP"],
    "yarn_x3":      ["FARMERS_MARKET", "YARN_STORE", "YARN_STORE", "YARN_STORE", "SMOOTHIE_SHOP", "SMOOTHIE_SHOP", "PET_CAFE", "FARMERS_MARKET"],
    "milk_rich":    ["PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "PIZZA_SHOP", "ICE_CREAM_SHOP"],
    "late_milk":    ["FARMERS_MARKET", "BAKERY", "BAKERY", "YARN_STORE", "ICE_CREAM_SHOP", "ICE_CREAM_SHOP", "ICE_CREAM_SHOP", "BRUNCH_SPOT"],
    "random_a":     random.Random(7).choices(SHOP_NAMES, k=8),
    "random_b":     random.Random(11).choices(SHOP_NAMES, k=8),
}
SCHEDULE_NAMES = list(SCHEDULES)


def _load(path, name=None):
    name = name or ("mod_" + str(abs(hash(path))))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SOL5 = {}


def sol5_mod():
    if "m" not in _SOL5:
        _SOL5["m"] = _load(os.path.join(SOL5, "farmlib.py"), "sol5_farmlib")
    return _SOL5["m"]


def build(spec):
    if isinstance(spec, str):
        return spec
    kind = spec[0]
    if kind == "sol5":
        m = sol5_mod()
        return m.build_agent(list(spec[1]) if spec[1] is not None else m.SEED_VEC)
    if kind == "sol5p":
        m = sol5_mod()
        p = m.vec_to_params(m.SEED_VEC)
        p.update(spec[1])
        return m.build_agent(p)
    if kind == "file":
        _, path, fn, args = spec
        m = _load(path)
        f = getattr(m, fn)
        if args is None:
            return f
        if isinstance(args, dict):
            return f(**args)
        return f(*args)
    raise ValueError(spec)


# ---- instrumentation ----------------------------------------------------------
def _patch(schedule):
    """Install forced-schedule + sales-recording patches. Returns (sales, restore)."""
    orig_eod = K._end_of_day
    orig_commit = K._commit_unit
    orig_pm = K._process_market
    sales = {}          # player idx -> {"rev": {item: $}, "units": {item: n}, "spend": {item: $}}
    farm_to_player = {}

    def eod(state, env, day):
        town = state[0].observation.town
        before = len(town["unlocked_shops"])
        orig_eod(state, env, day)
        if schedule is not None and len(town["unlocked_shops"]) > before:
            idx = (day + 1) // 3 - 1
            if 0 <= idx < len(schedule):
                town["unlocked_shops"][-1] = schedule[idx]

    def pm(state, env):
        farm_to_player.clear()
        farms = state[0].observation.farms
        for i, f in enumerate(farms):
            farm_to_player[id(f)] = i
        return orig_pm(state, env)

    def commit(op, item, price, farm, private, market, shed_capacity=100):
        ok = orig_commit(op, item, price, farm, private, market, shed_capacity)
        if ok:
            p = farm_to_player.get(id(farm), -1)
            rec = sales.setdefault(p, {"rev": {}, "units": {}, "spend": {}})
            if op == "SELL":
                rec["rev"][item] = rec["rev"].get(item, 0) + price
                rec["units"][item] = rec["units"].get(item, 0) + 1
            else:
                rec["spend"][item] = rec["spend"].get(item, 0) + price
        return ok

    K._end_of_day = eod
    K._commit_unit = commit
    K._process_market = pm

    def restore():
        K._end_of_day = orig_eod
        K._commit_unit = orig_commit
        K._process_market = orig_pm
    return sales, restore


def timed(fn):
    """Wrap agent(obs) in a plain function (the runner inspects __code__.co_argcount)."""
    times = []
    def agent(obs):
        t = time.perf_counter()
        try:
            return fn(obs)
        finally:
            times.append(time.perf_counter() - t)
    agent.times = times
    return agent


def _lat(times):
    if not times:
        return None
    s = sorted(times)
    return {"max": s[-1], "p99": s[int(0.99 * (len(s) - 1))], "mean": statistics.mean(s), "n": len(s)}


def play(spec0, spec1, schedule_name=None, seed=1000):
    schedule = SCHEDULES[schedule_name] if schedule_name else None
    sales, restore = _patch(schedule)
    try:
        agents = []
        for sp in (spec0, spec1):
            a = build(sp)
            agents.append(timed(a) if callable(a) else a)
        env = make("kaggriculture", configuration={"seed": seed}, debug=False)
        env.run(agents)
    finally:
        restore()
    final = env.steps[-1]
    out = {"seed": seed, "schedule": schedule_name,
           "shops": list(env.state[0]["observation"]["town"]["unlocked_shops"]),
           "rewards": [float(final[0]["reward"]), float(final[1]["reward"])],
           "players": []}
    for p in range(2):
        rec = sales.get(p, {"rev": {}, "units": {}, "spend": {}})
        a = agents[p]
        out["players"].append({"rev": rec["rev"], "units": rec["units"], "spend": rec["spend"],
                               "latency": _lat(a.times) if hasattr(a, "times") else None})
    return out


def _job(args):
    cand, opp, sched, seed, swap = args
    if swap:
        r = play(opp, cand, sched, seed)
        me, op = 1, 0
    else:
        r = play(cand, opp, sched, seed)
        me, op = 0, 1
    return {"schedule": sched, "seed": seed, "seat": me,
            "me": r["rewards"][me], "opp": r["rewards"][op],
            "me_rev": r["players"][me]["rev"], "opp_rev": r["players"][op]["rev"],
            "me_units": r["players"][me]["units"], "opp_units": r["players"][op]["units"],
            "me_lat": r["players"][me]["latency"], "shops": r["shops"]}


def run_matrix(cand, opponents, schedules=None, seeds=(1000,), workers=6, out=None, label="cand"):
    """opponents: dict name -> spec. Both seats. Returns nested results + summary."""
    schedules = schedules or SCHEDULE_NAMES
    jobs, keys = [], []
    for oname, ospec in opponents.items():
        for s in schedules:
            for sd in seeds:
                for swap in (False, True):
                    jobs.append((cand, ospec, s, sd, swap))
                    keys.append(oname)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            res = list(ex.map(_job, jobs))
    else:
        res = [_job(j) for j in jobs]
    by_opp = {}
    for k, r in zip(keys, res):
        by_opp.setdefault(k, []).append(r)
    summary = {}
    for oname, rs in by_opp.items():
        summary[oname] = {
            "me_mean": statistics.mean(r["me"] for r in rs),
            "opp_mean": statistics.mean(r["opp"] for r in rs),
            "margin": statistics.mean(r["me"] - r["opp"] for r in rs),
            "wins": sum(1 for r in rs if r["me"] > r["opp"]), "n": len(rs),
            "me_min": min(r["me"] for r in rs),
            "lat_max": max((r["me_lat"] or {}).get("max", 0) for r in rs),
            "lat_p99": max((r["me_lat"] or {}).get("p99", 0) for r in rs),
            "by_schedule": {s: statistics.mean(r["me"] for r in rs if r["schedule"] == s) for s in schedules},
            "by_schedule_margin": {s: statistics.mean(r["me"] - r["opp"] for r in rs if r["schedule"] == s) for s in schedules},
        }
    result = {"label": label, "cand": repr(cand), "summary": summary, "games": by_opp}
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(result, f, default=str)
    return result


def print_summary(result):
    print(f"== {result['label']} ==")
    for oname, s in result["summary"].items():
        print(f"  vs {oname:8s}  me={s['me_mean']:8.0f} opp={s['opp_mean']:8.0f} margin={s['margin']:+8.0f} "
              f"wins={s['wins']}/{s['n']} min={s['me_min']:.0f} lat_max={s['lat_max']*1000:.0f}ms p99={s['lat_p99']*1000:.0f}ms")
        print("     by schedule: " + "  ".join(f"{k}={v:.0f}" for k, v in s["by_schedule"].items()))


STD_OPPONENTS = {
    "sol5": ("sol5", None),
    "gideon": ("sol5p", {"n_cows": 6, "n_sheep": 10}),
    "pass": "pass",
}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="sol5", help="sol5 | gideon | file:/abs/path.py:builder")
    ap.add_argument("--opps", default="sol5,gideon,pass,mirror")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", default="1000")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    def spec_of(s):
        if s in STD_OPPONENTS:
            return STD_OPPONENTS[s]
        if s.startswith("file:"):
            _, path, fn = s.split(":")
            return ("file", path, fn, [])
        raise ValueError(s)
    cand = spec_of(a.cand)
    opps = {}
    for o in a.opps.split(","):
        opps[o] = cand if o == "mirror" else spec_of(o)
    seeds = [int(x) for x in a.seeds.split(",")]
    out = a.out or os.path.join(RESULTS, f"{a.cand.replace('/', '_').replace(':', '_')}.json")
    t = time.time()
    r = run_matrix(cand, opps, seeds=seeds, workers=a.workers, out=out, label=a.cand)
    print_summary(r)
    print(f"saved {out}  ({time.time()-t:.0f}s)")
