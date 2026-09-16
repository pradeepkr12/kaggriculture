import sys, os, importlib.util, statistics
from concurrent.futures import ProcessPoolExecutor
from kaggle_environments import make
ROOT="/Users/pradeepmahato/pradeep/kaggriculture"

def load(name, path):
    spec=importlib.util.spec_from_file_location(name, path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.agent

def play(args):
    seed, swap = args
    a=load("sol6m", f"{ROOT}/sol6/main.py")
    b=load("sol5m", f"{ROOT}/sol5/main.py")
    env=make("kaggriculture", configuration={"seed":seed}, debug=False)
    if swap: env.run([b,a]); f=env.steps[-1]; return f[1]["reward"], f[0]["reward"]
    else: env.run([a,b]); f=env.steps[-1]; return f[0]["reward"], f[1]["reward"]

if __name__=="__main__":
    seeds=list(range(300,332))
    jobs=[]
    for s in seeds: jobs.append((s,False)); jobs.append((s,True))
    with ProcessPoolExecutor(max_workers=12) as ex:
        res=list(ex.map(play, jobs))
    a=[r[0] for r in res]; b=[r[1] for r in res]
    w=sum(1 for x,y in res if x>y); l=sum(1 for x,y in res if x<y)
    print(f"sol6 vs sol5 (contested, {len(res)} games, both seats)")
    print(f"  sol6 avg={statistics.mean(a):.0f}  sol5 avg={statistics.mean(b):.0f}  margin={statistics.mean(x-y for x,y in res):+.0f}")
    print(f"  W/L/T = {w}/{l}/{len(res)-w-l}")
    print(f"  sol6 range [{min(a):.0f},{max(a):.0f}]  sol5 range [{min(b):.0f},{max(b):.0f}]")
