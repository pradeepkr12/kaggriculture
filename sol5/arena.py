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
from farmlib import build_agent  # noqa: E402

DEFAULT_WORKERS = max(1, (os.cpu_count() or 2) - 2)


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
