import random, os
random.seed(int.from_bytes(os.urandom(8),"big"))
COLORS=["R","Y","G","B"]
def build_deck():
    d=[]
    for c in COLORS:
        d.append((c,"0"))
        for v in [str(n) for n in range(1,10)]+["S","R","D2"]: d+=[(c,v),(c,v)]
    d+=[("W","WILD")]*4+[("W","WD4")]*4
    return d
VAL={**{str(n):n for n in range(10)},"S":20,"R":20,"D2":20,"WILD":50,"WD4":50}
NAMES=["Gerald","Loki","Ada","FRANK"]; PERS=["chaos","ruthless","kind","methodical"]

class OfficialUno:
    def __init__(self,log):
        self.log=log; self.deck=build_deck(); random.shuffle(self.deck)
        self.hands=[[self.deck.pop() for _ in range(7)] for _ in range(4)]
        while True:
            top=self.deck.pop()
            if top[1]=="WD4": self.deck.insert(0,top); random.shuffle(self.deck); continue
            break
        self.discard=[top]; self.color=top[0] if top[0]!="W" else random.choice(COLORS)
        self.dir=1; self.turn=0
    def top(self): return self.discard[-1]
    def draw(self,n):
        out=[]
        for _ in range(n):
            if not self.deck:
                keep=self.discard[-1]; self.deck=self.discard[:-1]; self.discard=[keep]; random.shuffle(self.deck)
                if not self.deck: break
            out.append(self.deck.pop())
        return out
    def has_color(self,p): return any(c==self.color for c,v in self.hands[p])
    def playable(self,card,p):
        c,v=card
        if v=="WILD": return True
        if v=="WD4": return not self.has_color(p)          # OFFICIAL restriction
        return c==self.color or v==self.top()[1]
    def choose_color(self,p):
        cnt={c:0 for c in COLORS}
        for c,v in self.hands[p]:
            if c in cnt: cnt[c]+=1
        m=max(cnt.values()); return random.choice([c for c in COLORS if cnt[c]==m])
    def pick(self,p):
        legal=[card for card in self.hands[p] if self.playable(card,p)]
        if not legal: return None
        per=PERS[p]
        def k(card):
            c,v=card;s=0
            if per=="chaos": s+=3 if c=="W" else (2 if v in("S","R","D2") else 0)
            if per=="ruthless": s+=5 if v in("D2","WD4") else (2 if v=="S" else 0)
            if per=="kind": s+=-3 if c=="W" else VAL.get(v,0)*0.1
            if per=="methodical": s+=(-4 if c=="W" else 0)+(1 if c==self.color else 0)
            return s+VAL.get(v,0)*0.05+random.random()
        return max(legal,key=k)
    def nxt(self,p): return (p+self.dir)%4
    def run_hand(self,hn):
        self.log.append(f"\n### Hand {hn} — up-card {self.top()[0]}{self.top()[1]} (color {self.color})")
        g=0
        while True:
            g+=1
            if g>2000: return min(range(4),key=lambda i:len(self.hands[i]))
            p=self.turn; card=self.pick(p)
            if card is None:
                d=self.draw(1); self.hands[p]+=d
                if d and self.playable(d[0],p):
                    card=d[0]; self.log.append(f"  {NAMES[p]} draws and plays {card[0]}{card[1]}.")
                else:
                    self.log.append(f"  {NAMES[p]} draws and passes."); self.turn=self.nxt(p); continue
            else:
                self.log.append(f"  {NAMES[p]} plays {card[0]}{card[1]}.")
            legal_wd4 = (card[1]=="WD4") and (not self.has_color_before(p,card))  # legality recorded pre-removal
            self.hands[p].remove(card); self.discard.append(card)
            if card[0]!="W": self.color=card[0]
            # Uno
            if len(self.hands[p])==1:
                if random.random()<0.9: self.log.append(f"    {NAMES[p]}: \"UNO!\"")
                else: self.hands[p]+=self.draw(2); self.log.append(f"    {NAMES[p]} forgot Uno — draws 2.")
            if len(self.hands[p])==0: return p
            n=self.nxt(p); c,v=card
            if v=="WILD": self.color=self.choose_color(p); self.log.append(f"    calls {self.color}.")
            elif v=="S": self.log.append(f"    Skip → {NAMES[n]} skipped."); self.turn=self.nxt(n); continue
            elif v=="R": self.dir*=-1; self.log.append(f"    Reverse."); self.turn=self.nxt(p); continue
            elif v=="D2":
                self.hands[n]+=self.draw(2); self.log.append(f"    {NAMES[n]} draws 2 & skipped."); self.turn=self.nxt(n); continue
            elif v=="WD4":
                self.color=self.choose_color(p)
                # OFFICIAL challenge: next player may challenge (rarely; usually backfires since play is legal)
                if random.random()<0.15:
                    if not legal_wd4:
                        self.hands[p]+=self.draw(4); self.log.append(f"    {NAMES[n]} challenges — {NAMES[p]} was ILLEGAL, draws 4. {NAMES[n]} plays on.")
                        self.turn=n; continue
                    else:
                        self.hands[n]+=self.draw(6); self.log.append(f"    {NAMES[n]} challenges and is WRONG — draws 6 & skipped.")
                        self.turn=self.nxt(n); continue
                else:
                    self.hands[n]+=self.draw(4); self.log.append(f"    calls {self.color}; {NAMES[n]} draws 4 & skipped."); self.turn=self.nxt(n); continue
            self.turn=n
    def has_color_before(self,p,card):
        # was there a color match in hand at play time (card still in hand)? for WD4 legality
        return any(c==self.color for c,v in self.hands[p] if (c,v)!=card) and card[1]=="WD4" and False or any(c==self.color for c,v in self.hands[p] if not (c==card[0] and v==card[1]))

def score(hands,w): return sum(VAL.get(v,0) for i,h in enumerate(hands) if i!=w for c,v in h)
log=[]; totals=[0,0,0,0]; wins=[0,0,0,0]; hn=0; first=None
while max(totals)<500 and hn<40:
    hn+=1; hl=[]; g=OfficialUno(hl); w=g.run_hand(hn); pts=score(g.hands,w); totals[w]+=pts; wins[w]+=1
    hl.append(f"  → **{NAMES[w]} out.** +{pts}. Totals: "+", ".join(f"{NAMES[i]} {totals[i]}" for i in range(4)))
    if hn==1: first=hl
    if hn>1: log.append(f"\n**Hand {hn}:** {NAMES[w]} out (+{pts}). "+ " · ".join(f"{NAMES[i]} {totals[i]}" for i in range(4)))
champ=max(range(4),key=lambda i:totals[i])
out=["## Uno — OFFICIAL rules — Gerald · Loki · Ada · FRANK","","*Restricted+challengeable Wild Draw Four, NO stacking, NO 7-0. Full Hand 1, then to 500.*"]
out+=first; out.append("\n---\n### The rest"); out+=log
out.append(f"\n---\n## Final (OFFICIAL)\n**{NAMES[champ]} wins with {totals[champ]}** after {hn} hands. "
           +" · ".join(f"{NAMES[i]} {totals[i]} ({wins[i]}h)" for i in range(4)))
open("/root/_uno_official_game.md","w").write("\n".join(out))
print("\n".join(out[:40])); print("...\n[OFFICIAL hands:",hn,"champ:",NAMES[champ],totals,"]")
