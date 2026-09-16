"""sol8 daily production planner: sol7's model-based marginal-value planner plus
a graduated, EMA-smoothed animal throttle (no more irreversible over-culling),
contested-sink purchase floors, EMA-controlled reversible crop production, and a
geese/wheat idle-labor filler. Runs on sol5's mechanics layer (farmlib_ph.py hooks).

Design vs sol7 (see sol8/README.md and REPORT.md):
  A. Graduated animal throttle instead of hard culling. Per animal type we keep an
     EMA (half-life ~2 days) of the planner's keep value and of realized price/base
     and pick a feeding rung: full FEED+CARE, FEED-only, or alternate-day FEED. The
     real cull (escape) rung is gated so hard it is unreachable for cows/sheep while
     any shop or future draw can restore the price -- prices recover late-season, so
     alternate-day feeding is the deepest throttle cows/sheep normally reach.
  B. Contested-sink purchase floor: buy up to 0.5-0.6 * sink/yield of each animal as
     soon as the sink is observed (respecting slots + deadlines), regardless of the
     opponent's flow. Keep the symmetric day-0 prior and a cow floor of 4 until day 6.
  C. EMA-controlled reversible crop production: strawberry planted through day 19,
     target from an EMA of the straw sink + price signal; wheat filler scaled by the
     EMA of idle unit-turns.
  D. Geese as labor filler: buy geese while EMA idle unit-turns > 12/day or the egg
     sink is unfilled (cap 10, deadline d24).
  E. Day-0 cash split: reserve melon seeds first (target 12), only the day-0 animal
     floor (2 cows + 3 sheep) before them; ramp animals from day 2.
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import farmlib_ph as F

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
LABOR_VALUE = 25.0     # $ per unit-action opportunity cost
STRAW_ACTIONS = 25.0   # water 18 days + 4 harvests + 3 fertilize
STRAW_UNITS = 8.0      # 4 fertilized production cycles x 2 units
MAX_ANIMAL_SLOTS = 24  # distance<=2 ring around the shed with 3 quadrants

STRAW_DEADLINE = 19    # sol8: plant strawberry through day 19 (yield by day 29)
EMA_HALFLIFE = 2.0
EMA_ALPHA = 1.0 - 0.5 ** (1.0 / EMA_HALFLIFE)   # ~0.293 per day

# purchase-floor coefficients: floor = FLOOR_FAC * sink / yield
FLOOR_FAC = {"COW": 0.60, "SHEEP": 0.55, "GOOSE": 0.50}

# sol8 step 2/3: crop-filler constants (engine-derived sink ratios, not tuned).
# CARROT has exactly one shop sink (PET_CAFE); planting the old uncapped 999-tile
# filler there floods CARROT's price and starves WHEAT (five shop sinks: BAKERY,
# PIZZA_SHOP, BRUNCH_SPOT, ICE_CREAM_SHOP, FARMERS_MARKET) of the idle-labor
# overflow. Cap CARROT modestly and let WHEAT absorb the rest.
CARROT_FILLER_FLOOR = 8.0
CARROT_FILLER_MAX = 40.0


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
        # sol8 EMA state
        self.ema_kv = {a: None for a in F.ANIMALS}        # smoothed keep value per animal type
        self.ema_pr = {p: None for p in PRODUCTS}         # smoothed realized price / base
        self.neg_days = {a: 0 for a in F.ANIMALS}         # consecutive days of alt_feed rung
        self.idle_ema = None                              # smoothed idle unit-turns/day
        self.straw_ema = None                             # smoothed strawberry tile target

    # ---- EMA helpers ---------------------------------------------------------
    @staticmethod
    def _ema(prev, x, a=EMA_ALPHA):
        return x if prev is None else a * x + (1 - a) * prev

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
                c = observed
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
        unlocked = farm.get("unlocked_quadrants", ["NW"])
        n_slots = len(F.animal_slots(unlocked))
        slot_cap = min(MAX_ANIMAL_SLOTS, max(6, n_slots))

        # ---- update EMA of realized price / base per product --------------------
        for p in PRODUCTS:
            base = F.MARKET_PARAMS[p]["base"]
            pr = F.market_price(p, inv.get(p, F.MARKET_I0)) / base
            self.ema_pr[p] = self._ema(self.ema_pr[p], pr)

        # ---- update EMA of idle unit-turns (from yesterday's mechanics stats) ----
        ystat = (self.mem.get("stats", {}) or {}).get("days", {}).get(day - 1)
        if ystat:
            self.idle_ema = self._ema(self.idle_ema, float(ystat.get("idle", 0)))

        # sink by day: current + expected future draws
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
        self._symmetric = day <= 1 and not any(cap["MILK"].values()) and not any(cap["WOOL"].values())

        wheat_p = F.market_price("WHEAT", inv["WHEAT"]) + 2
        fert_p = F.market_price("FERTILIZER", inv["FERTILIZER"])

        def animal_marginal(a, n_extra_already):
            ad = F.ANIMALS[a]
            first = day + ad["fy"] + 1
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

        # ---- purchase floors (contested-sink; B) --------------------------------
        egg_sink = sink_now["EGG"]
        idle_geese = 0
        # idle-labor filler kicks in once tiles are established (D); modest counts so
        # geese never dominate; they only ever take slots cows/sheep don't want.
        if (self.idle_ema or 0) > 12 and 8 <= day <= F.ANIMAL_BUY_DEADLINE["GOOSE"]:
            idle_geese = min(4, math.ceil((self.idle_ema - 12) / 8.0))

        def floor_for(a):
            if day > F.ANIMAL_BUY_DEADLINE[a]:
                return owned[a]
            prod = F.ANIMALS[a]["product"]
            s = sink_now[prod]
            fl = round(FLOOR_FAC[a] * s / ANIMAL_YIELD[a]) if s > 1.0 else 0
            if a == "COW" and day <= 6 and sink_now["MILK"] >= sink_now["WOOL"]:
                fl = max(fl, 4)                 # milk_rich under-buy fix (only when milk is the dominant animal sink)
            if a == "GOOSE":
                fl = max(fl, idle_geese)        # geese as idle-labor filler (D)
            return int(fl)

        # ---- animal targets: day-0 opening prior, else floor + marginal ----------
        buy_log = {}
        if day <= 1:
            # E: only the day-0 floor before melon seeds; ramp from day 2
            base_open = {"COW": 2, "SHEEP": 3, "GOOSE": 0}
            targets = {a: max(owned[a], base_open[a]) for a in F.ANIMALS}
            for a in F.ANIMALS:
                buy_log[a] = {"floor": base_open[a], "marg": 0, "want": targets[a]}
        else:
            def prio(a):
                # value-per-slot: realized $/day of one animal = price_ratio * base * yield.
                # scarce slots go to the higher-value animal (wool beats milk when a yarn
                # store is contested against a smaller milk sink, etc.).
                prod = F.ANIMALS[a]["product"]
                return self.ema_pr.get(prod, 0.5) * F.MARKET_PARAMS[prod]["base"] * ANIMAL_YIELD[a]
            # value animals (cows, sheep) claim slots first: floor + marginal
            val_target = {}
            for a in ("SHEEP", "COW"):
                if day > F.ANIMAL_BUY_DEADLINE[a]:
                    val_target[a] = owned[a]
                    buy_log[a] = {"floor": owned[a], "marg": 0, "want": owned[a]}
                    continue
                fl = floor_for(a)
                n = 0
                while owned[a] + n < slot_cap:
                    if animal_marginal(a, n) <= 0:
                        break
                    n += 1
                    if n >= 6:
                        break
                val_target[a] = max(fl, owned[a] + n)
                buy_log[a] = {"floor": fl, "marg": n, "want": val_target[a]}
            # clamp cows+sheep to slots: cut the weaker-priced one's excess above its
            # floor first, then above owned; never sell placed value animals.
            while val_target["COW"] + val_target["SHEEP"] > slot_cap:
                cc = [a for a in ("SHEEP", "COW") if val_target[a] > max(floor_for(a), owned[a])]
                if not cc:
                    cc = [a for a in ("SHEEP", "COW") if val_target[a] > owned[a]]
                if not cc:
                    break
                val_target[min(cc, key=prio)] -= 1
            # geese take only the residual slots (idle-labor filler, never crowding value)
            if day > F.ANIMAL_BUY_DEADLINE["GOOSE"]:
                goose_target = owned["GOOSE"]
            else:
                goose_want = min(10, max(floor_for("GOOSE"), owned["GOOSE"]))
                remaining = slot_cap - val_target["COW"] - val_target["SHEEP"]
                goose_target = min(goose_want, max(owned["GOOSE"], remaining))
            buy_log["GOOSE"] = {"floor": floor_for("GOOSE"), "want": goose_target}
            targets = {"COW": val_target["COW"], "SHEEP": val_target["SHEEP"], "GOOSE": goose_target}

        # ---- feeding rungs (A): graduated, EMA-smoothed throttle -----------------
        rung = {}
        for a in F.ANIMALS:
            n_alive = cnt.get(a, 0)
            if n_alive == 0:
                self.neg_days[a] = 0
                continue
            prod = F.ANIMALS[a]["product"]
            kv_raw = animal_keep_value(a)
            self.ema_kv[a] = self._ema(self.ema_kv[a], kv_raw)
            kv = self.ema_kv[a]
            pr = self.ema_pr.get(prod, 1.0)
            if kv >= 0:
                rg = "full"
            elif pr >= 0.6:
                rg = "feed_only"
            else:
                rg = "alt_feed"
            rung[a] = rg
            self.neg_days[a] = self.neg_days[a] + 1 if rg == "alt_feed" else 0

        # ---- real cull (rung iv): essentially unreachable while a sink can recover
        new_cull = {}
        for a in ("COW", "SHEEP", "GOOSE"):
            n_alive = cnt.get(a, 0)
            if n_alive == 0:
                continue
            prod = F.ANIMALS[a]["product"]
            shop_exists = sink_now[prod] > 1.0
            draws_remain = any(dd >= day for dd in DRAW_DAYS)   # a future draw could add a sink
            pr = self.ema_pr.get(prod, 1.0)
            fl = floor_for(a)
            can_cull = (day >= 12 and self.neg_days[a] >= 3 and not shop_exists
                        and not draws_remain and pr < 0.40 and n_alive > fl)
            if can_cull:
                new_cull[a] = min(n_alive, cull.get(a, 0) + 1)
            elif cull.get(a, 0) > 0:
                new_cull[a] = cull[a]              # already-escaped ones stay culled

        # ---- strawberry: EMA target, planted through day 19 (C) ------------------
        # (step 2 tried sizing this off sink-minus-opponent-flow; reverted -- realized
        # STRAWBERRY price stayed well above base (ema_pr 1.4-1.8) even at 38 tiles in
        # yarn_x3, i.e. the sink was not glutted, so cutting tiles only cost revenue;
        # see REPORT.md.)
        straw_target = cnt.get("STRAWBERRY", 0)
        if 2 <= day <= STRAW_DEADLINE:
            straw_pr = self.ema_pr.get("STRAWBERRY", 0.8)
            base_t = 32.0 if sink_now["STRAWBERRY"] > 1.0 else 26.0
            if straw_pr >= 0.9:
                base_t += 6.0
            elif straw_pr < 0.55:
                base_t -= 4.0
            self.straw_ema = self._ema(self.straw_ema, base_t)
            straw_target = int(round(min(42.0, max(24.0, self.straw_ema))))

        # ---- wheat filler scaled by idle EMA (C); carrot filler capped (step 2/3) --
        wheat_t = int(min(26, max(14, 14 + (self.idle_ema or 0) / 4.0)))
        # carrot filler tracks its own sink (mostly PET_CAFE) instead of the old
        # uncapped 999: a floor of 8 tiles for the town-center base sink, scaling up
        # to cover PET_CAFE draws (random_b has 4), capped so it never crowds wheat.
        carrot_t = int(min(CARROT_FILLER_MAX, max(CARROT_FILLER_FLOOR, sink_now.get("CARROT", 1.0))))

        P["n_cows"] = targets["COW"]
        P["n_sheep"] = targets["SHEEP"]
        P["n_geese"] = targets["GOOSE"]
        P["cull"] = new_cull
        P["animal_rung"] = rung
        P["wheat_tiles"] = wheat_t
        P["carrot_tiles"] = carrot_t
        if 5 <= day <= STRAW_DEADLINE:
            P["straw_tiles"] = max(straw_target, cnt.get("STRAWBERRY", 0))
        self.sink_now = sink_now
        self.opp_flow = opp_flow
        rec = {"day": day, "shops": len(shops),
               "targets": dict(targets), "owned": dict(owned),
               "floors": {a: floor_for(a) for a in F.ANIMALS},
               "rung": dict(rung), "cull": dict(new_cull),
               "kv_ema": {a: round(v, 0) for a, v in self.ema_kv.items() if v is not None},
               "pr_ema": {p: round(self.ema_pr[p], 2) for p in ("MILK", "WOOL", "STRAWBERRY", "EGG")},
               "straw": P.get("straw_tiles", 0), "wheat_t": wheat_t,
               "idle_ema": round(self.idle_ema, 1) if self.idle_ema is not None else None,
               "sink": {k: v for k, v in sink_now.items() if v > 1}}
        self.log.append(rec)
        if self.verbose:
            print(rec)

    # ---- selling ---------------------------------------------------------------
    def sell_override(self, item, q, ctx):
        """Inventory-targeting, opponent-aware sell rule for sink products."""
        if item in ("MELON", "EGG", "WHEAT", "FERTILIZER"):
            return None
        if not hasattr(self, "sink_now"):
            return None
        day, hour = ctx["day"], ctx["hour"]
        inv = ctx["inv"]
        sink = self.sink_now.get(item, 1.0)
        opp = self.opp_flow.get(item, {}).get(day, 0.0)
        stock = q + ctx["carried"]
        turns_left = ctx["turns_left"]
        days_left = turns_left / 24.0
        if opp >= 0.9 * sink:
            return q
        room = F.MARKET_I0 - inv
        k = max(0, min(q, room))
        residual = max(0.0, sink - opp)
        per_turn = residual / 24.0
        k = max(k, int(per_turn * 4))
        base = F.MARKET_PARAMS[item]["base"]
        reserve_frac = max(0.25, 0.9 - 0.65 * max(0, day - 10) / 19.0)
        k = max(k, F.sellable_qty(item, inv, reserve_frac, q))
        excess = inv - F.MARKET_I0
        if residual <= 0.01 or excess / max(residual, 0.01) > days_left:
            k = q
        hold_cap = max(3, int(1.5 * residual))
        if stock > hold_cap:
            k = max(k, min(q, stock - hold_cap))
        return k


def build_agent(verbose=False, use_sell=True, use_plan=True, base_vec=None, hungarian=True):
    m = F
    P = m.vec_to_params(base_vec or m.SEED_VEC)
    P["planner"] = use_plan
    P["melon_tiles"] = 12                 # E: ~12 melon tiles day 0 only (do not chase the sq glut)
    P["straw_deadline"] = STRAW_DEADLINE  # C: plant strawberry through day 19
    P["hands"] = lambda d: 8 if d >= LAST_DAY else (6 if d <= 3 else (9 if d <= 7 else 11))
    base = m.build_agent(P, hungarian=hungarian)
    pl = Planner(P, base.mem, verbose=verbose)
    if use_sell:
        P["sell_override"] = pl.sell_override
    base.mem["stats"]["plan"] = pl.log

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
    sched = sys.argv[1] if len(sys.argv) > 1 else "late_milk"
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
