"""fastsim: pure-stdlib re-implementation of the kaggriculture state transition.

Mirrors kaggle_environments/envs/kaggriculture/kaggriculture.py step-for-step
(unit actions, atomic PLANT validation, lockstep market, town consumption,
plant decay, end-of-day refresh) with a compact state layout:

  * tiles: flat list of 100 entries per farm, tiles[y*10+x]
        0 = EMPTY (engine None), 1 = LOCKED, 2 = WEED, 3 = empty COOP,
        4 = empty PASTURE, list = PLANT / ANIMAL record (see P_* / A_* indices)
  * units: list of [x, y]; units[0] is the farmer, units[1:] the hands
  * private: shed dict (12 keys), seeds dict (5 keys), invs list of dicts
  * market: inventory dict (9 keys); prices are derived on demand

Randomness (weeds + shop draw) is injectable:
  * weed_seed=None (default): no weed spawn; shop unlocks come from
    `forced_shops` (list indexed by unlock ordinal; missing -> no unlock)
  * weed_seed=<engine env.info['seed']>: bit-exact replication of the engine's
    random.Random((seed*1_000_003) ^ day) weed spawn and shop draw.

Default configuration only (boardSize 10, turnsPerDay 24, shedCapacity 100,
maxMarketOrdersPerTurn 10, farmHandCostMult 1, default MARKET_PARAMS).
"""
import math
import random

# ----------------------------------------------------------------------------
# Constants (copied from the engine)
# ----------------------------------------------------------------------------
CROPS = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}
ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}
PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]
PRODUCT_SET = frozenset(PRODUCTS)
TOWN_CENTER_PRODUCTS = [p for p in PRODUCTS if p != "FERTILIZER"]
SHED_ITEMS = PRODUCTS + list(ANIMALS)

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
SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
SHOP_NAMES_SORTED = sorted(SHOPS)
# shop -> list of (item, amount) consumed per tick
SHOP_DRAW = {name: [(it, 2 if len(items) == 1 else 1) for it in items] for name, items in SHOPS.items()}
MAX_SHOP_INSTANCES = 8

BOARD = 10
HALF = 5
TPD = 24
SHED_CAP = 100
MAX_ORDERS = 10
WEED_CHANCE = 0.005
SHOP_UNLOCK_INTERVAL = 3
SHOP_SELL_INTERVAL = 4
CENTER_SELL_INTERVAL = 24
EPISODE_STEPS = 720
STARTING_MONEY = 3000.0

LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]
MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}

