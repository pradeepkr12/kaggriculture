"""sol7 prototype P: model-based daily production planner + opponent-aware selling,
running on top of sol5's mechanics layer (farmlib_p.py hooks).

No tuned strategy vector. Every day at hour 0 the controller:
  1. reads the town's shops -> per-product sink rate (units/day), plus the expected
     sink from the remaining random draws;
  2. estimates the opponent's per-product flow from public data: market inventory
     delta + known town consumption - our own committed sales (exact except for
     the opponent's WHEAT/FERTILIZER buys), with a prior from their visible tiles;
  3. computes the marginal SEASON value of one more cow / sheep / goose /
     strawberry tile by simulating the market inventory trajectory of that
     product under (our flow + opponent flow - sink) and pricing every unit with
     the engine's price curve, net of purchase, feed, and labor opportunity cost;
  4. buys while the marginal value is positive and culls (stops feeding) animals
     whose remaining value is negative;
  5. selling: per product, keep the market at the price-maximizing inventory given
     the sink; if the opponent is flooding faster than the sink drains, get out
     first (sell everything now).
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import farmlib_p as F

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
PRODUCTS = F.PRODUCTS
TOWN_CENTER = [p for p in PRODUCTS if p != "FERTILIZER"]
DRAW_DAYS = [2, 5, 8, 11, 14, 17, 20, 23]          # shop appended at end of these days
LAST_DAY = 29

# physical constants (engine-derived, not tuned)
ANIMAL_YIELD = {"COW": 1.5, "SHEEP": 4 / 3, "GOOSE": 2.0}   # product units/day with daily FEED+CARE
ANIMAL_ACTIONS = 4                                          # FEED, CARE, HARVEST(amortized), COLLECT per day
FERT_PER_ANIMAL = 1.0
LABOR_VALUE = 25.0     # $ per unit-action opportunity cost (wheat filler: 6 units*$30 / 6 actions, minus walking)
STRAW_ACTIONS = 25.0   # water 18 days + 4 harvests + 3 fertilize
STRAW_UNITS = 8.0      # 4 fertilized production cycles x 2 units
MAX_ANIMAL_SLOTS = 24  # distance<=2 ring around the shed with 3 quadrants


def shop_sink(shops):
    """units/day consumed per product by town center + shop instances."""
    sink = {p: 1.0 for p in TOWN_CENTER}
    sink["FERTILIZER"] = 0.0
    for s in shops:
        prods = SHOPS[s]
        m = 12.0 if len(prods) == 1 else 6.0
        for p in prods:
            sink[p] += m
    return sink


def expected_draw_sink():
    """expected units/day per product added by ONE random shop draw."""
    e = {p: 0.0 for p in PRODUCTS}
    for s, prods in SHOPS.items():
        m = 12.0 if len(prods) == 1 else 6.0
        for p in prods:
            e[p] += m / len(SHOPS)
    return e


E_DRAW = expected_draw_sink()


def consumption_at(step, shops):
    c = {p: 0 for p in PRODUCTS}
    if step % 4 == 0:
        for s in shops:
            prods = SHOPS[s]
            m = 2 if len(prods) == 1 else 1
            for p in prods:
                c[p] += m
    if step % 24 == 0:
        for p in TOWN_CENTER:
            c[p] += 1
    return c


def _trajectory(item, inv0, day, our_flow, opp_flow_by_day, sink_by_day, extra_units_by_day):
    """Simulate inv_{d+1} = inv_d + our + opp + extra - sink; return (rev of extra units, opp revenue)."""
    inv = float(inv0)
    rev = 0.0
    opp_rev = 0.0
    for d in range(day, LAST_DAY + 1):
        extra = extra_units_by_day.get(d, 0.0)
        opp = opp_flow_by_day.get(d, 0.0) if isinstance(opp_flow_by_day, dict) else opp_flow_by_day
        price = F.market_price(item, int(inv + (our_flow + opp) / 2))
        if extra > 0:
            rev += extra * price
        opp_rev += opp * price
        inv += our_flow + opp + extra - sink_by_day.get(d, 1.0)
        if inv < F.MARKET_I0 - 3000:
            inv = F.MARKET_I0 - 3000
    return rev, opp_rev


def season_revenue(item, inv0, day, our_flow, opp_flow, sink_by_day, extra_units_by_day, margin_weight=1.0):
    """Value of selling `extra_units_by_day[d]` extra units on each remaining day d:
    our revenue from those units plus margin_weight * the revenue the price drop takes from the
    opponent's flow (2-player rating game: the objective is the margin, not the absolute score)."""
    rev, opp_with = _trajectory(item, inv0, day, our_flow, opp_flow, sink_by_day, extra_units_by_day)
    if margin_weight > 0 and (isinstance(opp_flow, dict) and any(opp_flow.values()) or (not isinstance(opp_flow, dict) and opp_flow > 0)):
        _, opp_without = _trajectory(item, inv0, day, our_flow, opp_flow, sink_by_day, {})
        rev += margin_weight * (opp_without - opp_with)
    return rev


