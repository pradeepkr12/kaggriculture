"""Task 1: sol5 walking share (vs pass, vs sol5; milk_starved seed 1000), plus
equivalence check of the research copy (flag off) against sol5/farmlib.py.
Reproduce: /opt/miniconda3/envs/env2/bin/python measure_walk.py
"""
import json, os, sys
from labrun import play_full, walk_summary, RESULTS
SOL5 = ("sol5", None)
CTRL = ("labor", {"hungarian": False})
HUNG = ("labor", {"hungarian": True})

games = {}
for oname, opp in (("pass", "pass"), ("sol5", SOL5)):
    for label, spec in (("sol5_orig", SOL5), ("labor_ctrl", CTRL), ("labor_hung", HUNG)):
        r = play_full(spec, opp, "milk_starved", 1000)
        st = r["stats"][0]
        games[f"{label}_vs_{oname}"] = {"rewards": r["rewards"], "latency": r["latency"][0],
                                        "walk": walk_summary(st),
                                        "hung_turns": st.get("hung_turns"), "hung_ncols_max": st.get("hung_ncols_max"),
                                        "per_day": {str(d): {k: v for k, v in ds.items() if k in ("moves","actions","idle","unit_turns","feeder_turns","feeder_moves","crew_turns","crew_moves","home_moves","animals")}
                                                    for d, ds in st["days"].items()}}
        w = games[f"{label}_vs_{oname}"]["walk"]["total"]
        print(f"{label:11s} vs {oname:5s} reward={r['rewards'][0]:8.0f}/{r['rewards'][1]:8.0f} "
              f"moves={w['moves']} actions={w['actions']} idle={w['idle']} unit_turns={w['unit_turns']} "
              f"walk={w['walk_share']:.3f} lat_max={r['latency'][0]['max']*1000:.0f}ms")
        for b in ("d00_09", "d10_19", "d20_29"):
            wb = games[f"{label}_vs_{oname}"]["walk"][b]
            extra = ""
            if wb.get("feeder_turns"):
                extra = f" feeder_turns={wb['feeder_turns']} feeder_walk={wb['feeder_walk_share']:.3f} crew_turns={wb['crew_turns']} crew_walk={wb['crew_walk_share']:.3f} (task {wb['crew_task_walk_share']:.3f}, home {wb['home_moves']})"
            print(f"    {b}: moves={wb['moves']} actions={wb['actions']} idle={wb['idle']} walk={wb['walk_share']:.3f}{extra}")

equiv = {o: games[f"sol5_orig_vs_{o}"]["rewards"] == games[f"labor_ctrl_vs_{o}"]["rewards"] for o in ("pass", "sol5")}
print("copy(flag off) == sol5 rewards:", equiv)
out = {"command": "cd sol7/research/labor && /opt/miniconda3/envs/env2/bin/python measure_walk.py",
       "schedule": "milk_starved", "seed": 1000, "equivalence_ctrl_vs_orig": equiv, "games": games}
os.makedirs(RESULTS, exist_ok=True)
with open(os.path.join(RESULTS, "labor_walking.json"), "w") as f:
    json.dump(out, f, indent=1, default=str)
print("saved", os.path.join(RESULTS, "labor_walking.json"))
