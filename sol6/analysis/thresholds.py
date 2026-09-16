import json, statistics
from kaggle_environments.envs.kaggriculture.kaggriculture import market_price,MARKET_PARAMS
PRODUCTS=["WHEAT","CARROT","TOMATO","STRAWBERRY","MELON","EGG","MILK","WOOL","FERTILIZER"]
def parse(o):
    if isinstance(o,list) and len(o)>=3 and o[0]=='SELL':
        try:n=int(o[2])
        except:return None
        return (o[1],n) if n>0 else None
    return None
# record price at which player sells each unit (capped by pre-step shed)
def analyze_seller(path, seller):
    d=json.load(open(path)); steps=d['steps']
    prices={it:[] for it in PRODUCTS}     # price per unit sold
    firstday={it:None for it in PRODUCTS}
    for i in range(len(steps)-1):
        inv=dict(steps[i][0]['observation']['market']['inventory'])
        day=steps[i][0]['observation']['day']; hour=steps[i][0]['observation']['hour']
        sheds=[dict(steps[i][p]['observation']['private'].get('shed',{}) or {}) for p in range(2)]
        moneys=[steps[i][0]['observation']['farms'][p]['money'] for p in range(2)]
        queues=[(steps[i+1][p].get('action') or {}).get('market',[]) or [] for p in range(2)]
        # lockstep both players (need both to move inventory correctly)
        parsed=[[parse(o) for o in q] for q in queues]
        rem=[[(x[1] if x else 0) for x in pl] for pl in parsed]
        maxlen=max((len(p) for p in parsed),default=0)
        for idx in range(maxlen):
            while True:
                quoted=[None,None]
                for p in range(2):
                    if idx<len(parsed[p]) and parsed[p][idx] and rem[p][idx]>0:
                        it=parsed[p][idx][0]
                        if it in PRODUCTS: quoted[p]=(it,market_price(it,inv[it]))
                if all(q is None for q in quoted): break
                did=False
                for p in range(2):
                    if quoted[p] is None: continue
                    it,pr=quoted[p]
                    if sheds[p].get(it,0)<=0: rem[p][idx]=0; continue
                    sheds[p][it]-=1
                    if p==seller:
                        prices[it].append(pr)
                        if firstday[it] is None: firstday[it]=(day,hour)
                    if pr>1: inv[it]+=1
                    rem[p][idx]-=1; did=True
                if not did: break
    return prices, firstday

GAMES=[("/tmp/kag_eps/109501907.json",0,"Gideon 111653 RANK1"),("/tmp/kag_eps/109310239.json",1,"Aru 98965"),("/tmp/kag_eps/109398887.json",1,"Riya 76856"),("/tmp/kag_eps/109391532.json",0,"US-sol5 in WIN")]
GAMES=[("/tmp/kag_eps/109501907.json",0,"Gideon 111653 RANK1"),("/tmp/kag_eps/109310239.json",1,"Aru 98965"),("/tmp/kag_eps/109398887.json",1,"Riya 76856"),("/tmp/kag_eps/109391532.json",0,"US-sol5 WIN")]
for path,seller,label in GAMES:
    prices,fd=analyze_seller(path,seller)
    print(f"\n=== {label} seller=P{seller} ===")
    print(f"  {'item':11}{'base':>5}{'n':>5}{'min$':>6}{'p10':>6}{'med':>6}{'max$':>6}  {'floor/base':>10}  first(d,h)")
    for it in PRODUCTS:
        ps=sorted(prices[it]); base=MARKET_PARAMS[it]['base']
        if not ps:
            print(f"  {it:11}{base:>5}{0:>5}"); continue
        p10=ps[max(0,len(ps)//10)]
        print(f"  {it:11}{base:>5}{len(ps):>5}{ps[0]:>6}{p10:>6}{ps[len(ps)//2]:>6}{ps[-1]:>6}  {ps[0]/base:>10.2f}  {fd[it]}")
