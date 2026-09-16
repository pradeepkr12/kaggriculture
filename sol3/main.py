"""Kaggriculture agent (sol3) — melon+strawberry hybrid with throttled shop-sink selling.

Strategy (found by CEM self-play optimization, see optimize.py / REPORT.md)
--------------------------------------------------------------------------
Two independent revenue streams the opponent cannot both contest:

  1. MELON (~20% of tiles): the highest-base product ($250) that NO town shop
     consumes. Uncontested it yields a huge pie; contested (a melon-dumping
     opponent) it splits evenly -- so playing some melon *neutralizes* a melon
     rival instead of losing the pie to them.
  2. STRAWBERRY (~77% of tiles): base $120 and demanded by 4 shop types. We sell
     it THROTTLED -- each turn only as many units as keep the price >= 0.71*base,
     read from the live shared market inventory. The town shops drain inventory
     every 4 turns, reopening room, so we ride a near-base price all season
     instead of crashing it. An opponent who *dumps* strawberry crashes their own
     price; our throttle holds ours, so contest only helps us.

Labor is the bottleneck (one action/unit/turn, moving costs turns), so we hire 5
cheap hands each morning (fib cost 1,1,2,3,5) and buy 1 extra quadrant (NE) for
room. A greedy multi-unit assignment sends each unit to the highest-value nearby
task: survival-water > harvest > bonus-water > plant > dig.

Validated on held-out seeds: beats sell-first melon 16-0 (+11k), a melon+straw
hybrid 15-1 (+12k), a strawberry-flooder 16-0 (+22k), and all builtins; the
self-mirror is exactly even (no exploit). Nets ~32k even in the worst case.
"""
import math

LAST_DAY = 29

# ---- baked strategy (resolved from the CEM-optimized vector) ----------------
FRACS = {
    "MELON": 0.19682017132398247,
    "CARROT": 0.007631546228391229,
    "TOMATO": 0.007631546228391229,
    "WHEAT": 0.013360338116782947,
    "STRAWBERRY": 0.7745563981024521,
}
CROP_LIST = ["MELON", "CARROT", "TOMATO", "WHEAT", "STRAWBERRY"]
TARGET_HANDS = 5
LAND_TARGET = 1
TILE_BUDGET = 42
SELL_THRESH = 0.71

LAND_PRICES = [1000, 2000, 4000]

CROPS = {
    "WHEAT":      {"seed": 10,  "fy": 2,  "myd": 4,  "interval": 0, "maxy": 6, "ongoing": False},
    "CARROT":     {"seed": 20,  "fy": 2,  "myd": 3,  "interval": 0, "maxy": 4, "ongoing": False},
    "TOMATO":     {"seed": 50,  "fy": 8,  "myd": 8,  "interval": 1, "maxy": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "fy": 10, "myd": 10, "interval": 2, "maxy": 4, "ongoing": True},
    "MELON":      {"seed": 80,  "fy": 10, "myd": 12, "interval": 0, "maxy": 6, "ongoing": False},
}
for _c, _d in CROPS.items():
    _d["window_start"] = (_d["myd"] + 1) // 2
    if _d["ongoing"]:
        _d["target_yield"] = _d["maxy"]
        _d["deadline"] = LAST_DAY - _d["fy"]
    else:
        _d["target_yield"] = min(_d["maxy"], 1 + (_d["myd"] - _d["window_start"] + 1))
        _d["deadline"] = LAST_DAY - _d["myd"]

# ---- market model (ported from the engine, for the sell throttle) -----------
MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0
MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "T": 450, "below_func": "hinge",  "below_target": 1.00, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "T": 200, "below_func": "hinge",  "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "T": 332, "below_func": "hinge",  "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}
# melon has no shop sink -> dump it (threshold 0); everything else is throttled.
SELLABLE = ["MELON", "WOOL", "MILK", "STRAWBERRY", "TOMATO", "EGG", "CARROT", "WHEAT", "FERTILIZER"]

# priorities
P_WATER_CRIT = 6
P_HARVEST = 5
P_WATER_BONUS = 4
P_PLANT = 3
P_DIG = 1


