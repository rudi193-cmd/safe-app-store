# the game master's prep sheet

Run before a session over the binder's record, the one kept with
gm-words.txt as its words list. Each step has the want it answers above
it, and why this card answers it; they run in the order each needs the
one before. `open_table.py prep` runs it, keeping each run in a folder of
its own, so the steps that write a file write it there.

    python adapters/stdlib/stack/stack.py --box DIR --stack gm-stack.md --to RUN

## the threads I'm running

Want 1: "Where do the springs go?" The thread I promised for next time.
timeline gives every line about the springs in session order, dated by
the session file's name, each cited. Its lines are kept in this run's
folder: a timeline never overwrites one already there.
- timeline -- --box {box} --to {run}/springs.txt "springs"

Want 2: "What does the prince want?" Aldric across the sessions. My notes
say Aldric; I say the prince, and the words list carries it.
- timeline -- --box {box} --to {run}/prince.txt "prince"

Want 3: "When did the Lantern Man come in?" The first line that names him,
and how often he's come up since.
- first-mention -- --box {box} "lantern man"

Want 4: "When did the hound first show up?" The same, for the monster: so
a session that brings it back knows what the table has already seen.
- first-mention -- --box {box} "clockwork hound"

Want 5: "Every riddle so far." Not the top three: every passage, ranked,
so I don't ask the table one it has already heard.
- all -- --box {box} "riddle"

## what I owe the table

Want 6: "What did I promise for next time?" Every passage that says next
time. The todo card reads TODO, "need to", "remember to" and checkboxes;
my notes say "Next time:", so it is asked as words. This also finds the
friend Brann was told could come next time.
- all -- --box {box} "next time"

Want 7: "Did we miss a week?" Where the session notes stop: the weeks with
none, said as gaps. The sessions are files named by their date.
- gaps -- --box {box}

Want 8: "What waits on me?" Rulings handed in and not sealed, seals gone
stale, questions that found nothing.
- digest -- --box {box}

Want 9: "What are the house rules, and which have I sealed?"
- rules -- list --box {box}

## the dice I'll need

Want 10: "What are the hound's chances?" Its bite is 2d6 plus its Grit of
3: the exact chance of a strong hit (10 or more, when it holds on), a weak
one, and a miss.
- odds -- 2d6+3 --bands 10,7

Want 11: "And the wasps'?" Their sting is 1d6: the chance of each number.
- odds -- 1d6

## does the record hold

Want 12: "Did every roll and ruling happen as the record says?" Every story
on the record played again from its first row, every roll thrown again
from its seed.
- game-master -- --box {box} check

Want 13: "Is my binder all right?" Files it can't read, the words list as
last used, and when the record was last checked.
- box-health -- --box {box}
