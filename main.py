"""Kaggriculture agent — melon-focused, multi-unit greedy task assignment.

Strategy
--------
Melon is by far the most labor-efficient crop: seed $80, base sale $250, up to 6
units/tile, and no town *shop* consumes it (only the town center, 1/day), so the
glut curve barely recovers but also starts very high. The binding constraint is
LABOR (each farmer/hand does one action per turn, and moving between tiles costs
actions), so we hire cheap farm hands (fib cost: 1,1,2,3,5...) and assign every
unit to the highest-value nearby task each turn.

Task priority: survival-water (plant dies tonight) > harvest > bonus-water >
plant > dig-weed. Melons are sold from the shed every turn (price only recovers
via town consumption, which is negligible for melon, so holding doesn't help).
"""

# ---- tunables (tuned empirically via eval.py) --------------------------------
CROP = "MELON"
SEED_COST = 80
FIRST_YIELD_DAY = 10
MAX_YIELD_DAY = 12
MAX_YIELD = 6
WINDOW_START = (MAX_YIELD_DAY + 1) // 2  # 6

TARGET_HANDS = 3          # hands to hire each morning
MAX_ACTIVE = 16           # cap on simultaneously-growing melon tiles
PLANT_DEADLINE_DAY = 18   # last day we start a new melon (needs 10 days to mature)
SEED_BUFFER = 5           # melon seeds to keep in stock
MONEY_BUFFER = 200        # keep this much cash on hand before discretionary spend

TURNS_PER_DAY = 24

# priorities
P_WATER_CRIT = 5
P_HARVEST = 4
P_WATER_BONUS = 3
P_PLANT = 2
P_DIG = 1


def _in_bounds(x, y, n):
    return 0 <= x < n and 0 <= y < n


def _step_toward(fx, fy, tx, ty, n):
    """Return a move op stepping one tile from (fx,fy) toward (tx,ty)."""
    dx, dy = tx - fx, ty - fy
    # move along the larger axis first
    if abs(dx) >= abs(dy) and dx != 0:
        return "EAST" if dx > 0 else "WEST"
    if dy != 0:
        return "SOUTH" if dy > 0 else "NORTH"
    if dx != 0:
        return "EAST" if dx > 0 else "WEST"
    return "PASS"


def _manhattan(ax, ay, bx, by):
    return abs(ax - bx) + abs(ay - by)


