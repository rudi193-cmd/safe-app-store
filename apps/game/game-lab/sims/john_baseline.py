import baseline_core as bc, chess, random, os, copy
from itertools import permutations
from collections import Counter
random.seed(int.from_bytes(os.urandom(8),"big"))
N=100
VAL={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9,chess.KING:0}

# ---- CHESS John (greedy, recapture-aware; identical both seats) ----
def john_move(b):
    best,bs=None,-1e9
    for mv in b.legal_moves:
        sc=0.0
        if mv.promotion: sc+=8
        ap=b.piece_at(mv.from_square); atk=VAL[ap.piece_type] if ap else 0
        cap=b.is_capture(mv); cv=0
        if cap:
            cp=b.piece_at(mv.to_square); cv=VAL[cp.piece_type] if cp else 1
        b.push(mv); mate=b.is_checkmate(); chk=b.is_check(); recap=b.is_attacked_by(b.turn,mv.to_square); b.pop()
        if cap: sc+=cv-(atk if recap else 0)
        if mate: sc+=1000
        elif chk: sc+=0.3
        if not cap: sc+=0.06*(mv.to_square in (chess.D4,chess.E4,chess.D5,chess.E5))
        sc+=random.random()*0.4
        if sc>bs: bs,best=sc,mv
    return best
def chess_john():
    b=chess.Board(); plies=0
    while not b.is_game_over(claim_draw=True) and plies<250:
        b.push(john_move(b)); plies+=1
    if b.is_game_over(claim_draw=True):
        r=b.result(claim_draw=True); t=("checkmate" if b.is_checkmate() else "stalemate" if b.is_stalemate()
           else "insufficient" if b.is_insufficient_material() else "draw")
    else:
        m=sum(len(b.pieces(p,chess.WHITE))*v-len(b.pieces(p,chess.BLACK))*v for p,v in VAL.items())
        r="1-0" if m>=2 else "0-1" if m<=-2 else "1/2-1/2"; t="capped"
    return ("P1" if r=="1-0" else "P2" if r=="0-1" else "draw"),plies,t

# ---- CHECKERS John (max-capture, else advance) ----
def checkers_john():
    b=bc.ck_start(); side='a'; m=0; since=0
    while True:
        L=bc.ck_legal(b,side)
        if not L: return ('P2' if side=='a' else 'P1'),m
        caps=[mv for mv in L if len(mv[2])>0]
        if caps: mv=max(caps,key=lambda x:(len(x[2]),random.random())); since=0
        else:
            def adv(mv):
                nr=mv[1][0]; return nr if side=='a' else 7-nr
            mv=max(L,key=lambda x:(adv(x),random.random())); since+=1
        b=bc.ck_apply(b,mv); m+=1
        opp='h' if side=='a' else 'a'
        if not any(p.lower()==opp for p in b.values()): return ('P1' if side=='a' else 'P2'),m
        if m>=300 or since>=60:
            aa=sum(2 if p=='A' else 1 for p in b.values() if p.lower()=='a')
            hh=sum(2 if p=='H' else 1 for p in b.values() if p.lower()=='h')
            return ('draw' if aa==hh else 'P1' if aa>hh else 'P2'),m
        side=opp

# ---- BACKGAMMON John (off>hit>make>advance) ----
def jscore(me,mv):
    k=mv[0]
    if k=='off': return 100+random.random()
    if k=='enter': return 50+(30 if mv[2] else 0)+random.random()
    _,p,q,hit=mv; s=0
    if hit: s+=30
    s+= 6 if me['pts'].get(q,0)>=1 else -2
    return s+(24-q)*0.1+random.random()
def john_bg_turn(me,o,dice):
    best=None;bu=-1
    for order in set(permutations(dice)):
        m2,o2=copy.deepcopy(me),copy.deepcopy(o);used=0
        for d in order:
            L=bc.bg_leg(m2,o2,d)
            if not L: continue
            mv=max(L,key=lambda x:jscore(m2,x)); m2,o2=bc.bg_apply(m2,o2,mv); used+=1
        if used>bu:bu=used;best=(m2,o2)
    return best
def backgammon_john():
    W,B=bc.bg_new(),bc.bg_new()
    while True:
        a,b=random.randint(1,6),random.randint(1,6)
        if a!=b:break
    wt=a>b;dice=[a,b];t=0
    while True:
        if wt:W,B=john_bg_turn(W,B,dice)
        else:B,W=john_bg_turn(B,W,dice)
        if W['off']==15 or B['off']==15:
            return ('P1' if W['off']==15 else 'P2'),t,((B if W['off']==15 else W)['off']==0)
        t+=1
        if t>600:
            pw=sum(p*c for p,c in W['pts'].items())+W['bar']*25; pb=sum(p*c for p,c in B['pts'].items())+B['bar']*25
            return ('P1' if pw<pb else 'P2'),t,False
        wt=not wt;d1,d2=random.randint(1,6),random.randint(1,6);dice=[d1,d2,d1,d2] if d1==d2 else [d1,d2]

