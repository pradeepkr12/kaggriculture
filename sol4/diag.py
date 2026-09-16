"""Single-game diagnostics for a sol4 agent: per-day timeline, fed/cared %, escapes,
shed overflow, labor mix, and per-product realized revenue (from money deltas
attributed to SELL orders at the live price).

Usage: python diag.py [seed] [opponent]   (opponent: pass|starter|sol3|melon|self)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kaggle_environments import make
from farmlib import build_agent, SEED_VEC, market_price, MARKET_PARAMS, ANIMALS, CROPS

SOL3_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sol3")


def make_opponent(name):
    if name in ("pass", "starter", "random"):
        return name
    if name == "sol3":
        sys.path.insert(0, SOL3_DIR)
        import importlib
        m = importlib.import_module("farmlib") if False else None
        spec = importlib.util.spec_from_file_location("sol3farmlib", os.path.join(SOL3_DIR, "farmlib.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod.build_agent([3.25, 0, 0, 0.56, 4.62, 4.52, 1.28, 42, 0.71])
    if name == "melon":
        import importlib.util
        spec = importlib.util.spec_from_file_location("sol3farmlib", os.path.join(SOL3_DIR, "farmlib.py"))
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod.build_agent([6, 0, 0, 0, 0, 3, 0, 16, 0.30])
    if name == "self":
        return build_agent(SEED_VEC)
    raise ValueError(name)


def run(vec=SEED_VEC, seed=1, opp="pass", verbose=True):
    import importlib.util  # noqa
    agent = build_agent(vec)
    env = make("kaggriculture", configuration={"seed": seed}, debug=False)
    env.run([agent, make_opponent(opp)])
    steps = env.steps
    final = steps[-1]
    me, op = final[0]["reward"], final[1]["reward"]

    # per-product revenue: attribute money delta of each step to my SELL orders (lockstep approx)
    rev = {}
    units_sold = {}
    escapes = 0
    overflow_lost = 0
    prev_animals = None
    day_rows = []
    for i in range(len(steps) - 1):
        # steps[i+1]['action'] is the action chosen from observation steps[i]
        obs = steps[i][0]["observation"]
        act = steps[i + 1][0]["action"] or {}
        nxt = steps[i + 1][0]["observation"]
        price = obs["market"]["prices"]
        for o in act.get("market", []):
            if o and o[0] == "SELL":
                q = int(o[2]) if len(o) > 2 else 1
                q = min(q, obs["private"]["shed"].get(o[1], 0))
                rev[o[1]] = rev.get(o[1], 0) + q * price[o[1]]
                units_sold[o[1]] = units_sold.get(o[1], 0) + q
        # escapes / overflow at day boundary
        if obs["hour"] == 23:
            farm = obs["farms"][0]
            n_anim = sum(1 for row in farm["tiles"] for t in row if isinstance(t, dict) and "animal" in t)
            nfarm = nxt["farms"][0]
            n_anim2 = sum(1 for row in nfarm["tiles"] for t in row if isinstance(t, dict) and "animal" in t)
            escapes += max(0, n_anim - n_anim2)
            shed_tot = sum(obs["private"]["shed"].values())
            carried = sum(sum(inv.values()) for inv in obs["private"]["inventories"])
            # after this step's actions+market, remaining carried drop into shed (cap 100)
            shed_after = sum(nxt["private"]["shed"].values())
            # approx loss: what we had minus what we kept minus what sold this step
            sold_now = sum(min(int(o[2]), obs["private"]["shed"].get(o[1], 0)) for o in act.get("market", []) if o and o[0] == "SELL")
            lost = max(0, shed_tot + carried - sold_now - shed_after)
            overflow_lost += lost
    # per-day rows from agent.stats
    st = agent.stats["days"]
    for d in sorted(st):
        r = st[d]
        n = max(1, r["animals"])
        day_rows.append((d, r["money_h0"], r["animals"], r["fed"] / n if r["animals"] else 1.0,
                         r["cared"] / n if r["animals"] else 1.0, r["moves"], r["actions"], r["idle"]))

    # final composition
    farm = final[0]["observation"]["farms"][0]
    comp = {}
    for row in farm["tiles"]:
        for t in row:
            if t == "LOCKED": k = "LOCKED"
            elif t is None: k = "empty"
            elif t.get("kind") == "PLANT": k = "crop_" + t["crop"]
            elif "animal" in t: k = "animal_" + t["animal"]
            else: k = "struct_" + str(t.get("kind"))
            comp[k] = comp.get(k, 0) + 1

    if verbose:
        print(f"seed={seed} opp={opp}  ME={me:.0f}  OPP={op:.0f}")
        print(" day  money_h0  anim  fed%  cared%  moves acts idle")
        for (d, m, a, f, c, mv, ac, idl) in day_rows:
            print(f"  {d:2d}  {m:8.0f}  {a:4d}  {100*f:4.0f}  {100*c:5.0f}  {mv:5d} {ac:4d} {idl:4d}")
        print(f" escapes={escapes}  overflow_lost~{overflow_lost}  plant_blocked={agent.stats['plant_blocked']}")
        print(" revenue by product:")
        tot = sum(rev.values()) or 1
        for k, v in sorted(rev.items(), key=lambda kv: -kv[1]):
            u = units_sold[k]
            print(f"   {k:11s} {u:5d}u  ${v:8.0f}  avg ${v/max(1,u):6.1f} ({100*v/max(1,u)/MARKET_PARAMS[k]['base']:3.0f}% base)  {100*v/tot:3.0f}%")
        print(" final tiles:", dict(sorted(comp.items(), key=lambda kv: -kv[1])))
        mk = final[0]["observation"]["market"]
        print(" final prices:", {k: mk["prices"][k] for k in mk["prices"]})
    return {"me": me, "opp": op, "rev": rev, "escapes": escapes, "overflow": overflow_lost, "days": day_rows}


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    opp = sys.argv[2] if len(sys.argv) > 2 else "pass"
    run(seed=seed, opp=opp)
