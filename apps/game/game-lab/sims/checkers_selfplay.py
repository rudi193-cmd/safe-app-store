import random, os
random.seed(int.from_bytes(os.urandom(8),"big"))
# English draughts. Ada = 'a' men (top, move +row), Heimdallr = 'h' (bottom, move -row). Kings 'A'/'H'.
DARK=lambda r,c: (r+c)%2==1
def start():
    b={}
    for r in range(8):
        for c in range(8):
            if DARK(r,c):
                if r<3: b[(r,c)]='a'
                elif r>4: b[(r,c)]='h'
    return b
def own(p,side): return p and p.lower()==side
def enemy(p,side): return p and p.lower()!=side
def dirs(p):
    if p=='a': return [(1,-1),(1,1)]
    if p=='h': return [(-1,-1),(-1,1)]
    return [(1,-1),(1,1),(-1,-1),(-1,1)]  # kings
def inb(r,c): return 0<=r<8 and 0<=c<8
def captures_from(b, sq, p, captured):
    # return list of full capture sequences: (endsq, captured_set, final_piece)
    seqs=[]; r,c=sq
    for dr,dc in dirs(p):
        mr,mc=r+dr,c+dc; lr,lc=r+2*dr,c+2*dc
        if inb(lr,lc) and (lr,lc) not in b and (mr,mc) in b and enemy(b[(mr,mc)], p.lower()) and (mr,mc) not in captured:
            np=p
            # promotion mid-jump ends the move (English rule)
            promo = (p=='a' and lr==7) or (p=='h' and lr==0)
            if promo: np=p.upper()
            newcap=captured|{(mr,mc)}
            if promo:
                seqs.append(((lr,lc),newcap,np))
            else:
                cont=captures_from({**{k:v for k,v in b.items()}}, (lr,lc), np, newcap)
                if cont:
                    for e,cc,fp in cont: seqs.append((e,cc,fp))
                else:
                    seqs.append(((lr,lc),newcap,np))
    return seqs
def legal(b, side):
    caps=[]; simples=[]
    for sq,p in list(b.items()):
        if not own(p,side): continue
        cs=captures_from(b, sq, p, frozenset())
        for e,cc,fp in cs: caps.append((sq,e,cc,fp))
    if caps: return caps, True
    for sq,p in list(b.items()):
        if not own(p,side): continue
        r,c=sq
        for dr,dc in dirs(p):
            nr,nc=r+dr,c+dc
            if inb(nr,nc) and (nr,nc) not in b:
                fp=p
                if (p=='a' and nr==7) or (p=='h' and nr==0): fp=p.upper()
                simples.append((sq,(nr,nc),frozenset(),fp))
    return simples, False
def apply(b, mv):
    sq,e,cc,fp=mv; nb=dict(b); del nb[sq]
    for cap in cc: nb.pop(cap,None)
    nb[e]=fp; return nb
def play():
    b=start(); side='a'; moves=0; since=0
    while True:
        mv_list, iscap = legal(b, side)
        if not mv_list:
            return ('h' if side=='a' else 'a'), moves, "no legal move"
        if iscap:
            mv=max(mv_list, key=lambda m:(len(m[2]), random.random()))
            since=0
        else:
            mv=random.choice(mv_list); since+=1
        b=apply(b, mv); moves+=1
        # opponent has pieces?
        opp='h' if side=='a' else 'a'
        if not any(own(p,opp) for p in b.values()):
            return side, moves, "all captured"
        if moves>=300 or since>=60:
            aa=sum(2 if p=='A' else 1 for p in b.values() if p.lower()=='a')
            hh=sum(2 if p=='H' else 1 for p in b.values() if p.lower()=='h')
            if aa==hh: return None, moves, "draw (material even)"
            return ('a' if aa>hh else 'h'), moves, f"adjudicated (material {aa}-{hh})"
        side=opp
NAME={'a':'Ada','h':'Heimdallr',None:'Draw'}
rows=[];A=H=D=0
for i in range(1,14):
    w,m,t=play(); rows.append((i,NAME[w],t,m))
    A+=w=='a';H+=w=='h';D+=w is None
out=["## Checkers (English draughts) — 13 rounds  ·  Ada vs Heimdallr","","| # | Winner | How | Moves |","|---|---|---|---|"]
for i,w,t,m in rows: out.append(f"| {i} | {w} | {t} | {m} |")
out+=["",f"**Tally — Ada {A} · Heimdallr {H} · Draws {D}.** Avg {sum(m for *_,m in rows)//13} moves."]
open("/root/_checkers_res.md","w").write("\n".join(out)); print("\n".join(out))
