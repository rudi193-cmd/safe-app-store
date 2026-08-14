import chess, random, os, copy
from itertools import permutations
def rs(): random.seed(int.from_bytes(os.urandom(8),"big"))
N=100

# ---------- CHESS (uniform random legal) ----------
def chess_once():
    b=chess.Board(); plies=0
    while not b.is_game_over(claim_draw=True) and plies<250:
        b.push(random.choice(list(b.legal_moves))); plies+=1
    if b.is_game_over(claim_draw=True):
        r=b.result(claim_draw=True)
        t=("checkmate" if b.is_checkmate() else "stalemate" if b.is_stalemate()
           else "insufficient" if b.is_insufficient_material()
           else "threefold" if b.can_claim_threefold_repetition()
           else "fifty-move" if b.can_claim_fifty_moves() else "draw")
    else:
        vals={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9}
        m=sum(len(b.pieces(p,chess.WHITE))*v-len(b.pieces(p,chess.BLACK))*v for p,v in vals.items())
        r="1-0" if m>=2 else "0-1" if m<=-2 else "1/2-1/2"; t="capped"
    w="P1" if r=="1-0" else "P2" if r=="0-1" else "draw"
    return w,plies,t

# ---------- CHECKERS (random legal, mandatory capture) ----------
DARK=lambda r,c:(r+c)%2==1
def ck_start():
    b={}
    for r in range(8):
        for c in range(8):
            if DARK(r,c):
                if r<3:b[(r,c)]='a'
                elif r>4:b[(r,c)]='h'
    return b
def ck_dirs(p): return {'a':[(1,-1),(1,1)],'h':[(-1,-1),(-1,1)]}.get(p,[(1,-1),(1,1),(-1,-1),(-1,1)])
def inb(r,c):return 0<=r<8 and 0<=c<8
def ck_caps(b,sq,p,cap):
    seqs=[];r,c=sq
    for dr,dc in ck_dirs(p):
        mr,mc=r+dr,c+dc;lr,lc=r+2*dr,c+2*dc
        if inb(lr,lc) and (lr,lc) not in b and (mr,mc) in b and b[(mr,mc)].lower()!=p.lower() and (mr,mc) not in cap:
            promo=(p=='a' and lr==7) or (p=='h' and lr==0); np=p.upper() if promo else p
            nc=cap|{(mr,mc)}
            if promo: seqs.append(((lr,lc),nc,np))
            else:
                cont=ck_caps(b,(lr,lc),np,nc)
                seqs+=cont if cont else [((lr,lc),nc,np)]
    return seqs
def ck_legal(b,side):
    caps=[];simp=[]
    for sq,p in list(b.items()):
        if p.lower()!=side:continue
        for e,cc,fp in ck_caps(b,sq,p,frozenset()): caps.append((sq,e,cc,fp))
    if caps:return caps
    for sq,p in list(b.items()):
        if p.lower()!=side:continue
        r,c=sq
        for dr,dc in ck_dirs(p):
            nr,nc=r+dr,c+dc
            if inb(nr,nc) and (nr,nc) not in b:
                fp=p.upper() if (p=='a' and nr==7) or (p=='h' and nr==0) else p
                simp.append((sq,(nr,nc),frozenset(),fp))
    return simp
def ck_apply(b,mv):
    sq,e,cc,fp=mv;nb=dict(b);del nb[sq]
    for x in cc:nb.pop(x,None)
    nb[e]=fp;return nb
def checkers_once():
    b=ck_start();side='a';m=0;since=0
    while True:
        L=ck_legal(b,side)
        if not L: return ('P2' if side=='a' else 'P1'),m
        mv=random.choice(L); iscap=len(mv[2])>0
        since=0 if iscap else since+1
        b=ck_apply(b,mv);m+=1
        opp='h' if side=='a' else 'a'
        if not any(p.lower()==opp for p in b.values()): return ('P1' if side=='a' else 'P2'),m
        if m>=300 or since>=60:
            aa=sum(2 if p=='A' else 1 for p in b.values() if p.lower()=='a')
            hh=sum(2 if p=='H' else 1 for p in b.values() if p.lower()=='h')
            return ('draw' if aa==hh else 'P1' if aa>hh else 'P2'),m
        side=opp

