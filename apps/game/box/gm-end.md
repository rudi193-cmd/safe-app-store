# the game master's end of the night

Run when the session is over, over the binder's record. The night's
handwritten pages go into the binder first, then the night is compiled,
then closed. `open_table.py end` runs it, each run kept in a folder of its
own, and ends with what the table made true.

    python adapters/stdlib/stack/stack.py --box DIR --stack gm-end.md --to RUN

## tonight's pages

Want 1: "Read what I wrote by hand." Photos of tonight's pages, put in the
box's scans folder, read by tesseract into the binder's scanned folder,
where every question and every step after this can find them. OCR
guesses: the binder cites the line tesseract read, not the page.
- ocr -- mirror --from {box}/../scans --to {box}/../pile/scanned

Want 2: "What's new in my binder tonight?" Every file new, edited or gone
since the last look, put on the record as fingerprints, never words.
- changed -- --box {box}

## what tonight added

Want 3: "Where did the springs go tonight?" The thread in session order,
typed nights and scanned ones together, each line cited.
- timeline -- --box {box} --to {run}/springs.txt "springs"

Want 4: "What did I promise for next time?" Every passage that says next
time, tonight's page with the rest.
- all -- --box {box} "next time"

Want 5: "What's still waiting on me?" Offers and rulings handed in tonight
and not answered, before everyone goes home.
- digest -- --box {box}

Want 6: "Tonight, in plain sentences." What was asked, handed in and
approved today, as places and counts, never the words.
- history -- --box {box} --days 1

## close the night

Want 7: "Did every roll and ruling happen as the record says?"
- game-master -- --box {box} check

Want 8: "One seal over the whole night." Every row since the last session
seal, handed in as one proposal: sealed, it says these were my actions.
- session-seal -- --box {box}

Want 9: "A copy of tonight, checked." The record zipped and its chain
checked in the copy before it's kept.
- backup -- --box {box} --to {run}

Want 10: "Where the record ended tonight." The record's length and last
hash, so a night cut off the end later is caught. Copy it somewhere the
box can't reach.
- tip-pin -- pin --box {box} --to {run}/pin.json
