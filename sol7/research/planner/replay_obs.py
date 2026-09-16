"""What can a player infer about the opponent from public observations?
Checks on the rank-1 replay (/private/tmp/109564916.json):
 (1) opponent per-turn sales are exactly recoverable from market inventory deltas
     (delta_inv + town consumption - my sales), except for $1 sales (which do not add inventory);
 (2) the opponent's production capacity per product is visible from their tiles.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kaggle_environments.envs.kaggriculture.kaggriculture as K

PRODUCTS = K.PRODUCTS

def consumption(step, shops):
    c = {p: 0 for p in PRODUCTS}
    if step % 4 == 0:
        for s in shops:
            prods = K.SHOPS[s]
            m = 2 if len(prods) == 1 else 1
            for p in prods:
                c[p] += m
    if step % 24 == 0:
        for p in K.TOWN_CENTER_PRODUCTS:
            c[p] += 1
    return c

def shed_total(priv):
    t = dict(priv["shed"])
    for inv in priv["inventories"]:
        for k, v in inv.items():
            t[k] = t.get(k, 0) + v
    return t

def main(path):
    d = json.load(open(path))
    steps = d["steps"]
    names = d["info"]["TeamNames"]
    # realized sales per player per step: shed+inventory decrease of item while a SELL order for it exists
    # (harvests only add; DROP moves between inv and shed; so a decrease in (shed+inv) total = sold or discarded)
    err = {p: 0 for p in PRODUCTS}; tot = {p: 0 for p in PRODUCTS}; floor_sales = {p: 0 for p in PRODUCTS}
    n_checked = 0
    for i in range(1, len(steps)):
        pre = steps[i-1]; post = steps[i]
        step = pre[0]["observation"]["step"]  # step index at which actions steps[i]['action'] were applied
        shops_pre = pre[0]["observation"]["town"]["unlocked_shops"]
        inv_pre = pre[0]["observation"]["market"]["inventory"]; inv_post = post[0]["observation"]["market"]["inventory"]
        prices_pre = pre[0]["observation"]["market"]["prices"]
        cons = consumption(step, shops_pre)
        sold = []
        for p in range(2):
            a = steps[i][p]["action"] or {}
            orders = a.get("market", []) if isinstance(a, dict) else []
            sell_items = {o[1] for o in orders if isinstance(o, list) and o and o[0] == "SELL"}
            before = shed_total(pre[p]["observation"]["private"]); after = shed_total(post[p]["observation"]["private"])
            s = {}
            for it in PRODUCTS:
                dec = before.get(it, 0) - after.get(it, 0)
                # harvest adds; sales subtract; EOD overflow discards (ignore hour 23)
                if it in sell_items and dec > 0:
                    s[it] = dec
            sold.append(s)
        for it in PRODUCTS:
            delta = inv_post[it] - inv_pre[it]
            # inferred opponent(=player1) sales from player0's viewpoint
            inferred = delta + cons[it] - sold[0].get(it, 0)
            actual = sold[1].get(it, 0)
            if prices_pre[it] <= 1:
                floor_sales[it] += actual
                continue
            tot[it] += 1
            if inferred != actual:
                err[it] += 1
        n_checked += 1
    print("turns checked", n_checked)
    print("mismatch rate of inferred opponent sales (excluding $1-price turns):")
    for it in PRODUCTS:
        print(f"  {it:11s} mismatches={err[it]:4d}/{tot[it]}  units sold at floor (unobservable)={floor_sales[it]}")

    # (2) visible production capacity vs realized sales, per player
    print("\nvisible tiles (day 12 / day 20) vs season sales per player")
    for p in range(2):
        for day in (12, 20):
            obs = steps[day*24][p]["observation"]; farm = obs["farms"][p]
            cnt = {}
            for row in farm["tiles"]:
                for t in row:
                    if isinstance(t, dict):
                        k = t.get("animal") or (t.get("crop") if t.get("kind") == "PLANT" else None)
                        if k: cnt[k] = cnt.get(k, 0) + 1
            print(f"  {names[p][:12]:12s} day{day}: {cnt}")
        # realized season sales from shed deltas
        tot_sales = {}
        for i in range(1, len(steps)):
            a = steps[i][p]["action"] or {}
            orders = a.get("market", []) if isinstance(a, dict) else []
            sell_items = {o[1] for o in orders if isinstance(o, list) and o and o[0] == "SELL"}
            before = shed_total(steps[i-1][p]["observation"]["private"]); after = shed_total(steps[i][p]["observation"]["private"])
            for it in sell_items:
                dec = before.get(it, 0) - after.get(it, 0)
                if dec > 0: tot_sales[it] = tot_sales.get(it, 0) + dec
        print(f"  {names[p][:12]:12s} season units sold: {tot_sales}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/private/tmp/109564916.json")
