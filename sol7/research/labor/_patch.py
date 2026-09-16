"""One-shot patcher: sol5/farmlib.py -> farmlib_labor.py (instrumented + Hungarian option).
Re-run: cp ../../../sol5/farmlib.py farmlib_labor.py && python _patch.py
"""
import re, os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "farmlib_labor.py")
src = open(P).read()

def rep(old, new, count=1):
    global src
    assert src.count(old) == count, (src.count(old), old[:80])
    src = src.replace(old, new)

rep('"""sol4 parametrized policy', '"""RESEARCH COPY of sol5/farmlib.py (sol7/research/labor). Adds: per-turn\nassignment logging, per-unit trace, feeder/crew sub-counters, and an optional\nHungarian (optimal) crop-crew assignment. Control path is byte-identical logic.\n\nsol4 parametrized policy')

# ---- Hungarian ---------------------------------------------------------------
rep('''# priorities (crop crew)
P_WATER_CRIT = 8''', '''# ---- Hungarian (rectangular, minimise cost; rows <= cols) ------------------------
def hungarian_min(cost):
    """cost: n x m (n <= m) list of lists. Returns list col-index per row.
    e-maxx / Kuhn-Munkres with potentials, O(n^2 m)."""
    n = len(cost)
    m = len(cost[0]) if n else 0
    assert n <= m
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)          # p[j] = row matched to column j (1-based), 0 = none
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            row = cost[i0 - 1]
            for j in range(1, m + 1):
                if not used[j]:
                    cur = row[j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    ans = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            ans[p[j] - 1] = j - 1
    return ans


HUNG_C0 = 200.0        # cost = C0 - score for eligible pairs (score in [-20, 40])
HUNG_INELIG = 1e6
HUNG_COL_CAP = 40


def hungarian_assign(score):
    """score: n_units x n_cols, None = ineligible. Maximise total score.
    Returns col index per unit, -1 if unassigned (no eligible column)."""
    n = len(score)
    if n == 0:
        return []
    m = len(score[0])
    if m == 0:
        return [-1] * n
    width = max(n, m)
    cost = []
    for r in score:
        row = [HUNG_C0 - s if s is not None else HUNG_INELIG for s in r]
        row.extend([HUNG_INELIG] * (width - m))
        cost.append(row)
    a = hungarian_min(cost)
    out = []
    for i, j in enumerate(a):
        out.append(j if (j >= 0 and j < m and score[i][j] is not None) else -1)
    return out


# priorities (crop crew)
P_WATER_CRIT = 8''')

# ---- builder signature ---------------------------------------------------------
rep('''def build_agent(params_or_vec):
    P = params_or_vec if isinstance(params_or_vec, dict) and "n_cows" in params_or_vec \\
        else vec_to_params(params_or_vec)

    mem = {"day": -1, "last_key": {}, "crew": None,
           "stats": {"days": {}, "escapes": 0, "plant_blocked": 0}}
''', '''def build_agent(params_or_vec=None, hungarian=False, log=None, trace=None):
    """hungarian: crop-crew assignment by Hungarian instead of greedy sweep.
    log: list -> per-turn assignment matrices appended (offline experiment).
    trace: list -> per-turn unit positions/ops appended (route analysis)."""
    if params_or_vec is None:
        params_or_vec = SEED_VEC
    P = params_or_vec if isinstance(params_or_vec, dict) and "n_cows" in params_or_vec \\
        else vec_to_params(params_or_vec)

    mem = {"day": -1, "last_key": {}, "crew": None,
           "stats": {"days": {}, "escapes": 0, "plant_blocked": 0,
                     "hungarian": bool(hungarian), "hung_turns": 0, "hung_ncols_max": 0}}
''')

