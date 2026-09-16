"""Task 4: route-planning bound from one recorded control game (sol5-identical,
vs sol5, milk_starved, seed 1000, seat 0). Per day and unit: tiles where the unit
acted (animals count once for FEED/CARE/HARVEST/COLLECT; plants once per action
tile; shed tiles for PICKUP/DROP) -> nearest-neighbour open tour from the unit's
hour-0 position, plus a 2-opt polish; compared with the unit's actual moves.
Reproduce: /opt/miniconda3/envs/env2/bin/python route_bound.py
"""
import json, os
from labrun import play_full, RESULTS
DIRS = {"NORTH", "SOUTH", "EAST", "WEST"}


def md(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def nn_path(start, tiles):
    left = [t for t in tiles if t != start]
    cur, total, order = start, 0, [start]
    while left:
        nxt = min(left, key=lambda t: (md(cur, t), t))
        total += md(cur, nxt)
        left.remove(nxt)
        order.append(nxt)
        cur = nxt
    return total, order


def path_len(order):
    return sum(md(order[i], order[i + 1]) for i in range(len(order) - 1))


def two_opt(order):
    """open path, fixed start (index 0)."""
    best = path_len(order)
    improved = True
    n = len(order)
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                L = path_len(cand)
                if L < best - 1e-9:
                    order, best, improved = cand, L, True
    return best, order


r = play_full(("labor", {"hungarian": False}), ("sol5", None), "milk_starved", 1000, trace_seat=0)
trace = r["trace"]
by_day = {}
for rec in trace:
    by_day.setdefault(rec["day"], []).append(rec)

days_out, tot = [], {"moves": 0, "actions": 0, "idle": 0, "nn": 0, "opt2": 0, "tiles_visited_sum": 0, "distinct_tiles_farm": 0, "global_bound": 0, "unit_turns": 0}
for day in sorted(by_day):
    recs = by_day[day]
    nu_max = max(len(x["units"]) for x in recs)
    per_unit = []
    all_tiles = set()
    for ui in range(nu_max):
        start, tiles, moves, actions, idle, feeder_turns = None, [], 0, 0, 0, 0
        for x in recs:
            if ui >= len(x["units"]):
                continue
            pos = tuple(x["units"][ui])
            if start is None:
                start = pos
            op = x["ops"][ui][0]
            if ui in x["busy"]:
                feeder_turns += 1
            if op in DIRS:
                moves += 1
            elif op == "PASS":
                idle += 1
            else:
                actions += 1
                if pos not in tiles:
                    tiles.append(pos)
        if start is None:
            continue
        all_tiles.update(tiles)
        nn, order = nn_path(start, tiles)
        o2, _ = two_opt(order)
        per_unit.append({"unit": ui, "start": list(start), "n_tiles": len(tiles), "moves": moves, "actions": actions,
                         "idle": idle, "feeder_turns": feeder_turns, "nn": nn, "opt2": o2})
    d = {"day": day, "units": len(per_unit), "unit_turns": sum(len(x["units"]) for x in recs),
         "moves": sum(u["moves"] for u in per_unit), "actions": sum(u["actions"] for u in per_unit),
         "idle": sum(u["idle"] for u in per_unit), "tiles_visited_sum": sum(u["n_tiles"] for u in per_unit),
         "distinct_tiles_farm": len(all_tiles), "nn": sum(u["nn"] for u in per_unit), "opt2": sum(u["opt2"] for u in per_unit),
         "global_bound": max(0, len(all_tiles) - len(per_unit)), "per_unit": per_unit}
    d["avoidable_vs_nn"] = d["moves"] - d["nn"]
    days_out.append(d)
    for k in tot:
        tot[k] += d[k]
    print(f"day {day:2d} units={d['units']:2d} tiles(sum)={d['tiles_visited_sum']:3d} distinct={d['distinct_tiles_farm']:3d} "
          f"moves={d['moves']:3d} actions={d['actions']:3d} idle={d['idle']:3d}  NN={d['nn']:3d} 2opt={d['opt2']:3d} globalLB={d['global_bound']:3d}  avoidable(NN)={d['avoidable_vs_nn']:3d}")
tot["avoidable_vs_nn"] = tot["moves"] - tot["nn"]
tot["avoidable_vs_opt2"] = tot["moves"] - tot["opt2"]
tot["avoidable_vs_global"] = tot["moves"] - tot["global_bound"]
tot["walk_share_actual"] = tot["moves"] / tot["unit_turns"]
tot["walk_share_if_nn"] = tot["nn"] / tot["unit_turns"]
tot["walk_share_if_global"] = tot["global_bound"] / tot["unit_turns"]
print("TOTAL", json.dumps(tot))
out = {"command": "cd sol7/research/labor && /opt/miniconda3/envs/env2/bin/python route_bound.py",
       "game": {"specs": r["specs"], "schedule": "milk_starved", "seed": 1000, "rewards": r["rewards"]},
       "method": __doc__, "total": tot, "days": days_out}
with open(os.path.join(RESULTS, "labor_route_bound.json"), "w") as f:
    json.dump(out, f, indent=1)
print("saved", os.path.join(RESULTS, "labor_route_bound.json"))
