# gatefirst — the counterfactual slice
b17: SAPS1

The same app, same two actors (journal = Steady, jeles = Rookie), same
WillowGate underneath — built gate-first instead of gate-retrofitted. This is
a comparison slice, not a second product: persons + fragments, SQLite, four
commands, one export.

## The diff you should spot

**Retrofit** (`sap/core/gate.py` + `db/*.py`): any code can import the whole
PII surface; a thread-local decides at the last line before the INSERT.

```python
import db.persons
with sap.core.gate.actor("jeles"):
    db.persons.add_person(conn, full_name=...)   # exists, callable —
                                                 # authorized("write") raises inside
```

**Gate-first** (`gatefirst/`): checking in is the only way to reach storage,
and it returns a handle shaped by trust at the door.

```python
handle = Gatehouse(base_dir).check_in("jeles")
handle.add_person                                # AttributeError —
                                                 # the capability was never minted
```

The ungrantable is uncallable. `dir(handle)` is the policy document; the
ledger announcement (`authorize_tool()` still runs inside every store method)
is the second wall, not the first.

## What each approach costs

- **Retrofit:** every new db function must remember the check — forget one
  line and the door is open, silently. But it bolted onto an existing codebase
  in a day, touched nothing structural, and scripts keep their escape hatch
  (`bypass(reason)`).
- **Gate-first:** every new capability must be threaded through handle
  construction — new method on the store, on the right handle class, minted at
  the right trust tier. More ceremony per capability, and every function in the
  call chain must now carry the handle as an argument (no ambient thread-local
  to lean on). In exchange, forgetting is not a failure mode: an unthreaded
  capability simply does not exist for the untrusted actor.

Retrofit fails open on omission; gate-first fails closed on omission. That is
the whole trade.

ΔΣ=42