SHED_TILES = [(HALF - 1, HALF - 1), (HALF, HALF - 1), (HALF - 1, HALF), (HALF, HALF)]  # NWSE
SHED_IDX = frozenset(y * BOARD + x for (x, y) in SHED_TILES)
SPAWN = (HALF - 1, HALF - 1)  # (4, 4): first shed tile in the NW quadrant
QUAD = [("N" if (i // BOARD) < HALF else "S") + ("W" if (i % BOARD) < HALF else "E") for i in range(BOARD * BOARD)]
QUAD_IDX = {q: [i for i in range(BOARD * BOARD) if QUAD[i] == q] for q in ("NW", "NE", "SW", "SE")}

# Tile codes
EMPTY, LOCKED, WEED, COOP, PASTURE = 0, 1, 2, 3, 4
KIND_PLANT, KIND_ANIMAL = 5, 6
STRUCT_CODE = {"COOP": COOP, "PASTURE": PASTURE}
ANIMAL_STRUCT = {a: STRUCT_CODE[d["structure"]] for a, d in ANIMALS.items()}
STRUCT_NAME = {COOP: "COOP", PASTURE: "PASTURE"}
# plant record: [KIND_PLANT, crop, planted_day, watered_today, consecutive_unwatered, yield_units, max_lifespan_step, fertilized_until_day]
P_CROP, P_PLANTED, P_WATERED, P_UNWATERED, P_YIELD, P_MLS, P_FERT = 1, 2, 3, 4, 5, 6, 7
# animal record: [KIND_ANIMAL, animal, placed_day, yield_units, consecutive_unfed, fed_today, cared_today, fertilizer_available, pending_care_bonus]
A_ANIMAL, A_PLACED, A_YIELD, A_UNFED, A_FED, A_CARED, A_FERT, A_PCB = 1, 2, 3, 4, 5, 6, 7, 8

PASS_ACTION = ["PASS"]


# ----------------------------------------------------------------------------
# Market pricing (bit-exact with the engine)
# ----------------------------------------------------------------------------
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


def _mp_table():
    t = {}
    for item, p in MARKET_PARAMS.items():
        base, I0, T = p["base"], p["I0"], p["T"]
        bf, af = p["below_func"], p["above_func"]
        bamp = p["below_target"] * base / _shape(bf, T, T)
        aamp = p["above_target"] * base / _shape(af, T, T)
        t[item] = (base, I0, T, bf, bamp, af, aamp)
    return t


_MP = _mp_table()


def market_price(item, inventory):
    base, I0, T, bf, bamp, af, aamp = _MP[item]
    if inventory < I0:
        price = base + bamp * _shape(bf, I0 - inventory, T)
    else:
        price = base - aamp * _shape(af, inventory - I0, T)
    r = int(round(price))
    return r if r > PRICE_FLOOR else PRICE_FLOOR


def market_prices(inv):
    return {item: market_price(item, inv[item]) for item in PRODUCTS}


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


HIRE_COST = [_fib(n) for n in range(40)]


# ----------------------------------------------------------------------------
# State containers
# ----------------------------------------------------------------------------
class Farm:
    __slots__ = ("money", "tiles", "units", "unlocked", "hires_today", "decay_from")

    def __init__(self):
        self.money = STARTING_MONEY
        self.tiles = [EMPTY if QUAD[i] == "NW" else LOCKED for i in range(BOARD * BOARD)]
        self.units = [list(SPAWN)]
        self.unlocked = ["NW"]
        self.hires_today = 0
        # earliest max_lifespan_step among plants (lower bound); the decay scan is
        # skipped while step < decay_from. Stale-low values only cost a scan.
        self.decay_from = 1 << 30

    def recompute_decay_from(self):
        m = 1 << 30
        for t in self.tiles:
            if type(t) is list and t[0] == KIND_PLANT and 0 <= t[P_MLS] < m:
                m = t[P_MLS]
        self.decay_from = m

    def clone(self):
        f = Farm.__new__(Farm)
        f.money = self.money
        f.tiles = [t if type(t) is int else t[:] for t in self.tiles]
        f.units = [u[:] for u in self.units]
        f.unlocked = self.unlocked[:]
        f.hires_today = self.hires_today
        f.decay_from = self.decay_from
        return f


class Private:
    __slots__ = ("shed", "seeds", "invs")

    def __init__(self):
        self.shed = {item: 0 for item in SHED_ITEMS}
        self.seeds = {crop: 0 for crop in CROPS}
        self.invs = [{}]

    def clone(self):
        p = Private.__new__(Private)
        p.shed = dict(self.shed)
        p.seeds = dict(self.seeds)
        p.invs = [dict(d) for d in self.invs]
        return p


def _inv_add(inv, item, n=1):
    inv[item] = inv.get(item, 0) + n


def _inv_take(inv, item, n=1):
    if inv.get(item, 0) < n:
        return False
    inv[item] -= n
    if inv[item] == 0:
        del inv[item]
    return True


class FastState:
    """Full two-player game state plus the transition."""
    __slots__ = ("step", "farms", "privs", "minv", "shops", "forced_shops", "weed_seed", "patched_weeds")

    def __init__(self, forced_shops=None, weed_seed=None):
        self.step = 0
        self.farms = [Farm(), Farm()]
        self.privs = [Private(), Private()]
        self.minv = {item: MARKET_I0 for item in PRODUCTS}
        self.shops = []
        self.forced_shops = list(forced_shops) if forced_shops else []
        self.weed_seed = weed_seed
        self.patched_weeds = 0

    # -- copying ---------------------------------------------------------------
    def clone(self):
        s = FastState.__new__(FastState)
        s.step = self.step
        s.farms = [f.clone() for f in self.farms]
        s.privs = [p.clone() for p in self.privs]
        s.minv = dict(self.minv)
        s.shops = self.shops[:]
        s.forced_shops = self.forced_shops
        s.weed_seed = self.weed_seed
        s.patched_weeds = self.patched_weeds
        return s

    # -- derived views -----------------------------------------------------------
    @property
    def day(self):
        return self.step // TPD

    @property
    def hour(self):
        return self.step % TPD

    def prices(self):
        return market_prices(self.minv)

    # -- main transition ---------------------------------------------------------
    def apply(self, actions):
        """actions: [action_p0, action_p1] in engine format
        ({"farmer": [...], "hands": [[...], ...], "market": [[...], ...]})."""
        step = self.step
        day = step // TPD
        farms = self.farms
        privs = self.privs
        for i in range(2):
            action = actions[i]
            if not isinstance(action, dict):
                action = {}
            farmer_action = action.get("farmer", PASS_ACTION)
            hands_actions = action.get("hands", [])
            if not isinstance(hands_actions, list):
                hands_actions = []
            farm = farms[i]
            priv = privs[i]
            # Atomic PLANT validation
            blocked = None
            demand = None
            for a in hands_actions:
                if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT":
                    if demand is None:
                        demand = {}
                    demand[a[1]] = demand.get(a[1], 0) + 1
            a = farmer_action
            if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT":
                if demand is None:
                    demand = {}
                demand[a[1]] = demand.get(a[1], 0) + 1
            if demand is not None:
                seeds = priv.seeds
                blocked = {crop for crop, n in demand.items() if n > seeds.get(crop, 0)}
                if not blocked:
                    blocked = None
            if blocked is not None and isinstance(farmer_action, list) and len(farmer_action) >= 2 \
                    and farmer_action[0] == "PLANT" and farmer_action[1] in blocked:
                farmer_action = PASS_ACTION
            self._unit(farm, priv, 0, farmer_action, day)
            for h, ha in enumerate(hands_actions):
                if blocked is not None and isinstance(ha, list) and len(ha) >= 2 and ha[0] == "PLANT" and ha[1] in blocked:
                    ha = PASS_ACTION
                self._unit(farm, priv, h + 1, ha, day)

        self._market(actions)
        self._town(step)
        for farm in farms:
            self._decay(farm, step)
        if (step + 1) % TPD == 0:
            self._end_of_day(day)
        self.step = step + 1

    # -- unit actions ------------------------------------------------------------
    def _unit(self, farm, priv, idx, action, day):
        if not isinstance(action, list) or not action:
            return
        op = action[0]
        units = farm.units
        if idx >= len(units):
            return
        pos = units[idx]
        x = pos[0]
        y = pos[1]
        invs = priv.invs
        while len(invs) <= idx:
            invs.append({})
        inv = invs[idx]

        mv = MOVES.get(op)
        if mv is not None:
            nx = x + mv[0]
            ny = y + mv[1]
            if 0 <= nx < BOARD and 0 <= ny < BOARD:
                pos[0] = nx
                pos[1] = ny
            return
        if op == "PASS":
            return

        ti = y * BOARD + x
        tiles = farm.tiles
        tile = tiles[ti]

        if op == "DROP":
            if ti not in SHED_IDX:
                return
            shed = priv.shed
            for item, n in list(inv.items()):
                if n <= 0:
                    del inv[item]
                    continue
                room = SHED_CAP - sum(shed.values())
                if room < 0:
                    room = 0
                take = n if n < room else room
                if take > 0:
                    shed[item] = shed.get(item, 0) + take
                del inv[item]
            return

        if op == "PICKUP":
            if ti not in SHED_IDX:
                return
            if len(action) < 2:
                return
            item = action[1]
            n = int(action[2]) if len(action) >= 3 else 1
            if n <= 0:
                return
            available = priv.shed.get(item, 0)
            if available < n:
                n = available
            if n <= 0:
                return
            priv.shed[item] -= n
            inv[item] = inv.get(item, 0) + n
            return

        if op == "PLACE":
            if len(action) < 2:
                return
            item = action[1]
            if item in ANIMALS and type(tile) is int and tile == ANIMAL_STRUCT[item]:
                if _inv_take(inv, item, 1):
                    tiles[ti] = [KIND_ANIMAL, item, day, 0, 0, False, False, False, 0]
                return
            if ti in SHED_IDX:
                n = int(action[2]) if len(action) >= 3 else 1
                if n <= 0:
                    return
                have = inv.get(item, 0)
                if have < n:
                    n = have
                if n <= 0:
                    return
                shed = priv.shed
                room = SHED_CAP - sum(shed.values())
                if room < 0:
                    room = 0
                if room < n:
                    n = room
                if n <= 0:
                    return
                inv[item] -= n
                if inv[item] == 0:
                    del inv[item]
                shed[item] = shed.get(item, 0) + n
            return

        if tile == LOCKED and type(tile) is int:
            return

        if op == "PLANT":
            if len(action) < 2:
                return
            crop = action[1]
            if crop not in CROPS:
                return
            if tile != EMPTY or type(tile) is not int:
                return
            seeds = priv.seeds
            if seeds.get(crop, 0) <= 0:
                return
            seeds[crop] -= 1
            cd = CROPS[crop]
            if cd["ongoing"]:
                tiles[ti] = [KIND_PLANT, crop, day, False, 1, 0, -1, -1]
            else:
                mls = (day + cd["max_yield_day"] + 1) * TPD
                tiles[ti] = [KIND_PLANT, crop, day, False, 1, 1, mls, -1]
                if mls < farm.decay_from:
                    farm.decay_from = mls
            return

        if op == "WATER":
            if type(tile) is not list or tile[0] != KIND_PLANT:
                return
            if tile[P_WATERED]:
                return
            tile[P_WATERED] = True
            cd = CROPS[tile[P_CROP]]
            if not cd["ongoing"]:
                age = day - tile[P_PLANTED]
                myd = cd["max_yield_day"]
                if (myd + 1) // 2 <= age <= myd:
                    bonus = 2 if tile[P_FERT] >= day else 1
                    y_ = tile[P_YIELD] + bonus
                    m = cd["max_yield"]
                    tile[P_YIELD] = y_ if y_ < m else m
            return

        if op == "HARVEST":
            if type(tile) is not list:
                return
            if tile[0] == KIND_PLANT:
                if tile[P_YIELD] <= 0:
                    return
                cd = CROPS[tile[P_CROP]]
                if day - tile[P_PLANTED] < cd["first_yield_day"]:
                    return
                units_ = tile[P_YIELD]
                tile[P_YIELD] = 0
                crop = tile[P_CROP]
                inv[crop] = inv.get(crop, 0) + units_
                if not cd["ongoing"]:
                    tiles[ti] = EMPTY
            else:
                if tile[A_YIELD] <= 0:
                    return
                units_ = tile[A_YIELD]
                tile[A_YIELD] = 0
                prod = ANIMALS[tile[A_ANIMAL]]["product"]
                inv[prod] = inv.get(prod, 0) + units_
            return

        if op == "FERTILIZE":
            if type(tile) is not list or tile[0] != KIND_PLANT:
                return
            if not _inv_take(inv, "FERTILIZER", 1):
                return
            if tile[P_FERT] < day + 2:
                tile[P_FERT] = day + 2
            return

        if op == "DIG":
            if type(tile) is int:
                if tile == EMPTY:
                    return
                tiles[ti] = EMPTY
                return
            if tile[0] == KIND_ANIMAL:
                return
            tiles[ti] = EMPTY
            return

        if op == "BUILD_COOP":
            if type(tile) is int and tile == EMPTY:
                tiles[ti] = COOP
            return

        if op == "BUILD_PASTURE":
            if type(tile) is int and tile == EMPTY:
                tiles[ti] = PASTURE
            return

        if op == "FEED":
            if type(tile) is not list or tile[0] != KIND_ANIMAL:
                return
            if tile[A_FED]:
                return
            if not _inv_take(inv, "WHEAT", 1):
                return
            tile[A_FED] = True
            return

        if op == "COLLECT_FERTILIZER":
            if type(tile) is not list or tile[0] != KIND_ANIMAL:
                return
            if not tile[A_FERT]:
                return
            tile[A_FERT] = False
            inv["FERTILIZER"] = inv.get("FERTILIZER", 0) + 1
            return

        if op == "CARE":
            if type(tile) is not list or tile[0] != KIND_ANIMAL:
                return
            if tile[A_CARED]:
                return
            tile[A_CARED] = True
            return

    # -- market --------------------------------------------------------------------
    @staticmethod
    def _parse_order(order):
        if not isinstance(order, list) or not order:
            return None
        op = order[0]
        if op == "HIRE":
            return ["HIRE", None, 0]
        if op == "BUY_LAND":
            return ["BUY_LAND", None, 0]
        if op in ("BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"):
            if len(order) < 3:
                return None
            try:
                n = int(order[2])
            except (TypeError, ValueError):
                return None
            if n <= 0:
                return None
            return [op, order[1], n]
        return None

    def _market(self, actions):
        queues = []
        for i in range(2):
            action = actions[i]
            m = action.get("market", []) if isinstance(action, dict) else []
            q = list(m) if isinstance(m, list) else []
            queues.append(q[:MAX_ORDERS])
        max_len = len(queues[0])
        if len(queues[1]) > max_len:
            max_len = len(queues[1])
        if max_len == 0:
            return
        minv = self.minv
        farms = self.farms
        privs = self.privs
        parse = self._parse_order
        for i in range(max_len):
            ostates = [parse(q[i]) if i < len(q) else None for q in queues]
            for pid in range(2):
                os_ = ostates[pid]
                if os_ is None:
                    continue
                if os_[0] == "HIRE":
                    self._hire(farms[pid], privs[pid])
                    ostates[pid] = None
                elif os_[0] == "BUY_LAND":
                    self._buy_land(farms[pid])
                    ostates[pid] = None
            idx_esc = 0
            while True:
                idx_esc += 1
                if idx_esc >= 100_000:
                    break
                quoted = [None, None]
                for pid in range(2):
                    os_ = ostates[pid]
                    if os_ is None or os_[2] <= 0:
                        continue
                    op = os_[0]
                    item = os_[1]
                    if op == "SELL" and item in PRODUCT_SET:
                        quoted[pid] = ("SELL", item, market_price(item, minv[item]), os_)
                    elif op == "BUY_PRODUCT" and (item == "WHEAT" or item == "FERTILIZER"):
                        quoted[pid] = ("BUY_PRODUCT", item, market_price(item, minv[item] - 1), os_)
                    elif op == "BUY_SEED" and item in CROPS:
                        quoted[pid] = ("BUY_SEED", item, CROPS[item]["seed"], os_)
                    elif op == "BUY_ANIMAL" and item in ANIMALS:
                        quoted[pid] = ("BUY_ANIMAL", item, ANIMALS[item]["cost"], os_)
                    else:
                        ostates[pid] = None
                if quoted[0] is None and quoted[1] is None:
                    break
                committed_any = False
                for pid in range(2):
                    q = quoted[pid]
                    if q is None:
                        continue
                    op, item, price, os_ = q
                    if self._commit(op, item, price, farms[pid], privs[pid]):
                        os_[2] -= 1
                        committed_any = True
                    else:
                        ostates[pid] = None
                if not committed_any:
                    break

    def _commit(self, op, item, price, farm, priv):
        shed = priv.shed
        if op == "SELL":
            if shed.get(item, 0) <= 0:
                return False
            shed[item] -= 1
            farm.money += price
            if price > 1:
                self.minv[item] += 1
            return True
        if op == "BUY_PRODUCT":
            if farm.money < price:
                return False
            if sum(shed.values()) >= SHED_CAP:
                return False
            farm.money -= price
            shed[item] = shed.get(item, 0) + 1
            self.minv[item] -= 1
            return True
        if op == "BUY_SEED":
            if farm.money < price:
                return False
            farm.money -= price
            priv.seeds[item] = priv.seeds.get(item, 0) + 1
            return True
        if op == "BUY_ANIMAL":
            if farm.money < price:
                return False
            if sum(shed.values()) >= SHED_CAP:
                return False
            farm.money -= price
            shed[item] = shed.get(item, 0) + 1
            return True
        return False

    @staticmethod
    def _hire(farm, priv):
        n = farm.hires_today
        cost = HIRE_COST[n] if n < len(HIRE_COST) else _fib(n)
        if farm.money < cost:
            return
        farm.money -= cost
        farm.hires_today = n + 1
        # spawn: least-occupied shed-access tile, ties -> NWSE order
        occ = [0, 0, 0, 0]
        for u in farm.units:
            t = (u[0], u[1])
            for k in range(4):
                if SHED_TILES[k] == t:
                    occ[k] += 1
                    break
        best = 0
        for k in range(1, 4):
            if occ[k] < occ[best]:
                best = k
        farm.units.append(list(SHED_TILES[best]))
        priv.invs.append({})

    @staticmethod
    def _buy_land(farm):
        n = len(farm.unlocked) - 1
        if n >= len(LAND_ORDER):
            return
        cost = LAND_PRICES[n]
        if farm.money < cost:
            return
        farm.money -= cost
        quadrant = LAND_ORDER[n]
        farm.unlocked.append(quadrant)
        tiles = farm.tiles
        for i in QUAD_IDX[quadrant]:
            if type(tiles[i]) is int and tiles[i] == LOCKED:
                tiles[i] = EMPTY

    # -- town ----------------------------------------------------------------------
    def _town(self, step):
        minv = self.minv
        if step % SHOP_SELL_INTERVAL == 0:
            for shop in self.shops:
                for item, k in SHOP_DRAW[shop]:
                    minv[item] -= k
        if step % CENTER_SELL_INTERVAL == 0:
            for item in TOWN_CENTER_PRODUCTS:
                minv[item] -= 1

    # -- decay ---------------------------------------------------------------------
    @staticmethod
    def _decay(farm, step):
        if step < farm.decay_from:
            return
        tiles = farm.tiles
        new_min = 1 << 30
        for i in range(BOARD * BOARD):
            t = tiles[i]
            if type(t) is not list or t[0] != KIND_PLANT:
                continue
            mls = t[P_MLS]
            if mls < 0:
                continue
            if step < mls:
                if mls < new_min:
                    new_min = mls
                continue
            if (step - mls) % 2 == 0:
                t[P_YIELD] -= 1
                if t[P_YIELD] <= 0:
                    tiles[i] = WEED
                    continue
            if mls < new_min:
                new_min = mls
        farm.decay_from = new_min

    # -- end of day ------------------------------------------------------------------
    def _end_of_day(self, day):
        rng = None
        if self.weed_seed is not None:
            rng = random.Random((self.weed_seed * 1_000_003) ^ day)
        next_day = day + 1
        for pid in range(2):
            farm = self.farms[pid]
            priv = self.privs[pid]
            tiles = farm.tiles
            for i in range(BOARD * BOARD):
                t = tiles[i]
                if type(t) is not list:
                    continue
                if t[0] == KIND_PLANT:
                    was_watered = t[P_WATERED]
                    if was_watered:
                        t[P_UNWATERED] = 0
                    else:
                        t[P_UNWATERED] += 1
                    t[P_WATERED] = False
                    if t[P_UNWATERED] >= 2:
                        tiles[i] = WEED
                        continue
                    cd = CROPS[t[P_CROP]]
                    if not cd["ongoing"]:
                        continue
                    dsf = next_day - t[P_PLANTED] - cd["first_yield_day"]
                    if dsf < 0:
                        continue
                    interval = cd["interval"]
                    if dsf % interval != 0:
                        continue
                    pc = dsf // interval + 1
                    my = cd["max_yield"]
                    if pc > my:
                        continue
                    fert = was_watered and t[P_FERT] >= day
                    y_ = t[P_YIELD] + (2 if fert else 1)
                    t[P_YIELD] = y_ if y_ < my else my
                    if pc == my:
                        t[P_MLS] = (next_day + 1) * TPD
                        if t[P_MLS] < farm.decay_from:
                            farm.decay_from = t[P_MLS]
                else:
                    if t[A_FED]:
                        t[A_UNFED] = 0
                    else:
                        t[A_UNFED] += 1
                    if t[A_UNFED] >= 2:
                        tiles[i] = ANIMAL_STRUCT[t[A_ANIMAL]]
                        continue
                    a = ANIMALS[t[A_ANIMAL]]
                    dsf = next_day - t[A_PLACED] - a["first_yield_day"]
                    if dsf >= 0 and dsf % a["interval"] == 0:
                        bonus = t[A_PCB] if t[A_FED] else 0
                        y_ = t[A_YIELD] + 1 + bonus
                        mh = a["max_held"]
                        t[A_YIELD] = y_ if y_ < mh else mh
                        t[A_PCB] = 0
                    if t[A_CARED] and t[A_FED]:
                        t[A_PCB] += 1
                    t[A_FERT] = True
                    t[A_FED] = False
                    t[A_CARED] = False
            if rng is not None:
                rnd = rng.random
                for i in range(BOARD * BOARD):
                    if tiles[i] == EMPTY and type(tiles[i]) is int and rnd() < WEED_CHANCE:
                        tiles[i] = WEED
            # drop inventories to shed
            shed = priv.shed
            for inv in priv.invs:
                for item, n in list(inv.items()):
                    if n <= 0:
                        del inv[item]
                        continue
                    room = SHED_CAP - sum(shed.values())
                    if room < 0:
                        room = 0
                    take = n if n < room else room
                    if take > 0:
                        shed[item] = shed.get(item, 0) + take
                    del inv[item]
            farm.units = [list(SPAWN)]
            farm.hires_today = 0
            priv.invs = [{}]
        if next_day > 0 and next_day % SHOP_UNLOCK_INTERVAL == 0:
            k = len(self.shops)
            if k < MAX_SHOP_INSTANCES:
                if k < len(self.forced_shops) and self.forced_shops[k] is not None:
                    self.shops.append(self.forced_shops[k])
                elif rng is not None:
                    self.shops.append(rng.choice(SHOP_NAMES_SORTED))

    # -- weed patching (validation helper) -------------------------------------------
    def patch_weeds_from(self, farms_obs):
        """Copy WEED tiles that exist in the recorded farms but not in ours (used
        when weed_seed is None). Returns the number of tiles patched."""
        n = 0
        for pid in range(2):
            tiles = self.farms[pid].tiles
            rows = farms_obs[pid]["tiles"]
            for y in range(BOARD):
                row = rows[y]
                for x in range(BOARD):
                    rt = row[x]
                    if isinstance(rt, dict) and rt.get("kind") == "WEED":
                        i = y * BOARD + x
                        if type(tiles[i]) is int and tiles[i] == EMPTY:
                            tiles[i] = WEED
                            n += 1
        self.patched_weeds += n
        return n

    # -- conversion to / from engine observation format ------------------------------
    @staticmethod
    def tile_to_obs(t):
        if type(t) is int:
            if t == EMPTY:
                return None
            if t == LOCKED:
                return "LOCKED"
            if t == WEED:
                return {"kind": "WEED"}
            return {"kind": STRUCT_NAME[t]}
        if t[0] == KIND_PLANT:
            return {
                "kind": "PLANT",
                "crop": t[P_CROP],
                "planted_day": t[P_PLANTED],
                "watered_today": t[P_WATERED],
                "consecutive_unwatered": t[P_UNWATERED],
                "yield_units": t[P_YIELD],
                "max_lifespan_step": t[P_MLS],
                "fertilized_until_day": t[P_FERT],
            }
        return {
            "kind": ANIMALS[t[A_ANIMAL]]["structure"],
            "animal": t[A_ANIMAL],
            "placed_day": t[A_PLACED],
            "yield_units": t[A_YIELD],
            "consecutive_unfed": t[A_UNFED],
            "fed_today": t[A_FED],
            "cared_today": t[A_CARED],
            "fertilizer_available": t[A_FERT],
            "pending_care_bonus": t[A_PCB],
        }

    @staticmethod
    def tile_from_obs(rt):
        if rt is None:
            return EMPTY
        if rt == "LOCKED":
            return LOCKED
        kind = rt.get("kind")
        if kind == "WEED":
            return WEED
        if kind == "PLANT":
            return [KIND_PLANT, rt["crop"], rt["planted_day"], rt["watered_today"], rt["consecutive_unwatered"],
                    rt["yield_units"], rt["max_lifespan_step"], rt.get("fertilized_until_day", -1)]
        if "animal" in rt:
            return [KIND_ANIMAL, rt["animal"], rt["placed_day"], rt["yield_units"], rt["consecutive_unfed"],
                    rt["fed_today"], rt["cared_today"], rt["fertilizer_available"], rt.get("pending_care_bonus", 0)]
        return STRUCT_CODE[kind]

    def farm_obs(self, pid):
        f = self.farms[pid]
        tt = self.tile_to_obs
        return {
            "money": f.money,
            "tiles": [[tt(f.tiles[y * BOARD + x]) for x in range(BOARD)] for y in range(BOARD)],
            "farmer": list(f.units[0]),
            "hands": [list(u) for u in f.units[1:]],
            "unlocked_quadrants": list(f.unlocked),
            "hires_today": f.hires_today,
        }

    def private_obs(self, pid):
        p = self.privs[pid]
        return {"shed": dict(p.shed), "seeds": dict(p.seeds), "inventories": [dict(d) for d in p.invs]}

    def market_obs(self):
        return {"inventory": dict(self.minv), "prices": self.prices()}

    def town_obs(self):
        return {"unlocked_shops": list(self.shops)}

    @classmethod
    def from_obs(cls, farms, market, town, privates, step, forced_shops=None, weed_seed=None):
        """Build a state from engine observation dicts. `privates` is a list of two
        private dicts (opponent's may be None -> empty private)."""
        s = cls(forced_shops=forced_shops, weed_seed=weed_seed)
        s.step = step
        for pid in range(2):
            fo = farms[pid]
            f = s.farms[pid]
            f.money = float(fo["money"])
            tf = cls.tile_from_obs
            f.tiles = [tf(fo["tiles"][y][x]) for y in range(BOARD) for x in range(BOARD)]
            f.units = [list(fo["farmer"])] + [list(h) for h in fo.get("hands", [])]
            f.unlocked = list(fo["unlocked_quadrants"])
            f.hires_today = fo.get("hires_today", 0)
            f.recompute_decay_from()
            po = privates[pid] if privates is not None else None
            p = s.privs[pid]
            if po is not None:
                p.shed = {item: 0 for item in SHED_ITEMS}
                p.shed.update(po.get("shed", {}))
                p.seeds = {crop: 0 for crop in CROPS}
                p.seeds.update(po.get("seeds", {}))
                p.invs = [dict(d) for d in po.get("inventories", [{}])]
            while len(p.invs) < len(f.units):
                p.invs.append({})
        s.minv = {item: market["inventory"][item] for item in PRODUCTS}
        s.shops = list(town.get("unlocked_shops", []))
        return s


# ----------------------------------------------------------------------------
# Market-only lookahead (market + town transition, no farm)
# ----------------------------------------------------------------------------
def market_only_rollout(minv, shops, step, n_steps, sell_plan, forced_shops=None):
    """Simulate only market inventory + town consumption for `n_steps` steps starting
    at engine step `step`, executing our own SELL orders from `sell_plan`
    (dict: step_offset -> list of (item, n)). Opponent orders are ignored.
    Returns (revenue, final_inventory_dict)."""
    inv = dict(minv)
    shops = list(shops)
    revenue = 0
    for k in range(n_steps):
        s = step + k
        orders = sell_plan.get(k)
        if orders:
            for item, n in orders:
                for _ in range(n):
                    price = market_price(item, inv[item])
                    revenue += price
                    if price > 1:
                        inv[item] += 1
        if s % SHOP_SELL_INTERVAL == 0:
            for shop in shops:
                for item, m in SHOP_DRAW[shop]:
                    inv[item] -= m
        if s % CENTER_SELL_INTERVAL == 0:
            for item in TOWN_CENTER_PRODUCTS:
                inv[item] -= 1
        if (s + 1) % TPD == 0:
            nd = (s + 1) // TPD
            if nd % SHOP_UNLOCK_INTERVAL == 0 and len(shops) < MAX_SHOP_INSTANCES and forced_shops:
                kk = len(shops)
                if kk < len(forced_shops) and forced_shops[kk] is not None:
                    shops.append(forced_shops[kk])
    return revenue, inv
