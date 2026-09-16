"""Planner + Hungarian labor assignment (farmlib_ph.py = labor/farmlib_labor.py + planner hooks)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import farmlib_ph as FH
import planner

def build_agent(verbose=False):
    P = FH.vec_to_params(FH.SEED_VEC)
    P["planner"] = True
    P["hands"] = lambda d: 8 if d >= planner.LAST_DAY else (6 if d <= 3 else (9 if d <= 7 else 11))
    base = FH.build_agent(P, hungarian=True)
    pl = planner.Planner(P, base.mem, verbose=verbose)
    P["sell_override"] = pl.sell_override
    def agent(obs):
        pl.infer_flows(obs)
        if obs["day"] != pl.day:
            pl.day = obs["day"]
            pl.plan_day(obs)
        act = base(obs)
        pl.note_orders(act.get("market", []))
        return act
    agent.planner = pl; agent.stats = base.stats
    return agent
