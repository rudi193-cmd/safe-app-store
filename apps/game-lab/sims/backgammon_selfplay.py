import random, os, copy
from itertools import permutations
random.seed(int.from_bytes(os.urandom(8),"big"))
def newp(): return {'pts':{24:2,13:5,8:3,6:5},'bar':0,'off':0}
def blocked(opp,q): return opp['pts'].get(25-q,0)>=2
def is_hit(opp,q): return opp['pts'].get(25-q,0)==1
def home(me): return all(me['pts'].get(p,0)==0 for p in range(7,25)) and me['bar']==0
def maxpt(me): 
    o=[p for p in range(1,25) if me['pts'].get(p,0)>0]; return max(o) if o else 0
def legal(me,opp,d):
    mv=[]
    if me['bar']>0:
        q=25-d
        if not blocked(opp,q): mv.append(('enter',q,is_hit(opp,q)))
        return mv
    hm=home(me); mx=maxpt(me)
    for p in range(24,0,-1):
        if me['pts'].get(p,0)==0: continue
        q=p-d
        if q>=1:
            if not blocked(opp,q): mv.append(('move',p,q,is_hit(opp,q)))
        elif hm:
            if p==d or (d>p and p==mx): mv.append(('off',p,False))
    return mv
def apply(me,opp,mv):
    me=copy.deepcopy(me); opp=copy.deepcopy(opp)
    k=mv[0]
    if k=='enter':
        _,q,hit=mv; me['bar']-=1
        if hit: opp['pts'][25-q]=opp['pts'].get(25-q,0)-1; opp['bar']+=1
        me['pts'][q]=me['pts'].get(q,0)+1
    elif k=='move':
        _,p,q,hit=mv; me['pts'][p]-=1
        if hit: opp['pts'][25-q]=opp['pts'].get(25-q,0)-1; opp['bar']+=1
        me['pts'][q]=me['pts'].get(q,0)+1
    elif k=='off':
        _,p,_=mv; me['pts'][p]-=1; me['off']+=1
    me['pts']={k2:v for k2,v in me['pts'].items() if v>0}
    return me,opp
def score(me,mv):
    k=mv[0]
    if k=='off': return 100+random.random()
    if k=='enter': return 50+(30 if mv[2] else 0)+random.random()
    _,p,q,hit=mv
    s=0
    if hit: s+=30
    if me['pts'].get(q,0)>=1: s+=6      # land on own point (safe/makes point)
    else: s-=2                          # leaves a blot
    s+=(24-q)*0.1                       # advance toward home
    return s+random.random()
def turn(me,opp,dice):
    best=None;bu=-1
    for order in set(permutations(dice)):
        m2,o2=copy.deepcopy(me),copy.deepcopy(opp); used=0
        for d in order:
            lm=legal(m2,o2,d)
            if not lm: continue
            mv=max(lm,key=lambda x:score(m2,x)); m2,o2=apply(m2,o2,mv); used+=1
        if used>bu: bu=used;best=(m2,o2)
    return best
def pip(me): return sum(p*c for p,c in me['pts'].items())+me['bar']*25
def play():
    W,B=newp(),newp()
    # opening roll
    while True:
        a,b=random.randint(1,6),random.randint(1,6)
        if a!=b: break
    turn_white = a>b
    dice=[a,b]
    t=0
    while True:
        if turn_white: W,B=turn(W,B,dice)
        else: B,W=turn(B,W,dice)
        # win?
        if W['off']==15 or B['off']==15:
            win='Gerald' if W['off']==15 else 'Nestor'
            loser=B if W['off']==15 else W
            val=1
            if loser['off']==0:
                val=3 if (loser['bar']>0 or any(loser['pts'].get(p,0)>0 for p in range(19,25))) else 2
            return win,val,t
        t+=1
        if t>500:
            pw,pb=pip(W),pip(B)
            return ('Gerald' if pw<pb else 'Nestor'),1,t
        turn_white=not turn_white
        d1,d2=random.randint(1,6),random.randint(1,6)
        dice=[d1,d2,d1,d2] if d1==d2 else [d1,d2]
LBL={1:"single",2:"GAMMON (2x)",3:"BACKGAMMON (3x)"}
rows=[];G=N=0;gpts=npts=0
for i in range(1,14):
    w,v,t=play(); rows.append((i,w,LBL[v],t))
    if w=='Gerald':G+=1;gpts+=v
    else:N+=1;npts+=v
out=["## Backgammon — 13 rounds  ·  Gerald vs Nestor","","| # | Winner | Result | Turns |","|---|---|---|---|"]
for i,w,l,t in rows: out.append(f"| {i} | {w} | {l} | {t} |")
out+=["",f"**Tally — Gerald {G} games / {gpts} pts · Nestor {N} games / {npts} pts.** "
      f"Avg {sum(t for *_,t in rows)//13} turns. Gammons/backgammons: {sum(1 for *_,l,_ in [(r[0],r[1],r[2],r[3]) for r in rows] if 'x' in l)}."]
open("/root/_bg_res.md","w").write("\n".join(out)); print("\n".join(out))