rep('''            stats["days"][day] = {"fed": 0, "cared": 0, "animals": 0, "money_h0": money,
                                  "idle": 0, "moves": 0, "actions": 0}''',
    '''            stats["days"][day] = {"fed": 0, "cared": 0, "animals": 0, "money_h0": money,
                                  "idle": 0, "moves": 0, "actions": 0,
                                  # research sub-counters (moves = feeder_moves + crew_moves + home_moves)
                                  "unit_turns": 0, "feeder_turns": 0, "feeder_moves": 0,
                                  "crew_turns": 0, "crew_moves": 0, "home_moves": 0, "hire_moves": 0}''')

# ---- assignment: build matrix + optional hungarian ---------------------------------
rep('''        for ui in unit_order:
            ux, uy = units[ui]
            best, best_s = None, None
            for tk in tasks:
                dk = (tk["x"], tk["y"], tk["op"][0]) if not tk["shed"] else tk["key"]
                if dk in used or not eligible(ui, tk):
                    continue
                tx, ty = target_of(ui, tk)
                s = tk["prio"] * K - _dist(ux, uy, tx, ty) + (3 if committed.get(ui) == tk["key"] else 0)
                if best_s is None or s > best_s:
                    best_s, best = s, tk
            if best is not None:
                assigned[ui] = best
                used.add((best["x"], best["y"], best["op"][0]) if not best["shed"] else best["key"])
''', '''        # -- research: score matrix over free units x distinct task columns (dk) --
        free = list(unit_order)
        col_of, cols = {}, []
        for ti, tk in enumerate(tasks):
            dk = (tk["x"], tk["y"], tk["op"][0]) if not tk["shed"] else tk["key"]
            if dk in used:
                continue
            if dk not in col_of:
                col_of[dk] = len(cols)
                cols.append({"dk": dk, "tis": []})
            cols[col_of[dk]]["tis"].append(ti)
        score_m, dist_m, best_ti = [], [], []
        for ui in free:
            ux, uy = units[ui]
            srow, drow, brow = [], [], []
            for c in cols:
                bs, bd, bt = None, None, None
                for ti in c["tis"]:
                    tk = tasks[ti]
                    if not eligible(ui, tk):
                        continue
                    tx, ty = target_of(ui, tk)
                    d = _dist(ux, uy, tx, ty)
                    s = tk["prio"] * K - d + (3 if committed.get(ui) == tk["key"] else 0)
                    if bs is None or s > bs:
                        bs, bd, bt = s, d, ti
                srow.append(bs); drow.append(bd); brow.append(bt)
            score_m.append(srow); dist_m.append(drow); best_ti.append(brow)

        # greedy (original sol5 sweep, verbatim) ---------------------------------
        greedy_pick = {}
        if not hungarian or log is not None:
            g_used = set(used)
            g_assigned = dict()
            for ui in unit_order:
                ux, uy = units[ui]
                best, best_s = None, None
                for tk in tasks:
                    dk = (tk["x"], tk["y"], tk["op"][0]) if not tk["shed"] else tk["key"]
                    if dk in g_used or not eligible(ui, tk):
                        continue
                    tx, ty = target_of(ui, tk)
                    s = tk["prio"] * K - _dist(ux, uy, tx, ty) + (3 if committed.get(ui) == tk["key"] else 0)
                    if best_s is None or s > best_s:
                        best_s, best = s, tk
                if best is not None:
                    g_assigned[ui] = best
                    dk = (best["x"], best["y"], best["op"][0]) if not best["shed"] else best["key"]
                    g_used.add(dk)
                    greedy_pick[ui] = col_of[dk]
            if not hungarian:
                for ui, tk in g_assigned.items():
                    assigned[ui] = tk
                used = g_used

        # hungarian ----------------------------------------------------------------
        hung_pick = {}
        if hungarian and free and cols:
            keep = list(range(len(cols)))
            if len(cols) > HUNG_COL_CAP:
                def colbest(j):
                    return max((score_m[i][j] for i in range(len(free)) if score_m[i][j] is not None), default=-1e9)
                keep = sorted(range(len(cols)), key=lambda j: -colbest(j))[:HUNG_COL_CAP]
            sub = [[score_m[i][j] for j in keep] for i in range(len(free))]
            res = hungarian_assign(sub)
            stats["hung_turns"] += 1
            stats["hung_ncols_max"] = max(stats["hung_ncols_max"], len(cols))
            for i, jj in enumerate(res):
                if jj >= 0:
                    j = keep[jj]
                    ui = free[i]
                    hung_pick[ui] = j
                    assigned[ui] = tasks[best_ti[i][j]]
                    used.add(cols[j]["dk"])

        if log is not None and free and cols:
            log.append({"day": day, "hour": hour, "K": K, "nu": nu, "n_busy": len(busy),
                        "free": [[ui, units[ui][0], units[ui][1]] for ui in free],
                        "cols": [{"key": str(c["dk"]), "prio": tasks[c["tis"][0]]["prio"],
                                  "shed": tasks[c["tis"][0]]["shed"]} for c in cols],
                        "score": score_m, "dist": dist_m,
                        "greedy": [greedy_pick.get(ui, -1) for ui in free],
                        "hung": [hung_pick.get(ui, -1) for ui in free] if hungarian else None})
''')