class Planner:
    def __init__(self, P, mem, verbose=False):
        self.P = P
        self.mem = mem
        self.verbose = verbose
        self.day = -1
        self.prev = None          # previous obs summary for flow inference
        self.opp_sales = {p: [] for p in PRODUCTS}   # per-turn inferred opponent sales
        self.my_sales = {p: [] for p in PRODUCTS}
        self.log = []

    # ---- observation helpers -------------------------------------------------
    @staticmethod
    def my_stock(priv):
        t = dict(priv.get("shed", {}) or {})
        for inv in priv.get("inventories", []) or []:
            for k, v in (inv or {}).items():
                t[k] = t.get(k, 0) + v
        return t

    @staticmethod
    def tile_counts(farm):
        cnt = {}
        for row in farm["tiles"]:
            for t in row:
                if isinstance(t, dict):
                    k = t.get("animal") or (t.get("crop") if t.get("kind") == "PLANT" else None)
                    if k:
                        cnt[k] = cnt.get(k, 0) + 1
        return cnt

    def infer_flows(self, obs):
        """Per-turn: attribute the market inventory change to me / opponent / town."""
        me = obs["player"]
        step = obs.get("step", obs["day"] * 24 + obs["hour"])
        inv = obs["market"]["inventory"]
        stock = self.my_stock(obs["private"])
        if self.prev is not None:
            pinv, pstock, pshops, pstep, porders = self.prev
            cons = consumption_at(pstep, pshops)
            for p in PRODUCTS:
                mine = 0
                if p in porders:
                    mine = max(0, pstock.get(p, 0) - stock.get(p, 0))
                self.my_sales[p].append(mine)
                opp = inv[p] - pinv[p] + cons[p] - mine
                if p in ("WHEAT", "FERTILIZER"):
                    opp = max(0, opp)      # opponent buys make this negative; ignore
                self.opp_sales[p].append(max(0, opp))
        self.prev = (dict(inv), stock, list(obs["town"]["unlocked_shops"]), step, set())

    def note_orders(self, orders):
        if self.prev is not None:
            self.prev = self.prev[:4] + ({o[1] for o in orders if o and o[0] == "SELL"},)

    def opp_capacity_by_day(self, obs):
        """Opponent production capacity per product per future day, from their visible tiles
        (animals produce from placed_day + first_yield_day; strawberry from planted_day + 10)."""
        day = obs["day"]
        opp = obs["farms"][1 - obs["player"]]
        cap = {p: {d: 0.0 for d in range(day, LAST_DAY + 1)} for p in PRODUCTS}
        for row in opp["tiles"]:
            for t in row:
                if not isinstance(t, dict):
                    continue
                if "animal" in t:
                    a = t["animal"]; ad = F.ANIMALS[a]
                    start = t.get("placed_day", day) + ad["fy"]
                    for d in range(max(day, start), LAST_DAY + 1):
                        cap[ad["product"]][d] += ANIMAL_YIELD[a]
                        cap["FERTILIZER"][d] += FERT_PER_ANIMAL
                elif t.get("kind") == "PLANT" and t.get("crop") == "STRAWBERRY":
                    start = t.get("planted_day", day) + 10
                    for d in range(max(day, start), min(LAST_DAY, start + 8) + 1):
                        cap["STRAWBERRY"][d] += 0.75
        return cap

    def opp_flow_by_day(self, p, obs, cap, window_turns=72):
        """Forecast of the opponent's sales per day: visible capacity, calibrated by observed sales
        (ratio of observed to capacity over the last 3 days, clipped to [0.5, 1.3]) once they produce.
        Day 0 (nothing visible yet): symmetric prior = assume the opponent builds what we build."""
        day = obs["day"]
        hist = self.opp_sales[p]
        observed = None
        if len(hist) >= 24:
            h = hist[-window_turns:]
            observed = sum(h) / (len(h) / 24.0)
        cap_now = cap[p].get(day, 0.0)
        cap_recent = sum(cap[p].get(d, 0.0) for d in range(max(0, day - 3), day)) / 3.0 if day > 0 else 0.0
        factor = 1.0
        if observed is not None and cap_recent > 0.5:
            factor = max(0.5, min(1.3, observed / cap_recent))
        out = {}
        for d in range(day, LAST_DAY + 1):
            c = cap[p].get(d, 0.0) * factor
            if observed is not None and cap[p].get(d, 0.0) < 0.1:
                c = observed            # sales without visible capacity (crops we do not model)
            out[d] = c
        self._opp_cap_now = cap_now
        return out

    # ---- daily plan --------------------------------------------------------------
    def plan_day(self, obs):
        P = self.P
        day = obs["day"]
        me = obs["player"]
        farm = obs["farms"][me]
        shops = list(obs["town"]["unlocked_shops"])
        inv = obs["market"]["inventory"]
        cnt = self.tile_counts(farm)
        stock = self.my_stock(obs["private"])
        sink_now = shop_sink(shops)
        draws_left = [d for d in DRAW_DAYS if d >= day]
        # sink by day: current + expected future draws (each adds E_DRAW from day d+1)
        sink_by_day = {}
        for p in PRODUCTS:
            for d in range(day, LAST_DAY + 1):
                s = sink_now[p]
                for dd in draws_left:
                    if dd < d:
                        s += E_DRAW[p]
                sink_by_day.setdefault(p, {})[d] = s
        cap = self.opp_capacity_by_day(obs)
        opp_flow = {p: self.opp_flow_by_day(p, obs, cap) for p in PRODUCTS}

        owned = {a: cnt.get(a, 0) + stock.get(a, 0) for a in F.ANIMALS}
        cull = dict(P.get("cull") or {})
        for a in F.ANIMALS:
            owned[a] = max(0, owned[a] - cull.get(a, 0))
        our_flow = {p: 0.0 for p in PRODUCTS}
        for a, ad in F.ANIMALS.items():
            our_flow[ad["product"]] += owned[a] * ANIMAL_YIELD[a]
        our_flow["STRAWBERRY"] += cnt.get("STRAWBERRY", 0) * 0.5
        our_flow["FERTILIZER"] += sum(owned.values()) * FERT_PER_ANIMAL
        self._symmetric = day <= 1 and not any(v for d in cap["MILK"].values() for v in [d]) \
            and not any(cap["WOOL"].values())

        wheat_p = F.market_price("WHEAT", inv["WHEAT"]) + 2
        fert_p = F.market_price("FERTILIZER", inv["FERTILIZER"])

        def animal_marginal(a, n_extra_already):
            ad = F.ANIMALS[a]
            first = day + ad["fy"] + 1          # bought today, placed today/tomorrow, first yield day
            if first >= LAST_DAY:
                return -1e9
            prod = ad["product"]
            y = ANIMAL_YIELD[a]
            extra = {d: y for d in range(first, LAST_DAY + 1)}
            flow = our_flow[prod] + n_extra_already * y
            of = opp_flow[prod]
            if self._symmetric:
                of = {d: (flow + y if d >= first else 0.0) for d in range(day, LAST_DAY + 1)}
            rev = season_revenue(prod, inv[prod], day, flow, of, sink_by_day[prod], extra)
            days = LAST_DAY - day
            rev += days * FERT_PER_ANIMAL * min(fert_p, 60) * 0.7
            cost = ad["cost"] + days * wheat_p + days * ANIMAL_ACTIONS * LABOR_VALUE
            return rev - cost

        def animal_keep_value(a):
            """value of continuing to feed one existing animal of type a for the rest of the season."""
            prod = F.ANIMALS[a]["product"]
            y = ANIMAL_YIELD[a]
            extra = {d: y for d in range(day + 1, LAST_DAY + 1)}
            flow = our_flow[prod] - y
            rev = season_revenue(prod, inv[prod], day, flow, opp_flow[prod], sink_by_day[prod], extra)
            days = LAST_DAY - day
            rev += days * FERT_PER_ANIMAL * min(fert_p, 60) * 0.7
            cost = days * wheat_p + days * ANIMAL_ACTIONS * LABOR_VALUE
            return rev - cost

        targets = dict(owned)
        total = sum(owned.values())
        buy_log = {}
        for a in ("SHEEP", "COW", "GOOSE"):
            if day > F.ANIMAL_BUY_DEADLINE[a]:
                continue
            n = 0
            while total + n < MAX_ANIMAL_SLOTS:
                mv = animal_marginal(a, n)
                if mv <= 0:
                    break
                n += 1
                if n >= 6:
                    break
            buy_log[a] = n
            targets[a] = owned[a] + n
            total += n
        # cull: stop feeding animals with negative keep value (never geese/sheep feeding the fert pie < 2 animals)
        new_cull = {}
        for a in ("COW", "SHEEP", "GOOSE"):
            n_alive = cnt.get(a, 0)
            if n_alive == 0:
                continue
            kv = animal_keep_value(a)
            if kv < 0 and day >= 10 and day <= 27:
                # cull one at a time per day (marginal), keep at least 2 animals total for fertilizer/labor
                new_cull[a] = min(n_alive, cull.get(a, 0) + 1)
            elif cull.get(a, 0) > 0:
                new_cull[a] = cull[a]          # already culled ones stay culled (they escape)
        # strawberry tiles: marginal season value of one more tile planted today
        straw_target = cnt.get("STRAWBERRY", 0)
        if 2 <= day <= 15:
            first = day + 10
            n = 0
            while n < 12 and straw_target + n < 40:
                extra = {d: 1.0 for d in range(first, LAST_DAY + 1)}
                flow = our_flow["STRAWBERRY"] + n * 0.5
                rev = season_revenue("STRAWBERRY", inv["STRAWBERRY"], day, flow, opp_flow["STRAWBERRY"],
                                     sink_by_day["STRAWBERRY"], extra)
                cost = 100 + STRAW_ACTIONS * LABOR_VALUE * (LAST_DAY - day) / 18.0 + 3 * 30
                if rev - cost <= 0:
                    break
                n += 1
            straw_target += n
        else:
            straw_target = 0
        P["n_cows"] = targets["COW"]
        P["n_sheep"] = targets["SHEEP"]
        P["n_geese"] = targets["GOOSE"]
        P["cull"] = new_cull
        if 2 <= day <= 15:
            P["straw_tiles"] = max(straw_target, cnt.get("STRAWBERRY", 0))
        self.sink_now = sink_now
        self.opp_flow = opp_flow
        rec = {"day": day, "shops": len(shops), "targets": targets, "buy": buy_log, "cull": new_cull,
               "straw": P["straw_tiles"], "opp_flow": {k: round(v.get(day, 0), 1) for k, v in opp_flow.items() if v.get(day, 0)},
               "sink": {k: v for k, v in sink_now.items() if v > 1}}
        self.log.append(rec)
        if self.verbose:
            print(rec)

    # ---- selling ---------------------------------------------------------------
    def sell_override(self, item, q, ctx):
        """Inventory-targeting, opponent-aware sell rule for sink products."""
        if item in ("MELON", "EGG", "WHEAT", "FERTILIZER"):
            return None                      # sol5 rules are fine (dump / reserve logic)
        if not hasattr(self, "sink_now"):
            return None
        day, hour = ctx["day"], ctx["hour"]
        inv = ctx["inv"]
        sink = self.sink_now.get(item, 1.0)          # units/day
        opp = self.opp_flow.get(item, {}).get(day, 0.0)   # units/day forecast for today
        stock = q + ctx["carried"]
        turns_left = ctx["turns_left"]
        days_left = turns_left / 24.0
        # 1) the opponent floods faster than the town drains: the price only falls from here -> sell now
        if opp >= 0.9 * sink:
            return q
        # 2) scarcity side: selling down to I0 never costs anything (price >= base)
        room = F.MARKET_I0 - inv
        k = max(0, min(q, room))
        # 3) above I0: sell what the residual sink will drain before our next production plus a
        #    reservation that decays with days left; always liquidate what can't recover in time.
        residual = max(0.0, sink - opp)              # units/day the market can absorb from us at ~base
        per_turn = residual / 24.0
        k = max(k, int(per_turn * 4))                # roughly one consumption tick worth
        base = F.MARKET_PARAMS[item]["base"]
        reserve_frac = max(0.25, 0.9 - 0.65 * max(0, day - 10) / 19.0)
        k = max(k, F.sellable_qty(item, inv, reserve_frac, q))
        excess = inv - F.MARKET_I0
        if residual <= 0.01 or excess / max(residual, 0.01) > days_left:
            k = q                                    # cannot recover in time
        # pressure valve: never hold more than ~1.5 days of residual sink
        hold_cap = max(3, int(1.5 * residual))
        if stock > hold_cap:
            k = max(k, min(q, stock - hold_cap))
        return k


