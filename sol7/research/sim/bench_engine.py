"""Task 1: raw engine throughput (interpreter steps/s) + fastsim cross-validation
against fresh engine trajectories (PASS and BUSY policies, seed 1).

Workloads:
  pass   : both players PASS every step, no market orders
  busy   : scripted wheat loop keeping 11 units busy (WATER/HARVEST/PLANT/DIG/moves)
           plus SELL/BUY_SEED orders each step and 10 HIREs at hour 0 (both players)
  replay : the recorded top-player actions from /private/tmp/109564916.json (seed
           1296760754; the engine reproduces the recorded final money exactly)

Timings: 'direct' = kaggriculture.interpreter(state, env) called in place on the
structified state (no structify/deepcopy/schema overhead); 'env_step' = env.step().

Usage: python bench_engine.py [--repeats 3] [--json out.json]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fastsim  # noqa: E402
import validate_replay  # noqa: E402

from kaggle_environments import make  # noqa: E402
from kaggle_environments.envs.kaggriculture import kaggriculture as K  # noqa: E402

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
BUSY_ACTIONS_PATH = os.path.join(RESULTS_DIR, "busy_actions.json")
N_STEPS = 719  # interpreter calls per game (steps[0] is the initial state)

PASS = {"farmer": ["PASS"], "hands": [], "market": []}

# 11 home tiles in the NW quadrant for farmer + 10 hands
HOMES = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (0, 2)]
N_HANDS = 10


def busy_policy(obs, player):
    farm = obs["farms"][player]
    priv = obs["private"]
    day, hour = obs["day"], obs["hour"]
    tiles = farm["tiles"]
    units = [farm["farmer"]] + list(farm["hands"])
    seeds_left = priv["seeds"].get("WHEAT", 0)
    acts = []
    for k, pos in enumerate(units):
        if k >= len(HOMES):
            acts.append(["PASS"])
            continue
        hx, hy = HOMES[k]
        x, y = pos
        if x != hx:
            acts.append(["WEST" if hx < x else "EAST"])
            continue
        if y != hy:
            acts.append(["NORTH" if hy < y else "SOUTH"])
            continue
        t = tiles[hy][hx]
        if t is None:
            if seeds_left > 0:
                seeds_left -= 1
                acts.append(["PLANT", "WHEAT"])
            else:
                acts.append(["PASS"])
        elif isinstance(t, dict) and t.get("kind") == "PLANT":
            if not t["watered_today"]:
                acts.append(["WATER"])
            elif day - t["planted_day"] >= 4 and t["yield_units"] > 0:
                acts.append(["HARVEST"])
            else:
                acts.append(["PASS"])
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            acts.append(["DIG"])
        else:
            acts.append(["PASS"])
    market = []
    shed_wheat = priv["shed"].get("WHEAT", 0)
    if shed_wheat > 0:
        market.append(["SELL", "WHEAT", shed_wheat])
    if priv["seeds"].get("WHEAT", 0) < len(HOMES):
        market.append(["BUY_SEED", "WHEAT", len(HOMES) - priv["seeds"].get("WHEAT", 0)])
    if hour == 0 and farm["money"] > 500:
        market.extend([["HIRE"]] * N_HANDS)
    return {"farmer": acts[0], "hands": acts[1:], "market": market}


def snapshot(state):
    """Plain-dict copy of the structified state list."""
    return json.loads(json.dumps(state))


def generate_trajectory(policy, seed):
    """Run the engine (direct interpreter) with `policy(obs, player)`; return a
    replay-like dict {'steps': [...], 'info': {'seed': seed}} plus the action list."""
    env = make("kaggriculture", configuration={"seed": seed})
    state = env.state
    steps = [snapshot(state)]
    actions = [None]
    for i in range(N_STEPS):
        obs = steps[-1]
        acts = []
        for p in range(2):
            o = dict(obs[0]["observation"])
            o["private"] = obs[p]["observation"]["private"]
            acts.append(policy(o, p) if policy is not None else PASS)
        for p in range(2):
            state[p].action = acts[p]
        state[0].observation.step = i
        K.interpreter(state, env)
        snap = snapshot(state)
        for p in range(2):
            snap[p]["action"] = acts[p]
            snap[p]["observation"]["step"] = i + 1
        steps.append(snap)
        actions.append(acts)
    return {"steps": steps, "info": {"seed": seed}}, actions


def time_direct(actions, seed, repeats):
    """Time N_STEPS in-place interpreter calls; actions[i] applied at step i-1."""
    times = []
    for _ in range(repeats):
        env = make("kaggriculture", configuration={"seed": seed})
        state = env.state
        interp = K.interpreter
        t0 = time.perf_counter()
        for i in range(N_STEPS):
            a = actions[i + 1]
            state[0].action = a[0]
            state[1].action = a[1]
            state[0].observation.step = i
            interp(state, env)
        times.append(time.perf_counter() - t0)
        final = [state[p].observation.farms[p]["money"] for p in range(2)]
    return times, final


def time_env_step(actions, seed, repeats):
    times = []
    for _ in range(repeats):
        env = make("kaggriculture", configuration={"seed": seed})
        t0 = time.perf_counter()
        for i in range(N_STEPS):
            env.step(actions[i + 1])
        times.append(time.perf_counter() - t0)
        final = [env.state[p].observation.farms[p]["money"] for p in range(2)]
    return times, final


def summarize(times, n_steps=N_STEPS):
    best = min(times)
    med = sorted(times)[len(times) // 2]
    return {"runs": times, "best_s": best, "median_s": med, "best_steps_per_s": n_steps / best,
            "median_steps_per_s": n_steps / med, "n_steps": n_steps}


def cross_validate(traj, label):
    out = {}
    for mode in ("rng", "patch"):
        r = validate_replay.run(traj, mode, verbose=False)
        out[mode] = {k: r[k] for k in ("exact_match", "divergent_steps", "first_divergence", "final_money_sim",
                                       "final_money_recorded") if k in r}
        if mode == "patch":
            out[mode]["weed_patches_tiles"] = r["weed_patches_tiles"]
            out[mode]["weed_patch_days"] = r["weed_patch_days"]
        print(f"[xval {label} {mode}] exact={r['exact_match']} div_steps={r['divergent_steps']}"
              + (f" weed_patches={r['weed_patches_tiles']}" if mode == "patch" else ""))
    return out


def main(argv=None):
    argv = list(argv or [])
    repeats = 3
    out = os.path.join(RESULTS_DIR, "bench_engine.json")
    while argv:
        a = argv.pop(0)
        if a == "--repeats":
            repeats = int(argv.pop(0))
        elif a == "--json":
            out = argv.pop(0)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    res = {"n_steps_per_game": N_STEPS, "repeats": repeats, "python": sys.version.split()[0], "workloads": {}}

    t0 = time.perf_counter()
    make("kaggriculture", configuration={"seed": 1})
    res["make_env_seconds"] = time.perf_counter() - t0

    # --- PASS
    traj, actions = generate_trajectory(None, seed=1)
    w = {"description": "both players PASS, no market orders", "seed": 1}
    w["fastsim_cross_validation"] = cross_validate(traj, "pass")
    w["direct"], w["final_money"] = (lambda t: (summarize(t[0]), t[1]))(time_direct(actions, 1, repeats))
    w["env_step"], _ = (lambda t: (summarize(t[0]), t[1]))(time_env_step(actions, 1, repeats))
    res["workloads"]["pass"] = w
    print(f"[engine pass] direct {w['direct']['best_steps_per_s']:.0f} steps/s ({w['direct']['best_s']:.2f}s/game); "
          f"env.step {w['env_step']['best_steps_per_s']:.0f} steps/s ({w['env_step']['best_s']:.2f}s/game)")

    # --- BUSY
    traj, actions = generate_trajectory(busy_policy, seed=1)
    with open(BUSY_ACTIONS_PATH, "w") as f:
        json.dump({"seed": 1, "actions": actions}, f)
    st = traj["steps"]
    n_units = [1 + len(st[i][0]["observation"]["farms"][p]["hands"]) for i in range(1, len(st)) for p in range(2)]
    n_orders = [len(a[p]["market"]) for a in actions[1:] for p in range(2)]
    w = {"description": "scripted wheat loop: 11 units WATER/HARVEST/PLANT + SELL/BUY_SEED each step + 10 HIRE at hour 0",
         "seed": 1, "mean_units_per_farm": sum(n_units) / len(n_units), "mean_market_orders_per_player_step": sum(n_orders) / len(n_orders),
         "final_money_engine": [st[-1][0]["observation"]["farms"][p]["money"] for p in range(2)]}
    w["fastsim_cross_validation"] = cross_validate(traj, "busy")
    w["direct"], _ = (lambda t: (summarize(t[0]), t[1]))(time_direct(actions, 1, repeats))
    w["env_step"], _ = (lambda t: (summarize(t[0]), t[1]))(time_env_step(actions, 1, repeats))
    res["workloads"]["busy"] = w
    print(f"[engine busy] units/farm={w['mean_units_per_farm']:.1f} direct {w['direct']['best_steps_per_s']:.0f} steps/s "
          f"({w['direct']['best_s']:.2f}s/game); env.step {w['env_step']['best_steps_per_s']:.0f} steps/s")

    # --- REPLAY workload
    rep = validate_replay.load_replay()
    seed = rep["info"]["seed"]
    actions = [None] + [[rep["steps"][i][p]["action"] for p in range(2)] for i in range(1, len(rep["steps"]))]
    w = {"description": "recorded top-player actions from replay 109564916 (mean 9.4 units/farm)", "seed": seed,
         "replay": validate_replay.REPLAY_DEFAULT}
    times, final = time_direct(actions, seed, repeats)
    w["direct"] = summarize(times)
    w["final_money_engine"] = final
    w["final_money_recorded"] = [rep["steps"][-1][0]["observation"]["farms"][p]["money"] for p in range(2)]
    w["engine_reproduces_recorded_final_money"] = (final == w["final_money_recorded"])
    times, _ = time_env_step(actions, seed, repeats)
    w["env_step"] = summarize(times)
    res["workloads"]["replay"] = w
    print(f"[engine replay] direct {w['direct']['best_steps_per_s']:.0f} steps/s ({w['direct']['best_s']:.2f}s/game); "
          f"env.step {w['env_step']['best_steps_per_s']:.0f} steps/s; reproduces final money: {w['engine_reproduces_recorded_final_money']}")

    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    return res


if __name__ == "__main__":
    main(sys.argv[1:])