# ---- UNO John (match color, dump high, save wilds) ----
UV={**{str(n):int(n) for n in range(10)},"S":15,"R":15,"D2":16,"WILD":-5,"WD4":-4}
def uno_john():
    deck=bc.uno_deck();random.shuffle(deck)
    hands=[[deck.pop() for _ in range(7)] for _ in range(4)]
    while True:
        top=deck.pop()
        if top[1]=="WD4":deck.insert(0,top);random.shuffle(deck);continue
        break
    disc=[top];color=top[0] if top[0]!="W" else random.choice(bc.COLORS);dir=1;turn=0;plies=0
    def draw(n):
        nonlocal deck,disc;out=[]
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
    def most_color(p):
        cnt={c:0 for c in bc.COLORS}
        for c,v in hands[p]:
            if c in cnt:cnt[c]+=1
        m=max(cnt.values());return random.choice([c for c in bc.COLORS if cnt[c]==m])
    while plies<1000:
        p=turn;legal=[c for c in hands[p] if playable(c,p)]
        if not legal:
            d=draw(1);hands[p]+=d
            if d and playable(d[0],p):card=d[0]
            else:turn=(turn+dir)%4;plies+=1;continue
        else:card=max(legal,key=lambda c:(UV[c[1]],random.random()))
        hands[p].remove(card);disc.append(card)
        if card[0]!="W":color=card[0]
        if len(hands[p])==0:return f"P{p+1}",plies
        n=(turn+dir)%4;c,v=card
        if v=="WILD":color=most_color(p)
        elif v=="WD4":color=most_color(p);hands[n]+=draw(4);turn=(n+dir)%4;plies+=1;continue
        elif v=="D2":hands[n]+=draw(2);turn=(n+dir)%4;plies+=1;continue
        elif v=="S":turn=(n+dir)%4;plies+=1;continue
        elif v=="R":dir*=-1;turn=(p+dir)%4;plies+=1;continue
        turn=n;plies+=1
    return "draw",plies

# ---- THE LEDGER John (honest bid + EV call) ----
def ledger_john():
    PROP={"kings":(lambda c:c[0]==13,4),"aces":(lambda c:c[0]==14,4),"face":(lambda c:c[0] in(11,12,13),12),
          "H":(lambda c:c[1]=="H",13),"S":(lambda c:c[1]=="S",13),"C":(lambda c:c[1]=="C",13),"D":(lambda c:c[1]=="D",13),
          "ten+":(lambda c:c[0]>=10,20),"red":(lambda c:c[1] in"HD",26),"black":(lambda c:c[1] in"CS",26)}
    DK={k:v[1] for k,v in PROP.items()}
    def bolder(a,b):
        if a is None:return True
        return b[0]>a[0] or (b[0]==a[0] and DK[b[1]]<DK[a[1]])
    seals=[0,0,0,0]
    while max(seals)<5:
        deck=[(r,s) for r in range(2,15) for s in "HDCS"];random.shuffle(deck)
        hands=[[deck.pop() for _ in range(4)] for _ in range(4)]
        allc=[c for h in hands for c in h]
        cur=None;cp=None;turn=random.randrange(4);guard=0
        while True:
            guard+=1
            if guard>50:break
            p=turn
            own=hands[p]
            def believe(prop):
                oc=sum(1 for c in own if PROP[prop][0](c))
                return oc+(12)*(DK[prop]-oc)/48.0
            if cur is not None:
                # John calls if current bid quantity exceeds his believed count
                if cur[0]>believe(cur[1])+0.5:
                    actual=sum(1 for c in allc if PROP[cur[1]][0](c));true=actual>=cur[0]
                    seals[cp if true else p]+=1;break
            # else raise honestly: lowest bolder claim John believes true
            cands=[]
            for prop in PROP:
                bel=believe(prop)
                for Nn in range(1,17):
                    if Nn<=bel+0.5 and bolder(cur,(Nn,prop)): cands.append((Nn,prop))
            if not cands:
                if cur is None:
                    # open with a safe honest claim
                    prop=max(PROP,key=lambda pr:believe(pr)); cur=(max(1,int(believe(prop))),prop);cp=p;turn=(turn+1)%4;continue
                actual=sum(1 for c in allc if PROP[cur[1]][0](c));true=actual>=cur[0]
                seals[cp if true else p]+=1;break
            cur=min(cands,key=lambda x:(x[0],DK[x[1]]));cp=p;turn=(turn+1)%4
    return f"P{seals.index(max(seals))+1}",sum(seals)

def block(name,res,seats,unit,extra=""):
    w=Counter(r[0] for r in res);ln=[r[1] for r in res]
    ks=[f"P{i}" for i in range(1,seats+1)]+["draw"]
    s=f"### {name} · {seats}p · N={N} · ALL-JOHN\n| "+" | ".join(ks)+" | avg |\n|"+"---|"*(len(ks)+1)+"\n"
    s+="| "+" | ".join(str(w.get(k,0)) for k in ks)+f" | {sum(ln)//len(ln)} {unit} |"
    if extra:s+="\n"+extra
    return s
if __name__=="__main__":
    out=[]
    r=[chess_john() for _ in range(N)];tm=Counter(x[2] for x in r)
    out.append(block("Chess",[(x[0],x[1]) for x in r],2,"plies","term: "+", ".join(f"{k} {v}" for k,v in tm.most_common())))
    out.append(block("Checkers",[checkers_john() for _ in range(N)],2,"moves"))
    r=[backgammon_john() for _ in range(N)];g=sum(1 for x in r if x[2])
    out.append(block("Backgammon",[(x[0],x[1]) for x in r],2,"turns",f"gammons {g}/{N}"))
    out.append(block("Uno (1 hand)",[uno_john() for _ in range(N)],4,"plies"))
    out.append(block("The Ledger",[ledger_john() for _ in range(N)],4,"seals"))
    open("/root/_john_core.md","w").write("\n\n".join(out));print("\n\n".join(out))
