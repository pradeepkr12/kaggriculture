"""Run the whole feasibility experiment and write results/sim_feasibility.json.

  1. validate_replay  : fastsim vs recorded replay (rng-exact and no-weed+patch modes)
  2. bench_engine     : raw engine steps/s (direct interpreter and env.step) + fastsim
                        cross-validation against fresh engine games (pass / busy)
  3. bench_fastsim    : fastsim steps/s, 1-day / 5-day / full-game rollouts,
                        market-only rollouts, per-turn planning budget

Single process, single thread (no multiprocessing).
Usage: python run_all.py
"""
import json
import os
import platform
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
RESULTS_DIR = os.path.join(os.path.dirname(HERE), "results")
PY = sys.executable

import validate_replay  # noqa: E402
import bench_engine  # noqa: E402
import bench_fastsim  # noqa: E402


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    t0 = time.perf_counter()
    val = validate_replay.main(["--json", os.path.join(RESULTS_DIR, "validate_replay.json")])
    eng = bench_engine.main(["--repeats", "3"])
    fs = bench_fastsim.main(["--repeats", "5"])

    b = fs["budget"]
    engine_replay = eng["workloads"]["replay"]
    fs_replay = fs["workloads"]["replay"]["full_game"]
    n_1day = b["rollouts_per_turn"]["1day_realistic"]["rollouts_per_turn"]
    n_5day = b["rollouts_per_turn"]["5day_realistic"]["rollouts_per_turn"]
    n_full = b["rollouts_per_turn"]["full_game_realistic"]["rollouts_per_turn"]
    summary = {
        "engine_direct_interpreter_steps_per_s": {k: v["direct"]["best_steps_per_s"] for k, v in eng["workloads"].items()},
        "engine_env_step_steps_per_s": {k: v["env_step"]["best_steps_per_s"] for k, v in eng["workloads"].items()},
        "engine_full_game_seconds_direct": {k: v["direct"]["best_s"] for k, v in eng["workloads"].items()},
        "engine_full_game_seconds_env_step": {k: v["env_step"]["best_s"] for k, v in eng["workloads"].items()},
        "fastsim_steps_per_s": {k: v["full_game"]["best_steps_per_s"] for k, v in fs["workloads"].items()},
        "fastsim_full_game_seconds": {k: v["full_game"]["best_s"] for k, v in fs["workloads"].items()},
        "fastsim_speedup_vs_engine_direct_replay": engine_replay["direct"]["best_s"] / fs_replay["best_s"],
        "validation_replay_109564916": {
            "rng_mode_exact_match": val["rng"]["exact_match"],
            "rng_mode_first_divergence": val["rng"]["first_divergence"],
            "patch_mode_exact_match": val["patch"]["exact_match"],
            "patch_mode_first_divergence": val["patch"]["first_divergence"],
            "patch_mode_weed_patches_tiles": val["patch"]["weed_patches_tiles"],
            "patch_mode_weed_patch_days": val["patch"]["weed_patch_days"],
            "steps_compared": val["rng"]["steps_compared"],
            "note": "all 19 end-game WEED tiles in this replay are dead plants (unwatered/decayed), not RNG spawns, hence 0 patches",
        },
        "validation_fresh_engine_games_seed1": {
            k: v["fastsim_cross_validation"] for k, v in eng["workloads"].items() if "fastsim_cross_validation" in v
        },
        "budget": {
            "kaggle_seconds_per_turn": b["kaggle_seconds_per_turn"],
            "kaggle_slowdown_factor": b["kaggle_slowdown_factor"],
            "rollouts_per_turn": {k: round(v["rollouts_per_turn"], 1) for k, v in b["rollouts_per_turn"].items()},
            "kaggle_ms_per_rollout": {k: round(v["kaggle_seconds_per_rollout"] * 1e3, 3) for k, v in b["rollouts_per_turn"].items()},
        },
        "verdict": {
            "receding_horizon_macro_plan_search_8_to_30_candidates_x_5day": n_5day >= 30,
            "candidates_5day_per_turn_sim_only": round(n_5day, 1),
            "candidates_1day_per_turn_sim_only": round(n_1day, 1),
            "full_game_rollouts_per_turn_sim_only": round(n_full, 1),
            "market_only_24step_rollouts_per_s_local": fs["market_only"]["24step"]["rollouts_per_s"],
            "market_only_120step_rollouts_per_s_local": fs["market_only"]["120step"]["rollouts_per_s"],
            "caveat": "rollout numbers count only the simulator transition with pre-recorded actions; the rollout policy "
                      "that generates actions inside the planner adds its own cost (typically 1-3x the transition), so "
                      "divide by ~2-4 for an end-to-end estimate",
        },
    }
    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "machine": {"platform": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0],
                    "cpu_count_used": 1},
        "assumptions": {"act_timeout_s": 1.0, "usable_per_turn_s": 0.4, "overage_total_s": 60.0, "turns": 720,
                        "kaggle_slowdown_factor": 2.0},
        "summary": summary,
        "validate_replay": val,
        "bench_engine": eng,
        "bench_fastsim": fs,
        "files": {
            "fastsim": os.path.join(HERE, "fastsim.py"),
            "validate_replay": os.path.join(HERE, "validate_replay.py"),
            "bench_engine": os.path.join(HERE, "bench_engine.py"),
            "bench_fastsim": os.path.join(HERE, "bench_fastsim.py"),
            "run_all": os.path.join(HERE, "run_all.py"),
            "busy_actions_trace": bench_engine.BUSY_ACTIONS_PATH,
        },
        "reproduce": [
            f"cd {HERE} && {PY} run_all.py",
            f"cd {HERE} && {PY} validate_replay.py /private/tmp/109564916.json --mode both",
            f"cd {HERE} && {PY} bench_engine.py --repeats 3",
            f"cd {HERE} && {PY} bench_fastsim.py --repeats 5",
        ],
        "total_wall_seconds": time.perf_counter() - t0,
    }
    path = os.path.join(RESULTS_DIR, "sim_feasibility.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print("wrote", path, f"({out['total_wall_seconds']:.1f}s)")
    return out


if __name__ == "__main__":
    main()
