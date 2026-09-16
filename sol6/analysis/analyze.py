import json, sys, math
sys.path.insert(0,'/opt/miniconda3/envs/env2/lib/python3.13/site-packages')
from kaggle_environments.envs.kaggriculture.kaggriculture import market_price, ANIMALS, CROPS, SHOPS, MARKET_PARAMS

PRODUCTS = ["WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER"]

def parse_order(o):
    if not isinstance(o,list) or not o: return None
    op=o[0]
    if op=="HIRE": return {"type":"HIRE"}
    if op=="BUY_LAND": return {"type":"BUY_LAND"}
    if op in ("BUY_SEED","BUY_PRODUCT","BUY_ANIMAL","SELL"):
        if len(o)<3: return None
        try: n=int(o[2])
        except: return None
        if n<=0: return None
        return {"type":op,"item":o[1],"remaining":n}
    return None

def sim_market(inv, sheds, moneys, queues):
    # returns executed sells[player][item]=(units,revenue), mutates nothing external
    inv=dict(inv); sheds=[dict(s) for s in sheds]; moneys=list(moneys)
    sells=[{},{}]; rev=[{},{}]
    maxlen=max((len(q) for q in queues),default=0)
    for i in range(maxlen):
        ostates=[parse_order(q[i]) if i<len(q) else None for q in queues]
        # atomic
        for pid,os in enumerate(ostates):
            if os is None: continue
            if os["type"] in ("HIRE","BUY_LAND"): ostates[pid]=None
        while True:
            quoted=[None,None]
            for pid,os in enumerate(ostates):
                if os is None or os["remaining"]<=0: continue
                op=os["type"]; item=os.get("item")
                if op=="SELL" and item in PRODUCTS:
                    quoted[pid]=("SELL",item,market_price(item,inv[item]),os)
                elif op=="BUY_PRODUCT" and item in ("WHEAT","FERTILIZER"):
                    quoted[pid]=("BUY_PRODUCT",item,market_price(item,inv[item]-1),os)
                elif op=="BUY_SEED" and item in CROPS:
                    quoted[pid]=("BUY_SEED",item,CROPS[item]["seed"],os)
                elif op=="BUY_ANIMAL" and item in ANIMALS:
                    quoted[pid]=("BUY_ANIMAL",item,ANIMALS[item]["cost"],os)
                else: ostates[pid]=None
            if all(q is None for q in quoted): break
            committed=False
            for pid,q in enumerate(quoted):
                if q is None: continue
                op,item,price,os=q
                ok=False
                if op=="SELL":
                    if sheds[pid].get(item,0)>0:
                        sheds[pid][item]-=1; moneys[pid]+=price
                        if price>1: inv[item]+=1
                        sells[pid][item]=sells[pid].get(item,0)+1
                        rev[pid][item]=rev[pid].get(item,0)+price; ok=True
                elif op=="BUY_PRODUCT":
                    if moneys[pid]>=price and sum(sheds[pid].values())<100:
                        moneys[pid]-=price; sheds[pid][item]=sheds[pid].get(item,0)+1; inv[item]-=1; ok=True
                elif op=="BUY_SEED":
                    if moneys[pid]>=price: moneys[pid]-=price; ok=True
                elif op=="BUY_ANIMAL":
                    if moneys[pid]>=price and sum(sheds[pid].values())<100: moneys[pid]-=price; sheds[pid][item]=sheds[pid].get(item,0)+1; ok=True
                if ok: os["remaining"]-=1; committed=True
                else: ostates[pid]=None
            if not committed: break
    return sells, rev

def scan_tiles(tiles):
    crop={c:0 for c in CROPS}; ani={a:0 for a in ANIMALS}
    fed=0; cared=0; nani=0
    for row in tiles:
        for t in row:
            if isinstance(t,dict):
                if t.get("kind")=="PLANT": crop[t["crop"]]=crop.get(t["crop"],0)+1
                elif "animal" in t:
                    ani[t["animal"]]+=1; nani+=1
                    if t.get("fed_today"): fed+=1
                    if t.get("cared_today"): cared+=1
    return crop,ani,nani,fed,cared

def analyze(path, us):
    d=json.load(open(path))
    steps=d['steps']; names=d['info']['TeamNames']
    opp=1-us
    # per-item cumulative sells/rev
    sold=[{p:[0,0.0] for p in PRODUCTS} for _ in range(2)]
    # per-day snapshots
    days={}
    hires=[0,0]; land_events=[[],[]]; melon_first=[None,None]
    daily=[]  # per (day) dict
    prev_hires_today=[0,0]
    for i,st in enumerate(steps):
        ob=st[0]['observation']
        day=ob['day']; hour=ob['hour']
        inv=ob['market']['inventory']
        prices=ob['market']['prices']
        farms=ob['farms']
        sheds=[st[p]['observation']['private'].get('shed',{}) or {} for p in range(2)]
        moneys=[farms[p]['money'] for p in range(2)]
        queues=[]
        nxt=steps[i+1] if i+1<len(steps) else None
        for p in range(2):
            act=(nxt[p].get('action') if nxt else None) or {}
            queues.append(act.get('market',[]) or [])
        # count hires/land from THIS step actions
        for p in range(2):
            for o in (queues[p] or []):
                if isinstance(o,list) and o and o[0]=="HIRE": hires[p]+=1
                if isinstance(o,list) and o and o[0]=="BUY_LAND": land_events[p].append((day,hour))
        # simulate sells
        sells,rev=sim_market(inv,sheds,moneys,queues)
        for p in range(2):
            for it,u in sells[p].items():
                sold[p][it][0]+=u
                sold[p][it][1]+=rev[p].get(it,0.0)
            if melon_first[p] is None and sells[p].get("MELON",0)>0:
                melon_first[p]=(day,hour)
        # snapshot at hour 23 (end of day) OR last step
        # collect per-day at hour 0 money and hour23 shed/tiles
        key=day
        if key not in days:
            days[key]={}
        if hour==0:
            for p in range(2):
                days[key][f'money_h0_{p}']=moneys[p]
        if hour==23 or i==len(steps)-1:
            for p in range(2):
                crop,ani,nani,fed,cared=scan_tiles(farms[p]['tiles'])
                days[key][f'shed_{p}']=dict(sheds[p])
                days[key][f'money_h23_{p}']=moneys[p]
                days[key][f'crop_{p}']=crop
                days[key][f'ani_{p}']=ani
                days[key][f'fed_{p}']=(fed,nani)
                days[key][f'prices']={it:prices[it] for it in PRODUCTS}
                days[key][f'quads_{p}']=farms[p].get('unlocked_quadrants',[])
                days[key][f'ninv_{p}']=len(farms[p].get('hands',[]))+1
    return d,names,us,opp,days,hires,land_events,sold,melon_first

if __name__=="__main__":
    pass
