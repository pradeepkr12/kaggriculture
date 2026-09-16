"""Direction 4 feasibility: is there a non-trivial sell policy in the top replays to clone?
For each player and product: mean shed+carried stock at hour 12, max stock, units sold,
mean realized price / base, and share of units sold within 1 day of production (approx via stock)."""
import json, sys, glob, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kaggle_environments.envs.kaggriculture.kaggriculture as K

def stock(priv):
    t = dict(priv["shed"])
    for inv in priv["inventories"]:
        for k, v in inv.items(): t[k] = t.get(k, 0) + v
    return t

def analyze(path):
    d = json.load(open(path)); steps = d["steps"]; names = d["info"]["TeamNames"]
    out = {}
    for p in range(2):
        rows = {}
        for it in K.PRODUCTS:
            rows[it] = {"hold12": [], "maxstock": 0, "units": 0, "rev": 0}
        for i in range(1, len(steps)):
            pre, post = steps[i-1], steps[i]
            obs = pre[0]["observation"]
            prices = obs["market"]["prices"]
            a = steps[i][p]["action"] or {}
            orders = a.get("market", []) if isinstance(a, dict) else []
            sell_items = {o[1] for o in orders if isinstance(o, list) and o and o[0] == "SELL"}
            b, af = stock(pre[p]["observation"]["private"]), stock(post[p]["observation"]["private"])
            for it in K.PRODUCTS:
                if obs["hour"] == 12: rows[it]["hold12"].append(b.get(it, 0))
                rows[it]["maxstock"] = max(rows[it]["maxstock"], b.get(it, 0))
                if it in sell_items:
                    dec = b.get(it, 0) - af.get(it, 0)
                    if dec > 0:
                        rows[it]["units"] += dec; rows[it]["rev"] += dec * prices[it]  # approx: pre-turn price
        out[names[p]] = {it: {"hold12_mean": round(sum(r["hold12"]) / max(1, len(r["hold12"])), 1),
                              "maxstock": r["maxstock"], "units": r["units"],
                              "price_over_base": round(r["rev"] / r["units"] / K.MARKET_PARAMS[it]["base"], 2) if r["units"] else None}
                        for it, r in rows.items()}
    return d["rewards"], out

if __name__ == "__main__":
    files = ["/private/tmp/109564916.json"] + sorted(glob.glob("/tmp/kag_eps/*.json"))
    res = {}
    for f in files:
        try:
            rewards, out = analyze(f)
        except Exception as e:
            print("skip", f, e); continue
        res[os.path.basename(f)] = {"rewards": rewards, "players": out}
        for nm, rows in out.items():
            if nm == "Pradeep Kumar Mahato": continue
            sc = rewards[list(out).index(nm)]
            print(f"{os.path.basename(f)} {nm[:14]:14s} {sc:>7.0f} | " + " ".join(
                f"{it[:4]}:h{r['hold12_mean']}/m{r['maxstock']}/u{r['units']}/p{r['price_over_base']}"
                for it, r in rows.items() if it in ("MILK", "WOOL", "STRAWBERRY", "MELON", "EGG")))
    json.dump(res, open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "replay_sellpolicy.json"), "w"))
