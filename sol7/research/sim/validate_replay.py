"""Validate fastsim step-for-step against a recorded kaggriculture replay.

steps[i][p]['action'] is the action applied to the observation at steps[i-1]
to produce steps[i]['observation'] (the interpreter sees step = i-1).

Two modes:
  * rng   : weed_seed = replay info['seed'] -> engine RNG replicated bit-exact
            (weeds + shop draw). Expect zero divergences.
  * patch : weed_seed = None (planning mode: no weeds); after each end-of-day
            step we copy WEED tiles from the recorded state and count patches;
            shop unlocks are forced from the recorded town list.

Usage:
  python validate_replay.py [/private/tmp/109564916.json] [--mode rng|patch|both] [--json out.json]
"""
import json
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fastsim  # noqa: E402

REPLAY_DEFAULT = "/private/tmp/109564916.json"


def load_replay(path=REPLAY_DEFAULT):
    with open(path) as f:
        return json.load(f)


def recorded_shops(steps):
    """Final unlocked shop list from the last recorded step (the forced schedule)."""
    return list(steps[-1][0]["observation"]["town"]["unlocked_shops"])


def diff_dicts(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: missing in fastsim (rec={b[k]!r})")
            elif k not in b:
                out.append(f"{path}.{k}: extra in fastsim (sim={a[k]!r})")
            else:
                out.extend(diff_dicts(a[k], b[k], f"{path}.{k}"))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: len sim={len(a)} rec={len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(diff_dicts(x, y, f"{path}[{i}]"))
    else:
        if a != b:
            out.append(f"{path}: sim={a!r} rec={b!r}")
    return out


def compare_step(sim, rec_step, ignore_weeds=False):
    """Return list of difference strings between sim state and recorded step."""
    diffs = []
    obs0 = rec_step[0]["observation"]
    for pid in range(2):
        sf = sim.farm_obs(pid)
        rf = obs0["farms"][pid]
        if ignore_weeds:
            # ignore tiles where the record has a WEED and sim has EMPTY (weed spawn)
            for y in range(fastsim.BOARD):
                for x in range(fastsim.BOARD):
                    rt = rf["tiles"][y][x]
                    if isinstance(rt, dict) and rt.get("kind") == "WEED" and sf["tiles"][y][x] is None:
                        sf["tiles"][y][x] = {"kind": "WEED"}
        diffs.extend(diff_dicts(sf, rf, f"farms[{pid}]"))
        sp = sim.private_obs(pid)
        rp = rec_step[pid]["observation"]["private"]
        diffs.extend(diff_dicts(sp, rp, f"private[{pid}]"))
    diffs.extend(diff_dicts(sim.market_obs(), obs0["market"], "market"))
    diffs.extend(diff_dicts(sim.town_obs(), obs0["town"], "town"))
    return diffs


def run(replay, mode, max_report=5, verbose=True):
    steps = replay["steps"]
    seed = replay["info"]["seed"]
    n = len(steps)
    s0 = steps[0]
    obs0 = s0[0]["observation"]
    privates = [s0[p]["observation"]["private"] for p in range(2)]
    if mode == "rng":
        sim = fastsim.FastState.from_obs(obs0["farms"], obs0["market"], obs0["town"], privates, 0,
                                         forced_shops=None, weed_seed=seed)
    else:
        sim = fastsim.FastState.from_obs(obs0["farms"], obs0["market"], obs0["town"], privates, 0,
                                         forced_shops=recorded_shops(steps), weed_seed=None)
    first_div = None
    n_div_steps = 0
    reports = []
    patched_total = 0
    patch_days = 0
    t0 = time.perf_counter()
    for i in range(1, n):
        actions = [steps[i][p]["action"] for p in range(2)]
        sim.apply(actions)
        assert sim.step == i
        if mode == "patch" and i % fastsim.TPD == 0:
            # weeds spawned in the end-of-day that produced this observation
            k = sim.patch_weeds_from(steps[i][0]["observation"]["farms"])
            patched_total += k
            if k:
                patch_days += 1
        diffs = compare_step(sim, steps[i])
        if diffs:
            n_div_steps += 1
            if first_div is None:
                first_div = {"step": i, "diffs": diffs[:20]}
            if len(reports) < max_report:
                reports.append({"step": i, "n_diffs": len(diffs), "diffs": diffs[:10]})
            if verbose and len(reports) <= max_report:
                print(f"[{mode}] step {i}: {len(diffs)} diffs; first: {diffs[:3]}")
    elapsed = time.perf_counter() - t0
    result = {
        "mode": mode,
        "replay_seed": seed,
        "steps_compared": n - 1,
        "exact_match": n_div_steps == 0,
        "divergent_steps": n_div_steps,
        "first_divergence": first_div,
        "sample_divergences": reports,
        "final_money_sim": [sim.farms[0].money, sim.farms[1].money],
        "final_money_recorded": [steps[-1][0]["observation"]["farms"][p]["money"] for p in range(2)],
        "replay_plus_compare_seconds": elapsed,
    }
    if mode == "patch":
        result["weed_patches_tiles"] = patched_total
        result["weed_patch_days"] = patch_days
        result["forced_shops"] = recorded_shops(steps)
    if verbose:
        print(f"[{mode}] exact_match={result['exact_match']} divergent_steps={n_div_steps} "
              f"final_money sim={result['final_money_sim']} rec={result['final_money_recorded']} "
              f"({elapsed:.2f}s incl. compare)"
              + (f" weed_patches={patched_total} tiles over {patch_days} days" if mode == "patch" else ""))
    return result


def main(argv):
    path = REPLAY_DEFAULT
    mode = "both"
    out = None
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--mode":
            mode = args.pop(0)
        elif a == "--json":
            out = args.pop(0)
        else:
            path = a
    replay = load_replay(path)
    results = {}
    for m in (["rng", "patch"] if mode == "both" else [mode]):
        results[m] = run(replay, m)
    if out:
        with open(out, "w") as f:
            json.dump(results, f, indent=1)
    return results


if __name__ == "__main__":
    main(sys.argv[1:])