# ---- counters in the emit loop ---------------------------------------------------
rep('''        for ui in range(nu):
            if ui in busy:
                dstat["actions" if len(ops_out[ui]) > 1 or ops_out[ui][0] not in ("NORTH", "SOUTH", "EAST", "WEST") else "moves"] += 1
                continue
            tk = assigned[ui]
            ux, uy = units[ui]
            if tk is None:
                if dist_to_shed(ux, uy) > 1:
                    sx, sy = _nearest_shed(ux, uy)
                    ops_out[ui] = [_step_toward(ux, uy, sx, sy)]
                    dstat["moves"] += 1
                else:
                    ops_out[ui] = ["PASS"]
                    dstat["idle"] += 1
                continue''', '''        dstat["unit_turns"] += nu
        for ui in range(nu):
            if ui in busy:
                dstat["feeder_turns"] += 1
                if len(ops_out[ui]) > 1 or ops_out[ui][0] not in ("NORTH", "SOUTH", "EAST", "WEST"):
                    dstat["actions"] += 1
                else:
                    dstat["moves"] += 1
                    dstat["feeder_moves"] += 1
                continue
            dstat["crew_turns"] += 1
            tk = assigned[ui]
            ux, uy = units[ui]
            if tk is None:
                if dist_to_shed(ux, uy) > 1:
                    sx, sy = _nearest_shed(ux, uy)
                    ops_out[ui] = [_step_toward(ux, uy, sx, sy)]
                    dstat["moves"] += 1
                    dstat["home_moves"] += 1
                else:
                    ops_out[ui] = ["PASS"]
                    dstat["idle"] += 1
                continue''')

rep('''            else:
                ops_out[ui] = [_step_toward(ux, uy, tx, ty)]
                dstat["moves"] += 1
        mem["last_key"] = new_last''', '''            else:
                ops_out[ui] = [_step_toward(ux, uy, tx, ty)]
                dstat["moves"] += 1
                dstat["crew_moves"] += 1
        mem["last_key"] = new_last
        if trace is not None:
            trace.append({"day": day, "hour": hour, "units": [list(u) for u in units],
                          "ops": [list(o) for o in ops_out], "busy": sorted(busy),
                          "assigned_key": [tk["key"] if tk else None for tk in assigned]})''')

rep('''    agent.stats = mem["stats"]
    agent.params = P
    agent.mem = mem
    return agent
''', '''    agent.stats = mem["stats"]
    agent.params = P
    agent.mem = mem
    return agent


def build_agent_hungarian(params_or_vec=None, log=None, trace=None):
    """sol5 SEED_VEC agent with the Hungarian crop-crew assignment enabled."""
    return build_agent(params_or_vec, hungarian=True, log=log, trace=trace)
''')

open(P, "w").write(src)
print("patched", P, len(src.splitlines()), "lines")
