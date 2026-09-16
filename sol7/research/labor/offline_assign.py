"""Task 2: offline greedy-vs-Hungarian on the logged per-turn score matrices of the
control (sol5-identical) agent. score = prio*K - dist (+3 commitment), as in the code.
Reproduce: /opt/miniconda3/envs/env2/bin/python offline_assign.py
"""
import json, os, time, statistics as S
from labrun import play_full, RESULTS, BANDS
import farmlib_labor as FL
CTRL = ("labor", {"hungarian": False})


def totals(rec, pick):
    sc = sum(rec["score"][i][j] for i, j in enumerate(pick) if j >= 0)
    di = sum(rec["dist"][i][j] for i, j in enumerate(pick) if j >= 0)
    na = sum(1 for j in pick if j >= 0)
    return sc, di, na


def hung_capped(rec, cap):
    score = rec["score"]
    n, m = len(score), len(score[0])
    keep = list(range(m))
    if cap and m > cap:
        def colbest(j):
            return max((score[i][j] for i in range(n) if score[i][j] is not None), default=-1e9)
        keep = sorted(range(m), key=lambda j: -colbest(j))[:cap]
    sub = [[score[i][j] for j in keep] for i in range(n)]
    res = FL.hungarian_assign(sub)
    return [keep[j] if j >= 0 else -1 for j in res]


def analyse(log):
    rows = []
    for rec in log:
        g = rec["greedy"]
        t0 = time.perf_counter()
        h = hung_capped(rec, FL.HUNG_COL_CAP)
        dt = time.perf_counter() - t0
        hf = hung_capped(rec, None)
        gs, gd, gn = totals(rec, g)
        hs, hd, hn = totals(rec, h)
        fs, fd, fn = totals(rec, hf)
        rows.append({"day": rec["day"], "hour": rec["hour"], "K": rec["K"], "n_free": len(rec["free"]),
                     "n_cols": len(rec["cols"]), "g_score": gs, "g_dist": gd, "g_n": gn,
                     "h_score": hs, "h_dist": hd, "h_n": hn, "f_score": fs, "f_dist": fd, "f_n": fn, "h_ms": dt * 1000})
    def summ(rs):
        if not rs:
            return None
        sub = [r for r in rs if r["h_score"] > r["g_score"] + 1e-9]
        return {"turns": len(rs), "mean_free_units": S.mean(r["n_free"] for r in rs),
                "mean_cols": S.mean(r["n_cols"] for r in rs), "max_cols": max(r["n_cols"] for r in rs),
                "share_turns_cols_gt_cap": S.mean(1 if r["n_cols"] > FL.HUNG_COL_CAP else 0 for r in rs),
                "share_greedy_suboptimal": len(sub) / len(rs),
                "mean_score_gain": S.mean(r["h_score"] - r["g_score"] for r in rs),
                "mean_score_gain_when_subopt": S.mean(r["h_score"] - r["g_score"] for r in sub) if sub else 0.0,
                "mean_dist_saving": S.mean(r["g_dist"] - r["h_dist"] for r in rs),
                "mean_dist_saving_when_subopt": S.mean(r["g_dist"] - r["h_dist"] for r in sub) if sub else 0.0,
                "total_dist_greedy": sum(r["g_dist"] for r in rs), "total_dist_hung": sum(r["h_dist"] for r in rs),
                "share_hung_assigns_more_units": S.mean(1 if r["h_n"] > r["g_n"] else 0 for r in rs),
                "extra_units_assigned_total": sum(r["h_n"] - r["g_n"] for r in rs),
                "share_uncapped_beats_capped": S.mean(1 if r["f_score"] > r["h_score"] + 1e-9 else 0 for r in rs),
                "hung_ms_mean": S.mean(r["h_ms"] for r in rs), "hung_ms_max": max(r["h_ms"] for r in rs),
                "hung_ms_p99": sorted(r["h_ms"] for r in rs)[int(0.99 * (len(rs) - 1))]}
    out = {"all": summ(rows)}
    for name, lo, hi in BANDS:
        out[name] = summ([r for r in rows if lo <= r["day"] <= hi])
    out["K1_hour_lt16"] = summ([r for r in rows if r["K"] == 1.0])
    out["K3_hour_ge16"] = summ([r for r in rows if r["K"] == 3.0])
    return out, rows


res = {"command": "cd sol7/research/labor && /opt/miniconda3/envs/env2/bin/python offline_assign.py",
       "schedule": "milk_starved", "seed": 1000, "score_def": "prio*K - manhattan_dist + 3*committed; K=1 (hour<16) else 3",
       "col_cap": FL.HUNG_COL_CAP, "games": {}}
for oname, opp in (("pass", "pass"), ("sol5", ("sol5", None))):
    r = play_full(CTRL, opp, "milk_starved", 1000, log_seat=0)
    summ, rows = analyse(r["log"])
    res["games"][f"ctrl_vs_{oname}"] = {"rewards": r["rewards"], "summary": summ}
    a = summ["all"]
    print(f"vs {oname}: turns={a['turns']} free/turn={a['mean_free_units']:.1f} cols/turn={a['mean_cols']:.1f} (max {a['max_cols']}, >cap {a['share_turns_cols_gt_cap']:.1%})")
    print(f"   greedy suboptimal {a['share_greedy_suboptimal']:.1%} of turns; mean score gain {a['mean_score_gain']:.3f}/turn ({a['mean_score_gain_when_subopt']:.2f} when subopt)")
    print(f"   mean dist saving {a['mean_dist_saving']:.3f} moves/turn ({a['mean_dist_saving_when_subopt']:.2f} when subopt); total dist greedy={a['total_dist_greedy']} hung={a['total_dist_hung']}")
    print(f"   hung assigns more units in {a['share_hung_assigns_more_units']:.1%} turns (+{a['extra_units_assigned_total']} unit-assignments); uncapped>capped {a['share_uncapped_beats_capped']:.1%}; hung ms mean={a['hung_ms_mean']:.2f} p99={a['hung_ms_p99']:.2f} max={a['hung_ms_max']:.2f}")
    for b in ("d00_09", "d10_19", "d20_29", "K1_hour_lt16", "K3_hour_ge16"):
        s = summ[b]
        if s:
            print(f"   {b}: subopt={s['share_greedy_suboptimal']:.1%} score_gain={s['mean_score_gain']:.3f} dist_save={s['mean_dist_saving']:.3f} cols={s['mean_cols']:.1f}")
with open(os.path.join(RESULTS, "labor_offline_assign.json"), "w") as f:
    json.dump(res, f, indent=1)
print("saved", os.path.join(RESULTS, "labor_offline_assign.json"))
