"""Evaluate main.agent over N seeded games vs baselines. Reports scores/win-rate."""
import sys
import statistics
from kaggle_environments import make

sys.path.insert(0, ".")
from main import agent as my_agent  # noqa: E402


def run_game(opponent, seed, my_pos=0):
    env = make("kaggriculture", configuration={"seed": seed}, debug=False)
    players = [None, None]
    players[my_pos] = my_agent
    players[1 - my_pos] = opponent
    env.run(players)
    final = env.steps[-1]
    my_reward = final[my_pos]["reward"]
    opp_reward = final[1 - my_pos]["reward"]
    return my_reward, opp_reward


def evaluate(opponent_name, n=10):
    mine, opp, wins = [], [], 0
    for s in range(n):
        # alternate seat to be fair
        my_pos = s % 2
        mr, orr = run_game(opponent_name, seed=1000 + s, my_pos=my_pos)
        mine.append(mr)
        opp.append(orr)
        if mr > orr:
            wins += 1
    print(f"vs {opponent_name:10s} | n={n} | "
          f"my avg={statistics.mean(mine):8.0f} (min={min(mine):.0f}, max={max(mine):.0f}) | "
          f"opp avg={statistics.mean(opp):7.0f} | winrate={wins}/{n}")
    return statistics.mean(mine)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    for opp in ["random", "starter", "pass"]:
        evaluate(opp, n)
