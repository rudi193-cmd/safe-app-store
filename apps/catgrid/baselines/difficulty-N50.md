# catgrid difficulty, measured: 50 boards a level

Produced by `python3 -m catgrid.rating 50` (seeds 0..49 per level, 8 min in
plain Python). Nothing here is estimated: rerun it and every number comes back.

| Column | Means |
|---|---|
| plain_share | share of the answer the two plain rules reach from an empty board |
| solved_by_plain | boards the plain rules finish alone |
| ahead_share / solved_by_ahead | the same with the look-ahead rule ("a cat here leaves that line nowhere") |
| random_wins | a random legal-move player (the table's baseline policy), capped at 5000 moves |
| careful_wins | reasons first, then hints, then guesses (marking a wrong guess) |
| careful_hearts_left | the careful player's hearts at the end, on average |

| level | boards | plain_share | solved_by_plain | ahead_share | solved_by_ahead | random_wins | careful_wins | careful_hearts_left |
|---|---|---|---|---|---|---|---|---|
| 5x5, 1 cat(s) | 50 | 0.124 | 0.08 | 1.0 | 1.0 | 0.0 | 1.0 | 3 |
| 6x6, 1 cat(s) | 50 | 0.123 | 0.06 | 1.0 | 1.0 | 0.0 | 1.0 | 3 |
| 8x8, 1 cat(s) | 50 | 0.128 | 0.02 | 1.0 | 1.0 | 0.0 | 1.0 | 3 |
| 9x9, 2 cat(s) | 50 | 0.0 | 0.0 | 0.502 | 0.5 | 0.0 | 0.92 | 2.58 |
| 10x10, 2 cat(s) | 50 | 0.0 | 0.0 | 0.4 | 0.36 | 0.0 | 0.76 | 2.08 |
| 13x13, 3 cat(s) | 50 | 0.0 | 0.0 | 0.235 | 0.16 | 0.0 | 0.6 | 1.44 |
