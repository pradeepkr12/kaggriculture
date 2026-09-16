import json
from kaggle_environments.envs.kaggriculture.kaggriculture import CROPS,ANIMALS,market_price,LAND_PRICES
def fib(n):
    a,b=1,1
    for _ in range(n): a,b=b,a+b
    return a
GAMES=[("/tmp/kag_eps/109310239.json",0,"LOSS Aru"),
       ("/tmp/kag_eps/109398887.json",0,"LOSS Riya"),
       ("/tmp/kag_eps/109501907.json",1,"LOSS Gideon"),
       ("/tmp/kag_eps/109391532.json",0,"WIN BiNar")]
for path,us,label in GAMES:
    d=json.load(open(path)); steps=d['steps']; names=d['info']['TeamNames']
    for p in [us,1-us]:
        who='US' if p==us else 'OPP'
        spend={'HIRE':0,'LAND':0,'SEED':0,'ANIMAL':0,'BUYPROD':0}
        hires_per_day={}
        # hires reset each day; track by day using hires_today from obs
        for i in range(1,len(steps)):
            act=(steps[i][p].get('action') or {})
            m=act.get('market',[]) or []
            ob=steps[i-1][p]['observation'] if False else steps[i-1][0]['observation']
            invmkt=steps[i-1][0]['observation']['market']['inventory']
            day=steps[i-1][0]['observation']['day']
            # hires need running count in day -> use farm hires_today at pre-state
            ht=steps[i-1][0]['observation']['farms'][p]['hires_today']
            k=ht
            for o in m:
                if not isinstance(o,list) or not o: continue
                if o[0]=='HIRE':
                    spend['HIRE']+=fib(k); k+=1
                elif o[0]=='BUY_LAND':
                    n_extra=len(steps[i-1][0]['observation']['farms'][p].get('unlocked_quadrants',['NW']))-1
                    if 0<=n_extra<3: spend['LAND']+=LAND_PRICES[n_extra]
                elif o[0]=='BUY_SEED':
                    spend['SEED']+=CROPS[o[1]]['seed']*int(o[2])
                elif o[0]=='BUY_ANIMAL':
                    spend['ANIMAL']+=ANIMALS[o[1]]['cost']*int(o[2])
                elif o[0]=='BUY_PRODUCT':
                    pr=market_price(o[1],invmkt[o[1]]-1)
                    spend['BUYPROD']+=pr*int(o[2])
        final=d['rewards'][p]
        totalspend=sum(spend.values())
        # sells = final - 3000 + spend  (approx; buyprod price approx)
        sells_est=final-3000+totalspend
        print(f"{label:11} {who:3} final={final:7.0f} spend total={totalspend:7.0f} "
              f"[HIRE {spend['HIRE']:.0f} LAND {spend['LAND']:.0f} SEED {spend['SEED']:.0f} "
              f"ANIMAL {spend['ANIMAL']:.0f} WHEAT/FERT {spend['BUYPROD']:.0f}]  sells~{sells_est:.0f}")
    print()
