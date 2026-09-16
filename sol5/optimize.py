"""CEM over the sol4 strategy vector, maximizing mean coin margin vs an opponent pool.

Supports coordinate-subset optimization (--dims) so several optimizers can run in
parallel on disjoint dimensions with a split CPU budget (--workers), then be merged.

Usage:
  python optimize.py --dims n_cows,n_sheep,n_geese,animal_day2,melon_tiles \
      --pop 12 --gens 6 --seeds 1,2,3 --workers 4 --pool pass,seed --out cem_A.json
  --pool items: pass | starter | sol3 | melon | seed (the current SEED_VEC as a fixed
    contested opponent) | mirror (the candidate itself; margin is 0 by construction,
    so only use with other pool members)
"""
import sys, os, json, random, statistics, argparse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena import fitness
from farmlib import PARAM_SPEC, DIM, SEED_VEC, clip_vec, vec_to_params

NAMES = [n for (n, _, _, _) in PARAM_SPEC]


def resolve_pool(items, cand=None):
    pool = []
    for it in items:
        if it == "seed":
            pool.append(list(SEED_VEC))
        elif it == "mirror":
            pool.append(list(cand) if cand is not None else list(SEED_VEC))
        else:
            pool.append(it)
    return pool


def evaluate(vec, pool_items, seeds, workers):
    pool = resolve_pool(pool_items, vec)
    f = fitness(list(vec), pool, seeds, workers=workers)
    return f["margin"], f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dims", default=",".join(NAMES))
    ap.add_argument("--pop", type=int, default=12)
    ap.add_argument("--elite", type=int, default=4)
    ap.add_argument("--gens", type=int, default=6)
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pool", default="pass,seed")
    ap.add_argument("--init", default=None, help="JSON list initial mean (default SEED_VEC)")
    ap.add_argument("--std_scale", type=float, default=0.25, help="initial std as fraction of range")
    ap.add_argument("--out", default="cem_out.json")
    ap.add_argument("--rng", type=int, default=0)
    a = ap.parse_args()

    dims = [NAMES.index(d) for d in a.dims.split(",") if d]
    seeds = [int(s) for s in a.seeds.split(",")]
    pool_items = a.pool.split(",")
    random.seed(a.rng)

    mean = list(json.loads(a.init)) if a.init else list(SEED_VEC)
    mean = clip_vec(mean)
    std = [0.0] * DIM
    for i in dims:
        _, lo, hi, _ = PARAM_SPEC[i]
        std[i] = (hi - lo) * a.std_scale

    log = []
    t0 = time.time()
    # evaluate the initial mean once as the baseline
    base_m, base_f = evaluate(mean, pool_items, seeds, a.workers)
    print(f"baseline margin={base_m:+.0f} my_mean={base_f['my_mean']:.0f}", flush=True)
    best_vec, best_m = list(mean), base_m

    for g in range(a.gens):
        pop = []
        for _ in range(a.pop):
            v = list(mean)
            for i in dims:
                v[i] = random.gauss(mean[i], std[i])
            pop.append(clip_vec(v))
        pop.append(list(mean))
        scored = []
        for v in pop:
            m, f = evaluate(v, pool_items, seeds, a.workers)
            scored.append((m, v, f["my_mean"]))
        scored.sort(key=lambda t: -t[0])
        elite = scored[:a.elite]
        if scored[0][0] > best_m:
            best_m, best_vec = scored[0][0], list(scored[0][1])
        for i in dims:
            vals = [e[1][i] for e in elite]
            mean[i] = statistics.mean(vals)
            _, lo, hi, _ = PARAM_SPEC[i]
            std[i] = max((hi - lo) * 0.03, statistics.pstdev(vals))
        row = {"gen": g, "best_margin": scored[0][0], "best_my_mean": scored[0][2],
               "elite_mean_margin": statistics.mean(e[0] for e in elite),
               "mean": {NAMES[i]: round(mean[i], 3) for i in dims}, "t": round(time.time() - t0)}
        log.append(row)
        print(json.dumps(row), flush=True)

    out = {"dims": [NAMES[i] for i in dims], "pool": pool_items, "seeds": seeds,
           "baseline_margin": base_m, "best_margin": best_m, "best_vec": best_vec,
           "best_params": vec_to_params(best_vec), "final_mean": mean, "log": log}
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"BEST margin={best_m:+.0f} (baseline {base_m:+.0f})  vec={[round(x, 3) for x in best_vec]}")
    print(f"saved {a.out}")


if __name__ == "__main__":
    main()
