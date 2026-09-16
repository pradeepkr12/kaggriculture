import json
from kaggle_environments.envs.kaggriculture.kaggriculture import market_price,CROPS,ANIMALS
PRODUCTS=["WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER"]
def parse(o):
    if not isinstance(o,list) or not o: return None
    if o[0]=='SELL' and len(o)>=3:
        try:n=int(o[2])
        except:return None
        return ['SELL',o[1],n] if n>0 else None
    return None
def sim(inv,queues):
    inv=dict(inv); sells=[{},{}]; rev=[{},{}]
    qs=[[parse(o) for o in q if parse(o)] for q in queues]
    maxlen=max((len(q) for q in qs),default=0)
    rem=[[o[2] for o in q] for q in qs]
    for i in range(maxlen):
        while True:
            quoted=[None,None]
            for p in range(2):
                if i<len(qs[p]) and rem[p][i]>0:
                    it=qs[p][i][1]
                    if it in PRODUCTS: quoted[p]=(it,market_price(it,inv[it]))
            if all(q is None for q in quoted): break
            did=False
            for p in range(2):
                if quoted[p] is None: continue
                it,price=quoted[p]
                sells[p][it]=sells[p].get(it,0)+1; rev[p][it]=rev[p].get(it,0)+price
                if price>1: inv[it]+=1
                rem[p][i]-=1; did=True
            if not did: break
    return sells,rev
GAMES=[("/tmp/kag_eps/109310239.json",0,"Aru"),("/tmp/kag_eps/109398887.json",0,"Riya"),
       ("/tmp/kag_eps/109501907.json",1,"Gideon"),("/tmp/kag_eps/109391532.json",0,"BiNar")]
for path,us,label in GAMES:
    d=json.load(open(path)); steps=d['steps']
    tot=[{it:[0,0.0] for it in PRODUCTS} for _ in range(2)]
    for i in range(len(steps)-1):
        inv=steps[i][0]['observation']['market']['inventory']
        queues=[(steps[i+1][p].get('action') or {}).get('market',[]) or [] for p in range(2)]
        s,r=sim(inv,queues)
        for p in range(2):
            for it in s[p]: tot[p][it][0]+=s[p][it]; tot[p][it][1]+=r[p][it]
    print(f"=== {label} (uncapped) us=P{us}")
    print(f"  {'item':11}{'US u':>7}{'US $':>9}{'OPP u':>7}{'OPP $':>9}")
    tu=to=0
    for it in PRODUCTS:
        uu,ur=tot[us][it]; ou,orv=tot[1-us][it]; tu+=ur; to+=orv
        print(f"  {it:11}{uu:>7}{ur:>9.0f}{ou:>7}{orv:>9.0f}")
    print(f"  {'TOTAL':11}{'':>7}{tu:>9.0f}{'':>7}{to:>9.0f}\n")
