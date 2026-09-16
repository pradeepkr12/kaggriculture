"""Apply the planner hooks (dynamic animal targets, cull set, sell override, hands schedule)
to a farmlib source. Usage: python _patch_hooks.py <src farmlib.py> <dst .py>"""
import sys

def patch(src):
    s = src
    def rep(old, new, count=1):
        nonlocal s
        assert s.count(old) == count, (old[:70], s.count(old))
        s = s.replace(old, new)
    rep('''    def animal_targets(day):
        if day < P["animal_day2"]:''', '''    def animal_targets(day):
        if P.get("planner"):
            return {"SHEEP": P["n_sheep"], "COW": P["n_cows"], "GOOSE": P["n_geese"]}
        if day < P["animal_day2"]:''')
    rep('''    def hands_target(day):
        if day >= LAST_DAY:''', '''    def hands_target(day):
        if P.get("hands"):
            return P["hands"](day)
        if day >= LAST_DAY:''')
    rep('''        animal_at = {(x, y): t for (x, y, t) in animals}
''', '''        animal_at = {(x, y): t for (x, y, t) in animals}
        cull_set = set()
        for a_name, n_cull in (P.get("cull") or {}).items():
            picked = 0
            for (x, y, t) in animals:
                if picked >= n_cull:
                    break
                if t["animal"] == a_name:
                    cull_set.add((x, y)); picked += 1
        mem["cull_set"] = cull_set
''')
    rep('''        def animal_pending(t):
            """Ordered list of ops still to do at this animal today."""
            a = ANIMALS[t["animal"]]
            ops = []
            if feed_today and not t.get("fed_today"):
                ops.append("FEED")
            if feed_today and not t.get("cared_today"):
                ops.append("CARE")''', '''        def animal_pending(t, pos=None):
            """Ordered list of ops still to do at this animal today."""
            a = ANIMALS[t["animal"]]
            ops = []
            culled = pos is not None and pos in cull_set
            if feed_today and not t.get("fed_today") and not culled:
                ops.append("FEED")
            if feed_today and not t.get("cared_today") and not culled:
                ops.append("CARE")''')
    rep('animals_with_work = [(x, y) for (x, y, t) in animals if animal_pending(t)]',
        'animals_with_work = [(x, y) for (x, y, t) in animals if animal_pending(t, (x, y))]')
    rep('route = [p for p in routes.get(ui, []) if p in animal_at and animal_pending(animal_at[p])]',
        'route = [p for p in routes.get(ui, []) if p in animal_at and animal_pending(animal_at[p], p)]')
    rep('unfed = [p for p in route if "FEED" in animal_pending(animal_at[p])]',
        'unfed = [p for p in route if "FEED" in animal_pending(animal_at[p], p)]')
    rep('''            here = animal_at.get((ux, uy))
            if here is not None and (ux, uy) in route:
                pend = animal_pending(here)''', '''            here = animal_at.get((ux, uy))
            if here is not None and (ux, uy) in route:
                pend = animal_pending(here, (ux, uy))''')
    rep('''            for p in route:
                pend = animal_pending(animal_at[p])''', '''            for p in route:
                pend = animal_pending(animal_at[p], p)''')
    rep('''            unfed_all = [(x, y) for (x, y, t) in animals if not t.get("fed_today")]''',
        '''            unfed_all = [(x, y) for (x, y, t) in animals if not t.get("fed_today") and (x, y) not in cull_set]''')
    rep('''            for op in animal_pending(t):
                if op == "FEED":''', '''            for op in animal_pending(t, (x, y)):
                if op == "FEED":''')
    rep('''        if any((x, y) not in routed and "FEED" in animal_pending(t) for (x, y, t) in animals) \\''',
        '''        if any((x, y) not in routed and "FEED" in animal_pending(t, (x, y)) for (x, y, t) in animals) \\''')
    rep('''        unfed_n = sum(1 for (_, _, t) in animals if not t.get("fed_today")) if feed_today else 0
        animals_total = n_animals + sum(shed.get(a, 0) + carried.get(a, 0) for a in ANIMALS)''',
        '''        unfed_n = sum(1 for (x, y, t) in animals if not t.get("fed_today") and (x, y) not in cull_set) if feed_today else 0
        animals_total = n_animals - len(cull_set) + sum(shed.get(a, 0) + carried.get(a, 0) for a in ANIMALS)''')
    rep('''        def sell_qty(item):
            q = shed.get(item, 0)
            if q <= 0:
                return 0
            if final_dump:
                return q
            inv = mkt_inv.get(item, MARKET_I0)''', '''        def sell_qty(item):
            q = shed.get(item, 0)
            if q <= 0:
                return 0
            if final_dump:
                return q
            inv = mkt_inv.get(item, MARKET_I0)
            ov = P.get("sell_override")
            if ov is not None:
                ctx = {"inv": inv, "day": day, "hour": hour, "carried": carried.get(item, 0),
                       "turns_left": endgame_turns_left, "crop_count": crop_count, "money": money,
                       "overflow": overflow, "wheat_reserve": wheat_reserve, "n_animals": n_animals}
                k = ov(item, q, ctx)
                if k is not None:
                    return max(0, min(q, int(k)))''')
    return s

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    open(dst, "w").write(patch(open(src).read()))
    print("patched", dst)
