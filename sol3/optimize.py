"""CEM optimizer: maximize self-play coin margin vs a fixed opponent pool.

Cross-Entropy Method — a simple, robust black-box optimizer well suited to a
low-dim (9) strategy vector and a noisy Monte-Carlo return. Each generation:
sample a population from a Gaussian, evaluate each candidate's mean margin vs the
opponent pool (both seats, several seeds), keep the top-k "elite", refit the
Gaussian to them. The mean converges to a high-margin strategy.

Opponent pool is fixed vectors (picklable): a pure sell-first melon and a
melon+strawberry hybrid, so we optimize for robustness against both the melon
meta and a hybrid rival rather than overfitting one opponent.
"""
import sys, os, random, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arena import fitness, DEFAULT_WORKERS
from farmlib import PARAM_SPEC, DIM, clip_vec

MELON_SF = [6, 0, 0, 0, 0, 3, 0, 16, 0.30]
HYB_STRAW = [4.0, 0, 0, 0, 3.0, 4, 1, 40, 0.80]
POOL = [MELON_SF, HYB_STRAW]

# CEM hyperparameters
POP = 16
ELITE = 5
GENS = 6
SEEDS = [1, 2, 3, 4]
INIT_MEAN = [4.0, 0.5, 1.5, 0.5, 3.0, 4, 1, 40, 0.80]
INIT_STD = [1.0, 0.8, 1.2, 0.8, 1.0, 1.0, 0.6, 8.0, 0.10]


def evaluate(vec):
    f = fitness(list(vec), POOL, SEEDS)
    return f["margin"], f


def main():
    random.seed(0)
    mean = list(INIT_MEAN)
    std = list(INIT_STD)
    best_vec, best_margin = None, -1e18

    for gen in range(GENS):
        pop = [clip_vec([random.gauss(mean[i], std[i]) for i in range(DIM)]) for _ in range(POP)]
        pop.append(clip_vec(mean))  # always keep the current mean
        scored = []
        for vec in pop:
            m, f = evaluate(vec)
            scored.append((m, vec, f))
        scored.sort(key=lambda t: -t[0])
        elite = scored[:ELITE]
        if scored[0][0] > best_margin:
            best_margin, best_vec = scored[0][0], list(scored[0][1])
        # refit gaussian to elite
        for i in range(DIM):
            vals = [e[1][i] for e in elite]
            mean[i] = statistics.mean(vals)
            std[i] = max(0.05, statistics.pstdev(vals))
        print(f"gen {gen}: best_margin={scored[0][0]:+8.0f}  elite_mean_margin={statistics.mean(e[0] for e in elite):+8.0f}")
        print(f"   mean = [{', '.join(f'{x:.2f}' for x in mean)}]")

    print("\n=== BEST ===")
    print(f"margin={best_margin:+8.0f}")
    print(f"vec = {[round(x, 3) for x in best_vec]}")
    # detail vs each opponent
    from farmlib import vec_to_params
    print("params:", vec_to_params(best_vec))
    return best_vec


if __name__ == "__main__":
    main()