def _shape(func, x, T=None):
    x = max(0.0, x)
    if func == "linear": return x
    if func == "sq":     return x * x
    if func == "sqrt":   return math.sqrt(x)
    if func == "log":    return math.log(1.0 + x)
    if func == "log10":  return math.log10(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def _market_price(item, inventory):
    p = MARKET_PARAMS[item]
    base, T = p["base"], p["T"]
    if inventory < MARKET_I0:
        amp = p["below_target"] * base / _shape(p["below_func"], T, T)
        price = base + amp * _shape(p["below_func"], MARKET_I0 - inventory, T)
    else:
        amp = p["above_target"] * base / _shape(p["above_func"], T, T)
        price = base - amp * _shape(p["above_func"], inventory - MARKET_I0, T)
    return max(PRICE_FLOOR, int(round(price)))


def _sellable_qty(item, inventory, thresh_frac, cap):
    """Largest k <= cap with _market_price(inventory + k - 1) >= thresh_frac*base."""
    if cap <= 0:
        return 0
    thr = thresh_frac * MARKET_PARAMS[item]["base"]
    lo, hi = 0, cap
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _market_price(item, inventory + mid - 1) >= thr:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _step_toward(fx, fy, tx, ty):
    dx, dy = tx - fx, ty - fy
    if abs(dx) >= abs(dy) and dx != 0:
        return "EAST" if dx > 0 else "WEST"
    if dy != 0:
        return "SOUTH" if dy > 0 else "NORTH"
    if dx != 0:
        return "EAST" if dx > 0 else "WEST"
    return "PASS"


def _dist(ax, ay, bx, by):
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
    mkt_inv = (obs.get("market", {}) or {}).get("inventory", {})

    owned_empty, weeds, plants = [], [], []
    crop_count = {c: 0 for c in CROP_LIST}
    for y in range(n):
        for x in range(n):
            t = tiles[y][x]
            if t == "LOCKED":
                continue
            if t is None:
                owned_empty.append((x, y))
            elif isinstance(t, dict):
                k = t.get("kind")
                if k == "WEED":
                    weeds.append((x, y))
                elif k == "PLANT":
                    c = t.get("crop")
                    if c in crop_count:
                        crop_count[c] += 1
                        plants.append((x, y, t, c))

    total_owned = len(owned_empty) + len(weeds) + sum(crop_count.values())
    budget = min(TILE_BUDGET, total_owned + 40)
    targets = {c: int(round(FRACS[c] * budget)) for c in CROP_LIST}

    # ---- tasks ------------------------------------------------------------
    tasks = []
    for (x, y, t, c) in plants:
        cd = CROPS[c]
        age = day - t["planted_day"]
        watered = t.get("watered_today", False)
        yu = t.get("yield_units", 0)
        if yu > 0 and age >= cd["fy"]:
            if cd["ongoing"]:
                tasks.append((P_HARVEST, x, y, ["HARVEST"]))
            elif yu >= cd["target_yield"] or age >= cd["myd"]:
                tasks.append((P_HARVEST, x, y, ["HARVEST"]))
                continue
        if not watered:
            if t.get("consecutive_unwatered", 0) >= 1:
                tasks.append((P_WATER_CRIT, x, y, ["WATER"]))
            elif (not cd["ongoing"] and cd["window_start"] <= age <= cd["myd"]
                  and yu < cd["target_yield"]):
                tasks.append((P_WATER_BONUS, x, y, ["WATER"]))

    deficits = {c: targets[c] - crop_count[c] for c in CROP_LIST}
    plantable = [c for c in CROP_LIST if deficits[c] > 0 and day <= CROPS[c]["deadline"]]
    plantable.sort(key=lambda c: -deficits[c])
    plant_plan = {}
    pi = 0
    empties = list(owned_empty)
    defc = dict(deficits)
    while empties and plantable:
        c = plantable[pi % len(plantable)]
        if defc[c] > 0:
            plant_plan[empties.pop()] = c
            defc[c] -= 1
        pi += 1
        if all(defc[c] <= 0 for c in plantable):
            break
    for (x, y), c in plant_plan.items():
        tasks.append((P_PLANT, x, y, ["PLANT", c]))
    if sum(max(0, d) for d in deficits.values()) > len(owned_empty):
        for (x, y) in weeds:
            tasks.append((P_DIG, x, y, ["DIG"]))

    # ---- assign to units --------------------------------------------------
    units = [tuple(me["farmer"])] + [tuple(q) for q in me.get("hands", [])]
    nu = len(units)
    assigned = [None] * nu
    tasks.sort(key=lambda tk: -tk[0])
    used = set()
    for tk in tasks:
        _, tx, ty, op = tk
        if (tx, ty) in used:
            continue
        best_u, best_d = None, None
        for ui in range(nu):
            if assigned[ui] is not None:
                continue
            ux, uy = units[ui]
            d = _dist(ux, uy, tx, ty)
            if best_d is None or d < best_d:
                best_d, best_u = d, ui
        if best_u is not None:
            assigned[best_u] = tk
            used.add((tx, ty))
        if all(a is not None for a in assigned):
            break

    ops = [["PASS"] for _ in range(nu)]
    plant_used = {}
    for ui in range(nu):
        tk = assigned[ui]
        if tk is None:
            continue
        _, tx, ty, op = tk
        ux, uy = units[ui]
        if (ux, uy) == (tx, ty):
            if op[0] == "PLANT":
                c = op[1]
                if seeds.get(c, 0) - plant_used.get(c, 0) > 0:
                    plant_used[c] = plant_used.get(c, 0) + 1
                    ops[ui] = op
                else:
                    ops[ui] = ["PASS"]
            else:
                ops[ui] = op
        else:
            ops[ui] = [_step_toward(ux, uy, tx, ty)]

    # ---- market orders (SELL FIRST: sell into a fresh high price) ---------
    endgame = day >= LAST_DAY
    sell_orders = []
    for item in SELLABLE:
        q = shed.get(item, 0)
        if q <= 0:
            continue
        if endgame:
            sell_orders.append(["SELL", item, q])
            continue
        k = _sellable_qty(item, mkt_inv.get(item, MARKET_I0), SELL_THRESH, q)
        if k > 0:
            sell_orders.append(["SELL", item, k])

    seed_orders = []
    for c in plantable:
        need = min(4, deficits[c]) - seeds.get(c, 0)
        if need > 0:
            cost = need * CROPS[c]["seed"]
            if money >= cost + 200:
                seed_orders.append(["BUY_SEED", c, need])
                money -= cost

    econ_orders = []
    n_extra = len(me.get("unlocked_quadrants", ["NW"])) - 1
    if n_extra < LAND_TARGET and n_extra < len(LAND_PRICES):
        if money >= LAND_PRICES[n_extra] + 300:
            econ_orders.append(["BUY_LAND"])
    if hour == 0:
        already = me.get("hires_today", 0)
        for _ in range(max(0, TARGET_HANDS - already)):
            econ_orders.append(["HIRE"])

    market_orders = (sell_orders + seed_orders + econ_orders)[:10]
    return {"farmer": ops[0], "hands": ops[1:], "market": market_orders}
