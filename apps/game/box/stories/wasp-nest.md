<!-- exported from story-timeline: timeline 64140262-9d7f-4d5e-848c-68f91b00815e -->
# The Wasp Nest

id: the-wasp-nest
setting: The same valley, a week on: up in the cellar ceiling, where the springs go. Every name here is a character, never a player.
stats: Grit, Wit, Heart, Weird
base stat: 1
offers: guest

## Characters

- pell: Pell | miller's apprentice | seated | Grit 2, Heart 1
- juno: Juno | tinker | seated | Wit 2, Weird 1
- brann: Brann | goat-herd | seated | Heart 2
- cogwen: Cogwen | the cellar's clockwork keeper
- old-vell: Old Vell | keeper of the lantern fair
- prince-aldric: Prince Aldric | freed, perhaps, last time

## Places

- the-cellar-ceiling: The cellar ceiling
- cogwen-s-workshop: Cogwen's workshop

## Scene up-into-the-ceiling: Up into the ceiling @ the-cellar-ceiling

The springs Cogwen kept go up, one by one, into the dark.
Something hums up there, and something glints.

### Prince Aldric comes to watch.

id: prince
kind: action
by: brann
suggests: Heart
when: sealed clockwork-cellar::room::free is sealed

- strong: He holds the ladder, and owes Brann's goats a second favour.
- weak: He holds the ladder, badly.
- miss: He talks the whole time.

### Juno climbs after the springs.

id: climb
kind: action
by: juno
suggests: Wit

- strong: She finds the nest, and every spring is woven into it like straw.
- weak: She finds the nest, and the nest finds her: the wasps wake.
- miss: The beam she's on is a spring too. Down she comes.

### The wasps come out.

id: wasps
kind: action
by: pell
suggests: Grit
when: up-into-the-ceiling::climb is weak, miss

- strong: Pell swings a smoking lantern and they scatter.
- weak: Pell gets them off Juno, and gets stung for it.
- miss: Everyone runs, and the wasps keep the nest.

### Is Old Vell's lamp in the nest?

id: lamp
kind: decision
proposed by: old-vell
fact: Old Vell's lost lamp is in the nest, and it's still lit.

## Scene cogwen-s-workshop: Cogwen's workshop @ cogwen-s-workshop

Behind the backwards gear is a room no one has been in.
In the middle of it, something tall, half built, made of springs.

### Brann asks Cogwen what she's building.

id: ask
kind: action
by: brann
suggests: Heart

- strong: Cogwen tells him: a friend, so the cellar isn't lonely.
- weak: Cogwen says "a friend", and won't say whose.
- miss: Cogwen covers it with a sheet and says nothing at all.

### The table's guest looks at it too.

id: guest
kind: action
by: pell
suggests: Heart
when: offered guest is sealed

- strong: The guest knows what it is, and smiles.
- weak: The guest has seen one before, a long time ago.
- miss: The guest goes very quiet.

### What is Cogwen building?

id: friend
kind: decision
proposed by: cogwen
fact: Cogwen is building a clockwork friend, from one spring of everything she ever let go.
