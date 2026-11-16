import chess, random, os
random.seed(int.from_bytes(os.urandom(8),"big"))
VAL={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9,chess.KING:0}
def material(b):
    return sum(len(b.pieces(p,chess.WHITE))*v-len(b.pieces(p,chess.BLACK))*v for p,v in VAL.items())
def pick(b):
    best,bs=None,-1e9
    for mv in b.legal_moves:
        sc=0.0
        if mv.promotion: sc+=8
        atkp=b.piece_at(mv.from_square); atk=VAL[atkp.piece_type] if atkp else 0
        cap=b.is_capture(mv)
        cv=0
        if cap:
            cp=b.piece_at(mv.to_square); cv=VAL[cp.piece_type] if cp else 1
        b.push(mv)
        mate=b.is_checkmate(); chk=b.is_check()
        recap=b.is_attacked_by(b.turn, mv.to_square)   # opponent to move; can they recapture?
        b.pop()
        if cap: sc += cv - (atk if recap else 0)        # avoid equal/losing trades
        if mate: sc+=1000
        elif chk: sc+=0.3
        if not cap: sc += 0.06*(mv.to_square in (chess.D4,chess.E4,chess.D5,chess.E5))
        sc += random.random()*0.4
        if sc>bs: bs,best=sc,mv
    return best
def play():
    b=chess.Board(); plies=0
    while not b.is_game_over(claim_draw=True) and plies<200:
        b.push(pick(b)); plies+=1
    if b.is_game_over(claim_draw=True):
        res=b.result(claim_draw=True)
        term=("checkmate" if b.is_checkmate() else "stalemate" if b.is_stalemate()
              else "insufficient material" if b.is_insufficient_material()
              else "threefold repetition" if b.can_claim_threefold_repetition()
              else "fifty-move rule" if b.can_claim_fifty_moves() else "draw")
    else:
        m=material(b); res="1-0" if m>=2 else "0-1" if m<=-2 else "1/2-1/2"; term=f"adjudicated ({m:+d})"
    return res,term,plies
rows=[];W=B=D=0
for i in range(1,14):
    r,t,p=play(); rows.append((i,r,t,p))
    W+=r=="1-0";B+=r=="0-1";D+=r=="1/2-1/2"
out=["## Chess — 13 rounds  ·  Willow (White) vs Loki (Black)","","| # | Result | Termination | Plies |","|---|---|---|---|"]
for i,r,t,p in rows: out.append(f"| {i} | {r} | {t} | {p} |")
out+=["",f"**Tally — White (Willow) {W} · Black (Loki) {B} · Draws {D}.** "
      f"Avg {sum(p for *_,p in rows)//13} plies (~{sum(p for *_,p in rows)//26} moves/side)."]
open("/root/_chess_res.md","w").write("\n".join(out)); print("\n".join(out))
