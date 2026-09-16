"""Parametrized Kaggriculture policy + action decoder — SHOP-SINK edition.

The melon monoculture (sol1/sol2) dumps a premium product that no *shop*
consumes, so its price crashes the moment we sell. sol3 abandons melon and
instead sells products the town's shops actually demand (wheat, carrot, tomato,
strawberry, and — via animals — egg/milk/wool), **throttled to the demand-sink
rate** so market inventory stays near I0 and the price stays near its high base.

The key mechanic (read from the engine): the shared market starts every product
at inventory I0=10000 (price==base). Town shops consume units every 4 turns and
the town center once per day, which *drains* inventory below I0 and pushes price
*above* base. Selling adds inventory back, pushing price down. So if we sell each
turn only up to the quantity that keeps price >= `sell_thresh * base`, we ride the
reopening room the shops create and never crash the price. The agent observation
exposes the live shared `market.inventory`, so we compute the sellable quantity
exactly rather than estimating it.

Strategy is a compact parameter vector (crop-mix weights, #hands, land, active-
tile budget, sell threshold); the decoder is a fixed greedy mechanism. ES/CEM
optimizes the vector against self-play return (arena.py).
"""
import math

LAST_DAY = 29
TURNS_PER_DAY = 24
BOARD = 10

# crop params mirrored from the engine (kaggriculture.py)
CROPS = {
    "WHEAT":      {"seed": 10,  "fy": 2,  "myd": 4,  "interval": 0, "maxy": 6, "ongoing": False},
    "CARROT":     {"seed": 20,  "fy": 2,  "myd": 3,  "interval": 0, "maxy": 4, "ongoing": False},
    "TOMATO":     {"seed": 50,  "fy": 8,  "myd": 8,  "interval": 1, "maxy": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "fy": 10, "myd": 10, "interval": 2, "maxy": 4, "ongoing": True},
    "MELON":      {"seed": 80,  "fy": 10, "myd": 12, "interval": 0, "maxy": 6, "ongoing": False},
}
CROP_LIST = ["MELON", "CARROT", "TOMATO", "WHEAT", "STRAWBERRY"]

LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]

# ---- market model (ported from engine for the sell throttle) ----------------
MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0
MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "I0": MARKET_I0, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "I0": MARKET_I0, "T": 450, "below_func": "hinge",  "below_target": 1.00, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "I0": MARKET_I0, "T": 200, "below_func": "hinge",  "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": MARKET_I0, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "I0": MARKET_I0, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "I0": MARKET_I0, "T": 332, "below_func": "hinge",  "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "I0": MARKET_I0, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "I0": MARKET_I0, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}
# products we ever try to sell, ranked by base value (sell high-value first)
SELLABLE = ["MELON", "WOOL", "MILK", "STRAWBERRY", "TOMATO", "EGG", "CARROT", "WHEAT", "FERTILIZER"]


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


def market_price(item, inventory):
    p = MARKET_PARAMS[item]
    base, I0, T = p["base"], p["I0"], p["T"]
    if inventory < I0:
        amp = p["below_target"] * base / _shape(p["below_func"], T, T)
        price = base + amp * _shape(p["below_func"], I0 - inventory, T)
    else:
        amp = p["above_target"] * base / _shape(p["above_func"], T, T)
        price = base - amp * _shape(p["above_func"], inventory - I0, T)
    return max(PRICE_FLOOR, int(round(price)))


def sellable_qty(item, inventory, thresh_frac, cap):
    """Max units we can add to `inventory` keeping price >= thresh_frac*base,
    capped at `cap`. Selling one unit raises inventory by one (unless price==1,
    but we stay well above the floor here)."""
    if cap <= 0:
        return 0
    thr = thresh_frac * MARKET_PARAMS[item]["base"]
    lo, hi = 0, cap
    # price is monotonically non-increasing in inventory, so binary-search the
    # largest k with market_price(inv+k) >= thr.
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if market_price(item, inventory + mid - 1) >= thr:
            lo = mid
        else:
            hi = mid - 1
    return lo


# derived per-crop values
for _c, _d in CROPS.items():
    _d["window_start"] = (_d["myd"] + 1) // 2
    if _d["ongoing"]:
        _d["target_yield"] = _d["maxy"]
        _d["deadline"] = LAST_DAY - _d["fy"]
    else:
        _d["target_yield"] = min(_d["maxy"], 1 + (_d["myd"] - _d["window_start"] + 1))
        _d["deadline"] = LAST_DAY - _d["myd"]

# priorities for the action decoder
P_WATER_CRIT = 6
P_HARVEST = 5
P_WATER_BONUS = 4
P_PLANT = 3
P_DIG = 1