def agent(obs):
    player = obs["player"]
    me = obs["farms"][player]
    priv = obs["private"]
    day = obs["day"]
    hour = obs["hour"]
    tiles = me["tiles"]
    n = len(tiles)
    money = me["money"]
    seeds = priv.get("seeds", {})
    shed = priv.get("shed", {})

    market = []

    # --- gather owned tiles & current melon state --------------------------
    owned = []          # (x, y, tile)
    active_melons = 0
    for y in range(n):
        for x in range(n):
            t = tiles[y][x]
            if t == "LOCKED":
                continue
            owned.append((x, y, t))
            if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == CROP:
                active_melons += 1

    empty_tiles = [(x, y) for (x, y, t) in owned if t is None]
    weed_tiles = [(x, y) for (x, y, t) in owned if isinstance(t, dict) and t.get("kind") == "WEED"]

    can_plant_more = active_melons < MAX_ACTIVE and day <= PLANT_DEADLINE_DAY
    plant_slots = max(0, MAX_ACTIVE - active_melons) if can_plant_more else 0

    # --- build task list ----------------------------------------------------
    tasks = []  # dict: x, y, op (list), prio
    for (x, y, t) in owned:
        if not (isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == CROP):
            continue
        age = day - t["planted_day"]
        watered = t.get("watered_today", False)
        yu = t.get("yield_units", 0)
        # harvest when mature
        if yu > 0 and age >= FIRST_YIELD_DAY and (yu >= MAX_YIELD or age >= FIRST_YIELD_DAY + 1):
            tasks.append({"x": x, "y": y, "op": ["HARVEST"], "prio": P_HARVEST})
            continue
        if not watered:
            if t.get("consecutive_unwatered", 0) >= 1:
                tasks.append({"x": x, "y": y, "op": ["WATER"], "prio": P_WATER_CRIT})
            elif WINDOW_START <= age <= MAX_YIELD_DAY and yu < MAX_YIELD:
                tasks.append({"x": x, "y": y, "op": ["WATER"], "prio": P_WATER_BONUS})

    # planting tasks on empty tiles (bounded by slots)
    if plant_slots > 0:
        for (x, y) in empty_tiles[:plant_slots]:
            tasks.append({"x": x, "y": y, "op": ["PLANT", CROP], "prio": P_PLANT})
        # reclaim weeds if we still want more room
        remaining = plant_slots - len(empty_tiles)
        if remaining > 0:
            for (x, y) in weed_tiles[:remaining]:
                tasks.append({"x": x, "y": y, "op": ["DIG"], "prio": P_DIG})

    # --- unit list ----------------------------------------------------------
    units = [tuple(me["farmer"])] + [tuple(p) for p in me.get("hands", [])]
    n_units = len(units)
    assigned = [None] * n_units  # task index per unit

    # assign tasks greedily: highest priority first, to nearest free unit
    tasks.sort(key=lambda tk: -tk["prio"])
    used_tiles = set()
    for ti, tk in enumerate(tasks):
        if (tk["x"], tk["y"]) in used_tiles:
            continue
        best_u, best_d = None, None
        for ui in range(n_units):
            if assigned[ui] is not None:
                continue
            ux, uy = units[ui]
            d = _manhattan(ux, uy, tk["x"], tk["y"])
            if best_d is None or d < best_d:
                best_d, best_u = d, ui
        if best_u is not None:
            assigned[best_u] = ti
            used_tiles.add((tk["x"], tk["y"]))
        if all(a is not None for a in assigned):
            break

    # --- resolve each unit's action ----------------------------------------
    ops = [["PASS"] for _ in range(n_units)]
    plants_this_turn = 0
    seeds_avail = seeds.get(CROP, 0)
    for ui in range(n_units):
        ti = assigned[ui]
        if ti is None:
            ops[ui] = ["PASS"]
            continue
        tk = tasks[ti]
        ux, uy = units[ui]
        if (ux, uy) == (tk["x"], tk["y"]):
            op = tk["op"]
            if op[0] == "PLANT":
                # respect atomic-plant rule: don't exceed available seeds
                if plants_this_turn < seeds_avail:
                    plants_this_turn += 1
                    ops[ui] = op
                else:
                    ops[ui] = ["PASS"]
            else:
                ops[ui] = op
        else:
            ops[ui] = [_step_toward(ux, uy, tk["x"], tk["y"], n)]

    farmer_op = ops[0]
    hands_ops = ops[1:]

    # --- market orders ------------------------------------------------------
    # 1) hire hands at the start of the day
    if hour == 0:
        already = me.get("hires_today", 0)
        to_hire = max(0, TARGET_HANDS - already)
        for _ in range(to_hire):
            market.append(["HIRE"])

    # 2) sell all melons sitting in the shed (price only recovers via town, so
    #    holding is pointless; selling every turn also prevents shed overflow)
    melon_in_shed = shed.get(CROP, 0)
    if melon_in_shed > 0:
        market.append(["SELL", CROP, melon_in_shed])

    # 3) keep a seed buffer for planting
    if can_plant_more:
        want = min(SEED_BUFFER, plant_slots)
        need = want - seeds.get(CROP, 0)
        if need > 0 and money >= MONEY_BUFFER + need * SEED_COST:
            market.append(["BUY_SEED", CROP, need])

    return {"farmer": farmer_op, "hands": hands_ops, "market": market[:10]}
