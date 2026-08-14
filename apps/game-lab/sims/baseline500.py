import baseline_core as bc, john_baseline as jb, random, os
from collections import Counter
random.seed(int.from_bytes(os.urandom(8),'big'))
N=500
def blk(tag,name,res,seats,unit,extra=''):
    w=Counter(r[0] for r in res);ln=[r[1] for r in res]
    ks=[f'P{i}' for i in range(1,seats+1)]+['draw']
    return f'| {name} | {tag} | '+' · '.join(str(w.get(k,0)) for k in ks)+f' | {sum(ln)//len(ln)} {unit} | {extra} |'
rows=['| Game | Policy | seat dist (…draw) | avg | note |','|---|---|---|---|---|']
rows.append(blk('random','Chess',[(x[0],x[1]) for x in [bc.chess_once() for _ in range(N)]],2,'plies'))
rows.append(blk('random','Checkers',[bc.checkers_once() for _ in range(N)],2,'moves'))
r=[bc.backgammon_once() for _ in range(N)];rows.append(blk('random','Backgammon',[(x[0],x[1]) for x in r],2,'turns',f'gam {sum(1 for x in r if x[2])}/{N}'))
rows.append(blk('random','Uno',[bc.uno_once() for _ in range(N)],4,'plies'))
rows.append(blk('random','Ledger',[bc.ledger_once() for _ in range(N)],4,'seals'))
rows.append(blk('JOHN','Chess',[(x[0],x[1]) for x in [jb.chess_john() for _ in range(N)]],2,'plies'))
rows.append(blk('JOHN','Checkers',[jb.checkers_john() for _ in range(N)],2,'moves'))
r=[jb.backgammon_john() for _ in range(N)];rows.append(blk('JOHN','Backgammon',[(x[0],x[1]) for x in r],2,'turns',f'gam {sum(1 for x in r if x[2])}/{N}'))
rows.append(blk('JOHN','Uno',[jb.uno_john() for _ in range(N)],4,'plies'))
rows.append(blk('JOHN','Ledger',[jb.ledger_john() for _ in range(N)],4,'seals'))
open('/root/_mine500.md','w').write('\n'.join(rows));print('\n'.join(rows))