def build_agent(verbose=False, use_sell=True, use_plan=True, base_vec=None):
    m = F
    P = m.vec_to_params(base_vec or m.SEED_VEC)
    P["planner"] = use_plan
    # winners' hire schedule: 11 hands from day 8 (cheap; fib cost for 11 = $232/day)
    P["hands"] = lambda d: 8 if d >= LAST_DAY else (6 if d <= 3 else (9 if d <= 7 else 11))
    base = m.build_agent(P)
    pl = Planner(P, base.mem, verbose=verbose)
    if use_sell:
        P["sell_override"] = pl.sell_override
    if use_plan:
        # day-0 opening: no shop info yet -> the marginal model decides with expected sinks
        pass

    def agent(obs):
        pl.infer_flows(obs)
        if use_plan and obs["day"] != pl.day:
            pl.day = obs["day"]
            pl.plan_day(obs)
        act = base(obs)
        pl.note_orders(act.get("market", []))
        return act

    agent.planner = pl
    agent.P = P
    agent.stats = base.stats
    return agent


def build_agent_plan_only():
    return build_agent(use_sell=False, use_plan=True)


def build_agent_sell_only():
    return build_agent(use_sell=True, use_plan=False)


if __name__ == "__main__":
    import json, time
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import harness
    sched = sys.argv[1] if len(sys.argv) > 1 else "milk_starved"
    opp = sys.argv[2] if len(sys.argv) > 2 else "sol5"
    a = build_agent(verbose=True)
    t = time.time()
    from kaggle_environments import make
    sales, restore = harness._patch(harness.SCHEDULES[sched])
    env = make("kaggriculture", configuration={"seed": 1000}, debug=True)
    env.run([a, harness.build(harness.STD_OPPONENTS[opp])])
    restore()
    print("rewards", env.steps[-1][0]["reward"], env.steps[-1][1]["reward"], f"{time.time()-t:.1f}s")
    for p in range(2):
        print(p, {k: int(v) for k, v in sorted(sales.get(p, {}).get("rev", {}).items(), key=lambda x: -x[1])})
