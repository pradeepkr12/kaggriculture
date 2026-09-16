"""Self-play arena: the Monte-Carlo return estimator that ES/CEM optimizes.

Because the market is shared, an agent's value is only meaningful *relative to an
opponent*. So the primitive is a head-to-head duel (played on both seats to
cancel first-mover asymmetry), and the optimization signal is the average
coin margin (my_reward - opp_reward) against a pool of opponents.

Agents are passed as *specs* (a builtin name string, or a parameter vector) so
they are picklable across worker processes; the closure is built inside workers.
"""
import os
import sys
import statistics
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaggle_environments import make  # noqa: E402
from farmlib import build_agent, SEED_VEC  # noqa: E402

DEFAULT_WORKERS = min(14, os.cpu_count() or 14)


SOL3_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sol3")
_SOL3 = {}


def _sol3_build_agent():
    if "mod" not in _SOL3:
        import importlib.util
        spec = importlib.util.spec_from_file_location("sol3farmlib", os.path.join(SOL3_DIR, "farmlib.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _SOL3["mod"] = mod
    return _SOL3["mod"].build_agent


# named reference opponents (sol3 parametrization)
REF = {
    "sol3": ("sol3", [3.25, 0, 0, 0.56, 4.62, 4.52, 1.28, 42, 0.71]),
    "melon": ("sol3", [6, 0, 0, 0, 0, 3, 0, 16, 0.30]),
}


def _resolve(spec):
    """spec: builtin name | 'sol3' | 'melon' | ('sol3', vec) | sol4 vector."""
    if isinstance(spec, str):
        if spec in REF:
            spec = REF[spec]
        else:
            return spec
    if isinstance(spec, tuple) and spec and spec[0] == "sol3":
        return _sol3_build_agent()(list(spec[1]))
    return build_agent(list(spec))


def play(spec0, spec1, seed):
    env = make("kaggriculture", configuration={"seed": seed}, debug=False)
    env.run([_resolve(spec0), _resolve(spec1)])
    f = env.steps[-1]
    return float(f[0]["reward"]), float(f[1]["reward"])


def _match_job(args):
    spec_a, spec_b, seed, swap = args
    if swap:
        rb, ra = play(spec_b, spec_a, seed)
    else:
        ra, rb = play(spec_a, spec_b, seed)
    return ra, rb


def _run_jobs(jobs, workers):
    if workers and workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(_match_job, jobs))
    return [_match_job(j) for j in jobs]


def duel(spec_a, spec_b, seeds, workers=DEFAULT_WORKERS):
    """Play spec_a vs spec_b over seeds, both seats. Return aggregate stats."""
    jobs = []
    for s in seeds:
        jobs.append((spec_a, spec_b, s, False))
        jobs.append((spec_a, spec_b, s, True))
    res = _run_jobs(jobs, workers)
    a = [r[0] for r in res]
    b = [r[1] for r in res]
    wins = sum(1 for x, y in res if x > y)
    losses = sum(1 for x, y in res if x < y)
    ties = len(res) - wins - losses
    return {
        "a_mean": statistics.mean(a), "b_mean": statistics.mean(b),
        "margin": statistics.mean(x - y for x, y in res),
        "wins": wins, "losses": losses, "ties": ties, "n": len(res),
    }


def fitness(spec, opponents, seeds, workers=DEFAULT_WORKERS):
    """Average coin margin of `spec` vs a pool of opponents (both seats).

    This is the RL return: expected competitive margin under self-play.
    """
    jobs = []
    for opp in opponents:
        for s in seeds:
            jobs.append((spec, opp, s, False))
            jobs.append((spec, opp, s, True))
    res = _run_jobs(jobs, workers)
    margins = [x - y for x, y in res]
    wins = sum(1 for x, y in res if x > y)
    return {
        "margin": statistics.mean(margins),
        "my_mean": statistics.mean(x for x, y in res),
        "winrate": wins / len(res),
        "n": len(res),
    }


def round_robin(named_specs, seeds, workers=DEFAULT_WORKERS):
    """named_specs: dict name->spec. Return per-agent win/margin vs the field."""
    names = list(named_specs)
    stats = {nm: {"wins": 0, "losses": 0, "ties": 0, "margin_sum": 0.0, "n": 0,
                  "score_sum": 0.0} for nm in names}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            na, nb = names[i], names[j]
            d = duel(named_specs[na], named_specs[nb], seeds, workers)
            stats[na]["wins"] += d["wins"]; stats[na]["losses"] += d["losses"]; stats[na]["ties"] += d["ties"]
            stats[nb]["wins"] += d["losses"]; stats[nb]["losses"] += d["wins"]; stats[nb]["ties"] += d["ties"]
            stats[na]["margin_sum"] += d["margin"] * d["n"]; stats[nb]["margin_sum"] -= d["margin"] * d["n"]
            stats[na]["score_sum"] += d["a_mean"] * d["n"]; stats[nb]["score_sum"] += d["b_mean"] * d["n"]
            stats[na]["n"] += d["n"]; stats[nb]["n"] += d["n"]
    rows = []
    for nm in names:
        s = stats[nm]
        g = s["wins"] + s["losses"] + s["ties"]
        rows.append({
            "name": nm, "winrate": s["wins"] / max(1, g),
            "wins": s["wins"], "losses": s["losses"], "ties": s["ties"],
            "avg_margin": s["margin_sum"] / max(1, s["n"]),
            "avg_score": s["score_sum"] / max(1, s["n"]),
        })
    rows.sort(key=lambda r: -r["winrate"])
    return rows


# =============================================================================
# sol6: forced-shop-schedule arena (PLAN section 5 / brief step A)
# =============================================================================
import importlib.util
import random as _random
import time as _time

SOL5_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sol5")
SHOP_NAMES = ["BAKERY", "PIZZA_SHOP", "BRUNCH_SPOT", "YARN_STORE",
              "ICE_CREAM_SHOP", "PET_CAFE", "SMOOTHIE_SHOP", "FARMERS_MARKET"]

# Shops unlock at end of days 2,5,...,23 -> visible as next_day 3,6,...,24.
NAMED_SCHEDULES = {
    "milk_starved":  {3: "BAKERY", 6: "BAKERY", 9: "BRUNCH_SPOT", 12: "FARMERS_MARKET",
                      15: "YARN_STORE", 18: "BAKERY", 21: "SMOOTHIE_SHOP", 24: "PET_CAFE"},
    "yarnless_3milk": {3: "PET_CAFE", 6: "BAKERY", 9: "PIZZA_SHOP", 12: "SMOOTHIE_SHOP",
                       15: "FARMERS_MARKET", 18: "PET_CAFE", 21: "FARMERS_MARKET", 24: "PIZZA_SHOP"},
    "yarn3":         {3: "FARMERS_MARKET", 6: "YARN_STORE", 9: "YARN_STORE", 12: "YARN_STORE",
                      15: "SMOOTHIE_SHOP", 18: "SMOOTHIE_SHOP", 21: "PET_CAFE", 24: "FARMERS_MARKET"},
    "milk_rich":     {3: "PIZZA_SHOP", 6: "ICE_CREAM_SHOP", 9: "SMOOTHIE_SHOP", 12: "PIZZA_SHOP",
                      15: "ICE_CREAM_SHOP", 18: "SMOOTHIE_SHOP", 21: "PIZZA_SHOP", 24: "ICE_CREAM_SHOP"},
    "bakery_heavy":  {3: "BAKERY", 6: "BRUNCH_SPOT", 9: "BAKERY", 12: "FARMERS_MARKET",
                      15: "BAKERY", 18: "BRUNCH_SPOT", 21: "PET_CAFE", 24: "BAKERY"},
}
NAMED_5 = ["milk_starved", "yarnless_3milk", "yarn3", "milk_rich", "bakery_heavy"]


def random_schedule(k):
    rng = _random.Random(7000 + k)
    return {d: rng.choice(SHOP_NAMES) for d in (3, 6, 9, 12, 15, 18, 21, 24)}


def get_schedule(spec):
    if spec is None:
        return None
    if isinstance(spec, str):
        if spec in NAMED_SCHEDULES:
            return NAMED_SCHEDULES[spec]
        if spec.startswith("random_"):
            return random_schedule(int(spec.split("_")[1]))
        raise ValueError(f"unknown schedule {spec}")
    return {int(k): v for k, v in spec.items()}


def _load_sol5():
    spec = importlib.util.spec_from_file_location("sol5farmlib", os.path.join(SOL5_DIR, "farmlib.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_side(spec):
    """Return (callable, agent_obj_or_None). agent_obj exposes .stats."""
    if spec in ("pass", "starter", "random"):
        return spec, None
    if spec in ("sol6", "self"):
        a = build_agent(list(SEED_VEC)); return a, a
    if spec == "sol5":
        m = _load_sol5(); a = m.build_agent(list(m.SEED_VEC)); return a, a
    if spec == "gideon":
        m = _load_sol5(); v = list(m.SEED_VEC); v[1] = 6; v[2] = 10
        a = m.build_agent(v); return a, a
    if isinstance(spec, (list, tuple)):
        a = build_agent(list(spec)); return a, a
    return spec, None


def _revenue_from_steps(steps, player):
    """Realized SELL revenue per product = units x decision price (prev step's
    market price the agent saw)."""
    rev = {}
    for i in range(1, len(steps)):
        prices = (steps[i - 1][0]["observation"].get("market", {}) or {}).get("prices", {}) or {}
        act = steps[i][player].get("action") or {}
        for o in (act.get("market") or []):
            if isinstance(o, list) and len(o) >= 3 and o[0] == "SELL":
                item = o[1]
                rev[item] = rev.get(item, 0.0) + o[2] * prices.get(item, 0)
    return rev


def _stats_summary(agent_obj):
    if agent_obj is None or not hasattr(agent_obj, "stats"):
        return None
    s = agent_obj.stats
    days = s["days"]
    need = sum(d.get("need_feed", 0) for d in days.values())
    fedn = sum(d.get("fed_need", 0) for d in days.values())
    idle = sum(d.get("idle", 0) for d in days.values())
    moves = sum(d.get("moves", 0) for d in days.values())
    actions = sum(d.get("actions", 0) for d in days.values())
    unit_turns = idle + moves + actions
    animals_by_day = {int(k): d.get("animals", 0) for k, d in days.items()}
    return {
        "fed_pct": (fedn / need) if need else 1.0,
        "escapes": s.get("escapes", 0),
        "escapes_intended": s.get("escapes_intended", 0),
        "idle_unit_turns": idle,
        "walking_share": (moves / unit_turns) if unit_turns else 0.0,
        "animals_by_day": animals_by_day,
        "max_animals": max(animals_by_day.values()) if animals_by_day else 0,
    }


def play(spec0, spec1, seed, schedule=None):
    """Full instrumented game. schedule: name | dict{day:shop} | None (natural)."""
    sched = get_schedule(schedule)
    import kaggle_environments.envs.kaggriculture.kaggriculture as K
    orig = K._end_of_day
    if sched is not None:
        def wrap(state, env, day):
            town = state[0].observation.town
            n = len(town["unlocked_shops"])
            orig(state, env, day)
            if len(town["unlocked_shops"]) > n and (day + 1) in sched:
                town["unlocked_shops"][-1] = sched[day + 1]
        K._end_of_day = wrap
    try:
        c0, a0 = _build_side(spec0)
        c1, a1 = _build_side(spec1)
        lat = [0.0, 0.0]

        def timed(callable_, idx):
            if not callable(callable_):
                return callable_
            def f(obs):
                t = _time.time(); r = callable_(obs); lat[idx] = max(lat[idx], _time.time() - t)
                return r
            return f
        env = make("kaggriculture", configuration={"seed": seed}, debug=False)
        env.run([timed(c0, 0), timed(c1, 1)])
        steps = env.steps
        r0 = float(steps[-1][0]["reward"]); r1 = float(steps[-1][1]["reward"])
        return {
            "scores": [r0, r1],
            "revenue": [_revenue_from_steps(steps, 0), _revenue_from_steps(steps, 1)],
            "stats": [_stats_summary(a0), _stats_summary(a1)],
            "latency": lat,
            "max_orders": max((len((steps[i][p].get("action") or {}).get("market") or [])
                               for i in range(len(steps)) for p in (0, 1)), default=0),
        }
    finally:
        K._end_of_day = orig


def _fjob(args):
    s0, s1, seed, sched, swap = args
    if swap:
        res = play(s1, s0, seed, sched)
        return {"scores": res["scores"][::-1], "revenue": res["revenue"][::-1],
                "stats": res["stats"][::-1], "latency": res["latency"][::-1],
                "max_orders": res["max_orders"]}
    return play(s0, s1, seed, sched)


def run_matrix(me, opponents, schedules, seeds, workers=None, both_seats=True):
    """me vs each opponent over schedules x seeds x seats. Returns list of records."""
    workers = workers or min(10, DEFAULT_WORKERS)
    jobs = []
    for opp in opponents:
        for sched in schedules:
            for seed in seeds:
                jobs.append((me, opp, seed, sched, False))
                if both_seats:
                    jobs.append((me, opp, seed, sched, True))
    results = _run_jobs2(jobs, workers)
    records = []
    for (s0, s1, seed, sched, swap), res in zip(jobs, results):
        records.append({
            "me": s0 if not swap else s0, "opp": s1, "schedule": sched, "seed": seed,
            "seat": 1 if swap else 0,
            "my_score": res["scores"][0], "opp_score": res["scores"][1],
            "my_revenue": res["revenue"][0], "opp_revenue": res["revenue"][1],
            "my_stats": res["stats"][0], "latency": max(res["latency"]),
            "max_orders": res["max_orders"],
        })
    return records


def _run_jobs2(jobs, workers):
    if workers and workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(_fjob, jobs))
    return [_fjob(j) for j in jobs]
