import sys, os, importlib.util, statistics
from concurrent.futures import ProcessPoolExecutor
from kaggle_environments import make
ROOT="/Users/pradeepmahato/pradeep/kaggriculture"

# proxies matching live-data opponent mixes, built via sol6 farmlib build_agent
# vec order: melon,cows,sheep,geese,straw,tomato,wheat,he,hm,hl,buySE,thrF,thrE,fert,taper,wbuf,drop,aday,strawdl
PROXIES={
 "gideon":[12, 6, 10, 0, 33, 0, 24, 6, 8, 12, 1, 0.70, 0.70, 2, 27, 3, 9, 6, 18],
 "aru":   [12, 8, 6, 3, 33, 0, 24, 6, 8, 12, 1, 0.70, 0.70, 2, 27, 3, 9, 6, 15],
}

def make_agent(spec):
    # spec: ("main", path) or ("vec", dir, vec)
    kind=spec[0]
    if kind=="main":
        m=importlib.util.spec_from_file_location("m"+str(abs(hash(spec[1]))%9999), spec[1])
        mod=importlib.util.module_from_spec(m); m.loader.exec_module(mod); return mod.agent
    if kind=="vec":
        m=importlib.util.spec_from_file_location("fl"+str(abs(hash(spec[1]))%9999), spec[1]+"/farmlib.py")
        mod=importlib.util.module_from_spec(m); m.loader.exec_module(mod)
        return mod.build_agent(list(spec[2]))

def play(args):
    specA, specB, seed, swap = args
    a=make_agent(specA); b=make_agent(specB)
    env=make("kaggriculture", configuration={"seed":seed}, debug=False)
    if swap: env.run([b,a]); f=env.steps[-1]; return f[1]["reward"], f[0]["reward"]
    env.run([a,b]); f=env.steps[-1]; return f[0]["reward"], f[1]["reward"]

def duel(specA, specB, seeds):
    jobs=[]
    for s in seeds: jobs.append((specA,specB,s,False)); jobs.append((specA,specB,s,True))
    with ProcessPoolExecutor(max_workers=12) as ex:
        res=list(ex.map(play, jobs))
    a=[r[0] for r in res]; b=[r[1] for r in res]
    w=sum(1 for x,y in res if x>y); l=sum(1 for x,y in res if x<y)
    return statistics.mean(a), statistics.mean(b), statistics.mean(x-y for x,y in res), w,l,len(res)

if __name__=="__main__":
    seeds=list(range(200,216))
    sol5=("main",f"{ROOT}/sol5/main.py")
    sol6=("main",f"{ROOT}/sol6/main.py")
    for pname,pvec in PROXIES.items():
        prox=("vec",f"{ROOT}/sol6",pvec)
        for name,me in [("sol5",sol5),("sol6",sol6)]:
            am,bm,mg,w,l,n=duel(me,prox,seeds)
            print(f"  {name} vs {pname:7s}: me={am:8.0f} opp={bm:8.0f} margin={mg:+8.0f} W/L/T={w}/{l}/{n-w-l}")
        print()
