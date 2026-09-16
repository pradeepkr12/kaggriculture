"""Per-day action / crop histogram for one game (labor + crop-health diagnostics).

Usage: python hist.py [seed] [opponent] [vec-json]
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import Counter
from kaggle_environments import make
from farmlib import build_agent, SEED_VEC
from arena import _resolve


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    opp = sys.argv[2] if len(sys.argv) > 2 else "pass"
    vec = json.loads(sys.argv[3]) if len(sys.argv) > 3 else SEED_VEC
    ag = build_agent(vec)
    env = make("kaggriculture", configuration={"seed": seed}, debug=False)
    env.run([ag, _resolve(opp)])
    steps = env.steps
    print(f"seed={seed} opp={opp} ME={steps[-1][0]['reward']:.0f} OPP={steps[-1][1]['reward']:.0f}")
    print(" day units | PLANT WATER HARV FEED CARE COLL DROP PICK BUILD PLACE FERT DIG MOVE PASS | alive: mel str tom whe car | weeds seeds shed money")
    for d in range(30):
        ops = Counter()
        for h in range(24):
            i = d * 24 + h + 1
            if i >= len(steps):
                break
            a = steps[i][0]["action"] or {}
            for op in [a.get("farmer")] + (a.get("hands") or []):
                if op:
                    ops["MOVE" if op[0] in ("NORTH", "SOUTH", "EAST", "WEST") else op[0]] += 1
        obs = steps[min(len(steps) - 1, d * 24 + 12)][0]["observation"]
        me = obs["farms"][0]
        cc = Counter(); weeds = 0
        for row in me["tiles"]:
            for t in row:
                if isinstance(t, dict):
                    if t.get("kind") == "PLANT": cc[t["crop"]] += 1
                    elif t.get("kind") == "WEED": weeds += 1
        nunits = 1 + len(me["hands"])
        seeds = sum(obs["private"]["seeds"].values()); shed = sum(obs["private"]["shed"].values())
        print(f" {d:2d} {nunits:3d} | {ops['PLANT']:5d} {ops['WATER']:5d} {ops['HARVEST']:4d} {ops['FEED']:4d} {ops['CARE']:4d} "
              f"{ops['COLLECT_FERTILIZER']:4d} {ops['DROP']:4d} {ops['PICKUP']:4d} {ops['BUILD_PASTURE']+ops['BUILD_COOP']:5d} "
              f"{ops['PLACE']:5d} {ops['FERTILIZE']:4d} {ops['DIG']:3d} {ops['MOVE']:4d} {ops['PASS']:4d} | "
              f"{cc['MELON']:3d} {cc['STRAWBERRY']:3d} {cc['TOMATO']:3d} {cc['WHEAT']:3d} {cc['CARROT']:3d} | "
              f"{weeds:3d} {seeds:5d} {shed:4d} {me['money']:7.0f}")


if __name__ == "__main__":
    main()