# ---------- BACKGAMMON (random legal per die) ----------
def bg_new():return {'pts':{24:2,13:5,8:3,6:5},'bar':0,'off':0}
def bg_block(o,q):return o['pts'].get(25-q,0)>=2
def bg_hit(o,q):return o['pts'].get(25-q,0)==1
def bg_home(me):return all(me['pts'].get(p,0)==0 for p in range(7,25)) and me['bar']==0
def bg_leg(me,o,d):
    mv=[]
    if me['bar']>0:
        q=25-d
        if not bg_block(o,q): mv.append(('enter',q,bg_hit(o,q)))
        return mv
    hm=bg_home(me); occ=[p for p in range(1,25) if me['pts'].get(p,0)>0]; mx=max(occ) if occ else 0
    for p in range(24,0,-1):
        if me['pts'].get(p,0)==0:continue
        q=p-d
        if q>=1:
            if not bg_block(o,q):mv.append(('move',p,q,bg_hit(o,q)))
        elif hm and (p==d or (d>p and p==mx)): mv.append(('off',p,False))
    return mv
def bg_apply(me,o,mv):
    me=copy.deepcopy(me);o=copy.deepcopy(o);k=mv[0]
    if k=='enter':
        _,q,h=mv;me['bar']-=1
        if h:o['pts'][25-q]=o['pts'].get(25-q,0)-1;o['bar']+=1
        me['pts'][q]=me['pts'].get(q,0)+1
    elif k=='move':
        _,p,q,h=mv;me['pts'][p]-=1
        if h:o['pts'][25-q]=o['pts'].get(25-q,0)-1;o['bar']+=1
        me['pts'][q]=me['pts'].get(q,0)+1
    else:
        _,p,_=mv;me['pts'][p]-=1;me['off']+=1
    me['pts']={a:b for a,b in me['pts'].items() if b>0};return me,o
def bg_turn(me,o,dice):
    best=None;bu=-1
    for order in set(permutations(dice)):
        m2,o2=copy.deepcopy(me),copy.deepcopy(o);used=0
        for d in order:
            L=bg_leg(m2,o2,d)
            if not L:continue
            m2,o2=bg_apply(m2,o2,random.choice(L));used+=1
        if used>bu:bu=used;best=(m2,o2)
    return best
def backgammon_once():
    W,B=bg_new(),bg_new()
    while True:
        a,b=random.randint(1,6),random.randint(1,6)
        if a!=b:break
    wt=a>b;dice=[a,b];t=0
    while True:
        if wt:W,B=bg_turn(W,B,dice)
        else:B,W=bg_turn(B,W,dice)
        if W['off']==15 or B['off']==15:
            win='P1' if W['off']==15 else 'P2';loser=B if W['off']==15 else W
            gam= loser['off']==0
            return win,t,gam
        t+=1
        if t>600:
            pw=sum(p*c for p,c in W['pts'].items())+W['bar']*25
            pb=sum(p*c for p,c in B['pts'].items())+B['bar']*25
            return ('P1' if pw<pb else 'P2'),t,False
        wt=not wt;d1,d2=random.randint(1,6),random.randint(1,6)
        dice=[d1,d2,d1,d2] if d1==d2 else [d1,d2]

# ---------- UNO official (random legal, single hand, 4p) ----------
COLORS=["R","Y","G","B"]
def uno_deck():
    d=[]
    for c in COLORS:
        d.append((c,"0"))
        for v in [str(n) for n in range(1,10)]+["S","R","D2"]:d+=[(c,v),(c,v)]
    d+=[("W","WILD")]*4+[("W","WD4")]*4;return d