# ---- parameter <-> vector helpers -------------------------------------------
# (name, lo, hi)
PARAM_SPEC = [
    ("w_MELON", 0.0, 6.0),
    ("w_CARROT", 0.0, 6.0),
    ("w_TOMATO", 0.0, 6.0),
    ("w_WHEAT", 0.0, 6.0),
    ("w_STRAWBERRY", 0.0, 6.0),
    ("hands", 0.0, 6.0),
    ("land", 0.0, 3.0),
    ("tile_budget", 4.0, 64.0),
    ("sell_thresh", 0.30, 0.98),
]
DIM = len(PARAM_SPEC)


def clip_vec(v):
    out = [max(lo, min(hi, x)) for x, (_, lo, hi) in zip(v, PARAM_SPEC)]
    # tolerate short vectors (back-compat): pad with midpoints
    for i in range(len(out), DIM):
        _, lo, hi = PARAM_SPEC[i]
        out.append((lo + hi) / 2)
    return out


def vec_to_params(v):
    v = clip_vec(v)
    d = {name: val for val, (name, _, _) in zip(v, PARAM_SPEC)}
    ws = [d["w_" + c] for c in CROP_LIST]
    m = max(ws)
    exps = [math.exp(w - m) for w in ws]
    s = sum(exps) or 1.0
    fracs = {c: e / s for c, e in zip(CROP_LIST, exps)}
    return {
        "fracs": fracs,
        "hands": int(round(d["hands"])),
        "land": int(round(d["land"])),
        "tile_budget": int(round(d["tile_budget"])),
        "sell_thresh": float(d["sell_thresh"]),
    }


# ---- decoder helpers --------------------------------------------------------
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


def build_agent(params_or_vec, sell_first=True):
    p = params_or_vec if isinstance(params_or_vec, dict) and "fracs" in params_or_vec \
        else vec_to_params(params_or_vec)
    fracs = p["fracs"]
    target_hands = p["hands"]
    land_target = p["land"]
    tile_budget = p["tile_budget"]
    sell_thresh = p.get("sell_thresh", 0.75)

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
        market = obs.get("market", {}) or {}
        mkt_inv = market.get("inventory", {})

        # inventory of owned tiles + current crop composition
        owned_empty = []
        weeds = []
        crop_count = {c: 0 for c in CROP_LIST}
        plants = []  # (x,y,tile,crop)
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
        budget = min(tile_budget, total_owned + 40)  # allow growth as land unlocks
        targets = {c: int(round(fracs[c] * budget)) for c in CROP_LIST}

        # ---- build tasks --------------------------------------------------
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
                xy = empties.pop()
                plant_plan[xy] = c
                defc[c] -= 1
            pi += 1
            if all(defc[c] <= 0 for c in plantable):
                break
        for (x, y), c in plant_plan.items():
            tasks.append((P_PLANT, x, y, ["PLANT", c]))
        if sum(max(0, d) for d in deficits.values()) > len(owned_empty):
            for (x, y) in weeds:
                tasks.append((P_DIG, x, y, ["DIG"]))

        # ---- assign tasks to units ---------------------------------------
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
                    have = seeds.get(c, 0) - plant_used.get(c, 0)
                    if have > 0:
                        plant_used[c] = plant_used.get(c, 0) + 1
                        ops[ui] = op
                    else:
                        ops[ui] = ["PASS"]
                else:
                    ops[ui] = op
            else:
                ops[ui] = [_step_toward(ux, uy, tx, ty)]

        # ---- market orders ------------------------------------------------
        # THROTTLED SELLING: sell each product only up to the quantity that keeps
        # its price >= sell_thresh*base (computed from the live shared market
        # inventory). This holds prices near their high base while the town shops
        # keep draining inventory. On the final day, dump everything -- unsold
        # inventory is worth nothing at the end.
        endgame = day >= LAST_DAY
        sell_orders = []
        for item in SELLABLE:
            q = shed.get(item, 0)
            if q <= 0:
                continue
            if endgame:
                sell_orders.append(["SELL", item, q])
                continue
            inv = mkt_inv.get(item, MARKET_I0)
            k = sellable_qty(item, inv, sell_thresh, q)
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
        if n_extra < land_target and n_extra < len(LAND_PRICES):
            if money >= LAND_PRICES[n_extra] + 300:
                econ_orders.append(["BUY_LAND"])
        if hour == 0 and target_hands > 0:
            already = me.get("hires_today", 0)
            for _ in range(max(0, target_hands - already)):
                econ_orders.append(["HIRE"])

        if sell_first:
            market_orders = sell_orders + seed_orders + econ_orders
        else:
            market_orders = econ_orders + seed_orders + sell_orders

        return {"farmer": ops[0], "hands": ops[1:], "market": market_orders[:10]}

    return agent
