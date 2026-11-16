#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A complete end-to-end game of THE LEDGER, played by the guardians. Real deck,
real hidden hands, personality-driven bluffing/calling. Narrated transcript."""
import random, os, math
random.seed(int.from_bytes(os.urandom(8),"big"))

SUITS="HDCS"; RANKS=list(range(2,15))  # 11=J,12=Q,13=K,14=A
def deck(): return [(r,s) for r in RANKS for s in SUITS]
RANKNAME={11:"J",12:"Q",13:"K",14:"A"}
def rn(r): return RANKNAME.get(r,str(r))
def cardstr(c): return f"{rn(c[0])}{c[1]}"

# properties: name -> (predicate, count-in-52, rarity_rank lower=rarer=bolder)
PROPS = {
 "kings":  (lambda c: c[0]==13, 4),
 "aces":   (lambda c: c[0]==14, 4),
 "face":   (lambda c: c[0] in (11,12,13), 12),
 "hearts": (lambda c: c[1]=="H", 13),
 "spades": (lambda c: c[1]=="S", 13),
 "clubs":  (lambda c: c[1]=="C", 13),
 "diamonds":(lambda c: c[1]=="D",13),
 "ten-plus":(lambda c: c[0]>=10, 20),
 "red":    (lambda c: c[1] in "HD", 26),
 "black":  (lambda c: c[1] in "CS", 26),
}
DECKCT={k:v[1] for k,v in PROPS.items()}
def cnt(cards,prop): p=PROPS[prop][0]; return sum(1 for c in cards if p(c))

def bolder(a,b):
    """is claim b strictly bolder than claim a? claim=(N,prop)"""
    if a is None: return True
    (na,pa),(nb,pb)=a,b
    if nb>na: return True
    if nb==na and DECKCT[pb]<DECKCT[pa]: return True
    return False

PLAYERS=["Gerald","Loki","FRANK","Heimdallr","Ada","Willow"]
# personality: (call_bias, bluff_bias)  higher call_bias => calls more; higher bluff => overclaims
PERS={
 "Gerald":  (0.06, 1.15),  # lies often but not suicidally; sometimes the lie is nearly true
 "Loki":    (0.80, 0.45),  # the auditor: calls hard, plays for the catch
 "FRANK":   (0.42, 0.30),  # honest, careful, remembers
 "Heimdallr":(0.50,0.35),  # orderly, principled caller
 "Ada":     (0.30, 0.75),  # warm, gambles, a quiet bluffer
 "Willow":  (0.38, 0.55),  # reads the room
}
FLAV_CALL={"Loki":"Checked. You've been talking too long.","Heimdallr":"That does not pass. Checked.",
 "FRANK":"I've been keeping count. Checked.","Ada":"Mm — I don't think so, love. Checked.",
 "Willow":"...no. Checked.","Gerald":"Reluctantly, and against my nature: checked."}

def est_total(own, prop, n_players):
    """expected total of prop across all hands given own hand."""
    ownc=cnt(own,prop); others=(n_players-1)*4
    remaining=DECKCT[prop]-ownc
    exp=ownc + others*max(0,remaining)/48.0
    sd=math.sqrt(max(0.25, others*(remaining/48.0)*(1-remaining/48.0)))
    return exp, sd
def p_true(own,prop,N,n_players):
    exp,sd=est_total(own,prop,n_players)
    # P(total >= N) via normal approx
    z=(N-0.5-exp)/sd
    return 0.5*math.erfc(z/math.sqrt(2))

LOG=[]
def out(s): LOG.append(s)

seals={p:3 for p in PLAYERS}
successful_calls={p:0 for p in PLAYERS}
clean_bluffs={p:0 for p in PLAYERS}      # false claims that were raised-over, not called
wild_used={"Gerald":False}
apple_used={"Ada":False}
WIN=8
nestor_idx=0
hand_no=0
ledger=[]

def alive(): return [p for p in PLAYERS if seals[p]>0]

out("# THE LEDGER — one complete game")
out(f"*Players: {', '.join(PLAYERS)}. Everyone starts on 3 seals. First to {WIN} takes the Win. "
    "Nestor token (the honest seat) rotates clockwise. Real deck, real hidden hands.*\n")

def notable(line): out(line)

while max(seals.values())<WIN and len(alive())>1 and hand_no<60:
    hand_no+=1
    order=[p for p in PLAYERS if seals[p]>0]
    if len(order)<2: break
    d=deck(); random.shuffle(d)
    hands={p:[d.pop() for _ in range(4)] for p in order}
    allcards=[c for h in hands.values() for c in h]
    # who holds nestor token (skip broke)
    while PLAYERS[nestor_idx%len(PLAYERS)] not in order: nestor_idx+=1
    nestor=PLAYERS[nestor_idx%len(PLAYERS)]
    lead=f"Hand {hand_no}"
    seat=f"  · honest seat: {nestor}"
    chain=[]   # list of (player, (N,prop))
    # opening player: left of nestor
    start=(order.index(nestor)+1)%len(order)
    turn=start
    current=None; current_player=None
    called=False; caller=None
    passes=0
    # build the claim chain
    guard=0
    while True:
        guard+=1
        if guard>40: break
        p=order[turn%len(order)]
        is_nestor=(p==nestor)
        # decide: call or raise/open
        if current is not None:
            pt=p_true(hands[p],current[1],current[0],len(order))
            cb=PERS[p][0]
            # Loki re-open / aggression baked into cb
            want_call = pt < (0.45 if is_nestor else (0.55 if p=="Loki" else 0.28)) and random.random()<(cb+0.30)
            # can we raise truthfully (nestor) or plausibly?
            if is_nestor:
                # nestor may only claim N<=own count for a prop; find a bolder truthful claim
                opt=None
                for prop in PROPS:
                    oc=cnt(hands[p],prop)
                    for N in range(current[0], oc+1):
                        cand=(N,prop)
                        if bolder(current,cand): opt=cand; break
                    if opt: break
                if opt and not want_call:
                    current=opt; current_player=p; chain.append((p,opt))
                    out(f"- **{p}** (honest seat) raises truthfully → *at least {opt[0]} {opt[1]}*.")
                    turn=(turn+1)%len(order); continue
                else:
                    called=True; caller=p
                    out(f"- **{p}** (honest seat) calls — a free check. *\"{FLAV_CALL.get(p,'Checked.')}\"*")
                    break
            else:
                if want_call:
                    called=True; caller=p
                    out(f"- **{p}** calls. *\"{FLAV_CALL.get(p,'Checked.')}\"*")
                    break
                # else raise: pick a bolder claim near belief (+bluff)
                bluff=PERS[p][1]
                made=None
                # try minimal bolder claim we can stomach
                cands=[]
                for prop in PROPS:
                    exp,sd=est_total(hands[p],prop,len(order))
                    target=int(round(exp+bluff*0.4))  # personality inflation
                    for N in range(current[0], current[0]+4):
                        cand=(N,prop)
                        if bolder(current,cand):
                            stomach = N <= exp+ (bluff)*sd + 0.6
                            if stomach or (p=="Gerald" and random.random()<0.5):
                                cands.append((abs(N-target),cand));
                if cands:
                    cands.sort(); made=cands[0][1]
                if made is None:
                    called=True; caller=p
                    out(f"- **{p}** can't raise it and won't eat it — calls. *\"{FLAV_CALL.get(p,'Checked.')}\"*")
                    break
                current=made; current_player=p; chain.append((p,made))
                gline=""
                if p=="Gerald" and made[0]>est_total(hands[p],made[1],len(order))[0]+1:
                    gline=" *(a lie told with his whole chest)*"
                out(f"- **{p}** raises → *at least {made[0]} {made[1]}*.{gline}")
                turn=(turn+1)%len(order); continue
        else:
            # opening
            if is_nestor:
                # honest open: claim something own hand guarantees
                best=None
                for prop in PROPS:
                    oc=cnt(hands[p],prop)
                    if oc>=1:
                        if best is None or DECKCT[prop]<DECKCT[best[1]]: best=(max(1,oc),prop)
                current=best or (1,"red"); current_player=p; chain.append((p,current))
                out(f"**{p}** opens (honest seat): *at least {current[0]} {current[1]}.*")
            else:
                prop=random.choice(list(PROPS)); exp,sd=est_total(hands[p],prop,len(order))
                N=max(1,int(round(exp+ (PERS[p][1]-0.4)*0.5)))
                current=(N,prop); current_player=p; chain.append((p,current))
                out(f"**{p}** opens: *at least {current[0]} {current[1]}.*")
            turn=(turn+1)%len(order); continue

    # resolve the call
    N,prop=current; actual=cnt(allcards,prop)
    truth = actual>=N
    reveal=", ".join(f"{pp}:[{' '.join(cardstr(c) for c in hands[pp])}]" for pp in order)
    out(f"  - **Check.** Claim was *≥{N} {prop}*. Actual on the table: **{actual}**. → claim is **{'TRUE' if truth else 'FALSE'}**.")
    # credit clean bluffs: earlier false claims that got raised over (not the called one)
    for (pp,(cn2,cp2)) in chain[:-1]:
        if cnt(allcards,cp2)<cn2 and pp!="__": clean_bluffs[pp]+=1
    if truth:
        # caller wrong: caller pays claimant
        seals[caller]-=1; seals[current_player]+=1
        out(f"  - {caller} called an honest claim and pays 1 seal to {current_player}. "
            f"*(Nestor: \"The record shows {current_player} was telling the truth.\")*" if caller==nestor else
            f"  - {caller} misjudged it — pays 1 seal to {current_player}.")
    else:
        seals[current_player]-=1; seals[caller]+=1   # liar pays the caller (±1, no pile bonus — keeps it from snowballing)
        successful_calls[caller]+=1
        ledger.append(f"H{hand_no}: {prop} was exactly {actual} (caught {current_player}).")
        tag=" **[AUDITOR]**" if caller=="Loki" else ""
        out(f"  - Caught. **{current_player}** pays 1 seal to **{caller}**, who seals the true count into the Ledger.{tag}")
        if current_player=="Gerald":
            out(f"    *Gerald, unbothered: \"A good lie is its own reward. This was a good lie.\"*")
    # note clean bluffs that rode this hand (false claims raised over, never called)
    rode=[f"{pp} (≥{cn2} {cp2})" for (pp,(cn2,cp2)) in chain[:-1] if cnt(allcards,cp2)<cn2]
    if rode:
        out(f"  - Rode uncalled though false — clean bluffs: {', '.join(rode)}.")
    # standings every few hands
    tot=" · ".join(f"{p} {seals[p]}" for p in PLAYERS)
    out(f"  - seals → {tot}\n")
    nestor_idx+=1

# ---- endgame ----
winner=max(PLAYERS,key=lambda p:seals[p])
trick=max(PLAYERS,key=lambda p:clean_bluffs[p])
aud=max(PLAYERS,key=lambda p:successful_calls[p])
out("---\n## The tally")
out(f"- **The Win** (most seals): **{winner}** — {seals[winner]} seals.")
out(f"- **The Trickster's Cup** (most lies sealed uncaught): **{trick}** — {clean_bluffs[trick]} clean bluffs.")
out(f"- **The Auditor's Cup** (most successful calls): **{aud}** — {successful_calls[aud]} clean catches.")
out(f"\n*Final seals:* " + ", ".join(f"{p} {seals[p]}" for p in PLAYERS))
out(f"*Hands played: {hand_no}. Lies caught (ledger entries): {len(ledger)}.*")
# closing voices
out("")
if aud=="Loki":
    out("> Loki, pocketing the Auditor's Cup and ignoring the Win entirely: \"Keep the money. I got what I came for.\"")
if trick=="Gerald":
    out("> Gerald, holding the Trickster's Cup aloft: \"Every lie I told, I told to your face. That's craftsmanship.\"")
out("> Nestor, closing the book: \"Play it again tomorrow. A thing isn't settled until it's been checked — and we do so love to check.\"")

open("/root/THE_LEDGER_playthrough.md","w").write("\n".join(LOG))
print("\n".join(LOG[-16:]))
print(f"\n[hands={hand_no} winner={winner} trickster={trick}({clean_bluffs[trick]}) auditor={aud}({successful_calls[aud]})]")