def uno_once():
    deck=uno_deck();random.shuffle(deck)
    hands=[[deck.pop() for _ in range(7)] for _ in range(4)]
    while True:
        top=deck.pop()
        if top[1]=="WD4":deck.insert(0,top);random.shuffle(deck);continue
        break
    disc=[top];color=top[0] if top[0]!="W" else random.choice(COLORS);dir=1;turn=0;plies=0
    def draw(n):
        nonlocal deck,disc
        out=[]
        for _ in range(n):
            if not deck:
                k=disc[-1];deck=disc[:-1];disc=[k];random.shuffle(deck)
                if not deck:break
            out.append(deck.pop())
        return out
    def hascol(p):return any(c==color for c,v in hands[p])
    def playable(card,p):
        c,v=card
        if v=="WILD":return True
        if v=="WD4":return not hascol(p)
        return c==color or v==disc[-1][1]
    while plies<1000:
        p=turn;legal=[c for c in hands[p] if playable(c,p)]
        if not legal:
            d=draw(1);hands[p]+=d
            if d and playable(d[0],p):card=d[0]
            else:turn=(turn+dir)%4;plies+=1;continue
        else:card=random.choice(legal)
        hands[p].remove(card);disc.append(card)
        if card[0]!="W":color=card[0]
        if len(hands[p])==0:return f"P{p+1}",plies
        n=(turn+dir)%4;c,v=card
        if v=="WILD":color=random.choice(COLORS)
        elif v=="WD4":color=random.choice(COLORS);hands[n]+=draw(4);turn=(n+dir)%4;plies+=1;continue
        elif v=="D2":hands[n]+=draw(2);turn=(n+dir)%4;plies+=1;continue
        elif v=="S":turn=(n+dir)%4;plies+=1;continue
        elif v=="R":dir*=-1;turn=(p+dir)%4;plies+=1;continue
        turn=n;plies+=1
    return "draw",plies

# ---------- run all ----------
from collections import Counter
def summarize(name, results, seats, unit, extra=None):
    wins=Counter(r[0] for r in results)
    lens=[r[1] for r in results]
    line=f"### {name}  ·  {seats}p  ·  N={N}\n"
    order=[f"P{i}" for i in range(1,seats+1)]+["draw"]
    line+="| "+" | ".join(order)+" | avg len |\n|"+"---|"*(len(order)+1)+"\n"
    line+="| "+" | ".join(f"{wins.get(k,0)}" for k in order)+f" | {sum(lens)//len(lens)} {unit} |\n"
    if extra: line+=extra+"\n"
    return line


# ---------- THE LEDGER (our game, generic random 4p) ----------
def ledger_once():
    import random as R
    PROP={"kings":(lambda c:c[0]==13,4),"aces":(lambda c:c[0]==14,4),"face":(lambda c:c[0] in(11,12,13),12),
          "H":(lambda c:c[1]=="H",13),"S":(lambda c:c[1]=="S",13),"C":(lambda c:c[1]=="C",13),"D":(lambda c:c[1]=="D",13),
          "ten+":(lambda c:c[0]>=10,20),"red":(lambda c:c[1] in"HD",26),"black":(lambda c:c[1] in"CS",26)}
    DK={k:v[1] for k,v in PROP.items()}
    def bolder(a,b):
        if a is None:return True
        return b[0]>a[0] or (b[0]==a[0] and DK[b[1]]<DK[a[1]])
    seals=[0,0,0,0]
    while max(seals)<5:
        deck=[(r,s) for r in range(2,15) for s in "HDCS"];R.shuffle(deck)
        hands=[[deck.pop() for _ in range(4)] for _ in range(4)]
        allc=[c for h in hands for c in h]
        cur=None;cp=None;turn=R.randrange(4);guard=0
        while True:
            guard+=1
            if guard>50:break
            p=turn
            if cur is not None and (R.random()<0.5):  # call
                actual=sum(1 for c in allc if PROP[cur[1]][0](c))
                true=actual>=cur[0]
                if true: seals[cp]+=1   # caller wrong -> claimant scores
                else: seals[p]+=1       # caught -> caller scores
                break
            # raise/open
            cands=[]
            for prop in PROP:
                for N in range(1,17):
                    if bolder(cur,(N,prop)): cands.append((N,prop))
            cands=[x for x in cands if x[0]<= (cur[0]+3 if cur else 8)]
            if not cands:
                if cur is None: break
                actual=sum(1 for c in allc if PROP[cur[1]][0](c));true=actual>=cur[0]
                seals[cp if true else p]+=1;break
            cur=R.choice(cands);cp=p;turn=(turn+1)%4
    return f"P{seals.index(max(seals))+1}",sum(seals)

if __name__=="__main__":
    pass
