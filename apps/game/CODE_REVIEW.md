# Code Review — Jane GM (Safe-App-Game)

**Date:** 2026-04-08
**Reviewer:** Claude (automated)
**Scope:** Full codebase review of all source files

---

## Summary

The app **cannot run as-is**. Two undefined function calls will crash it on both the setup screen and the game screen, and the state persistence cycle is fundamentally broken. The SAFE integration module is entirely dead code with multiple undefined references. Below are all findings grouped by severity.

---

## Critical — App Will Crash

### 1. `streamlit_app.py:197` — `render_game_setup()` is not defined

```python
render_game_setup()  # NameError
```

The function defined on line 125 is `render_character_creation()`, but line 197 calls `render_game_setup()`. This crashes on every page load before the game starts.

**Fix:** Rename the call to `render_character_creation()`.

---

### 2. `streamlit_app.py:216` — `get_color_code()` is not defined

```python
color = get_color_code(value)  # NameError
```

The function defined on line 42 is `get_stat_color()`, but line 216 calls `get_color_code()`. This crashes during active gameplay when rendering the stat block.

**Fix:** Rename the call to `get_stat_color()`.

---

### 3. `streamlit_app.py:40,120` — `st.experimental_rerun()` is deprecated

`st.experimental_rerun()` was removed in Streamlit 1.27+. Depending on the installed version this will raise `AttributeError`.

**Fix:** Replace both calls with `st.rerun()`.

---

### 4. `engine_v1_7.py:31` — State file integrity check uses wrong key names

```python
if set(data["stats"].keys()) != set(["Grit", "Weird", "Cute", "Cool"]):
    raise ValueError("State file integrity compromised.")
```

After character creation, `launch_game()` saves stats with **operational metric names** (`Integrity`, `Synthesis`, `Trust`, `Efficiency`). On the next load, this integrity check **always fails**, silently resetting the player's progress to defaults. The save/load cycle is broken.

**Fix:** Accept both naming schemes, or standardise on one throughout.

---

## Moderate Bugs

### 5. `streamlit_app.py:221` — Negative stats display as `+-3`

```python
f"<h3 style='color: {color}; margin-top: 0px;'>+{value}</h3>"
```

The `+` is hardcoded, so a stat value of `-3` renders as `+-3`.

**Fix:** Use a conditional prefix: `f"{'+'if value >= 0 else ''}{value}"`.

---

### 6. `streamlit_app.py:37` — `reset_game_state()` saves the old engine

After creating a new `Engine()` on line 33, line 37 calls `engine._save_state()` on the **module-level** reference (line 25), which still points to the old engine. The new engine's clean state is never persisted.

**Fix:** Call `st.session_state.engine._save_state()` instead, or save before replacing.

---

### 7. `safe_integration.py:87,96,110` — `WILLOW_URL` and `APP_ID` are never defined

`get_consent_status()`, `request_consent_url()`, and `check_inbox()` all reference these undefined module-level variables. Any call raises `NameError`.

**Fix:** Define these as module constants or load from config/environment.

---

### 8. `safe_integration.py:102` — `_drop()` function is never defined

```python
def send(to_app, subject, body, thread_id=None):
    return _drop("send", {...})  # NameError
```

**Fix:** Implement `_drop()` or replace with the intended HTTP call.

---

### 9. `engine_v1_7.py:97` — `check_proportionality()` division by zero

```python
if self.stats['Efficiency'] * 2 >= task_complexity / resource_cost:
```

If `resource_cost` is `0`, this raises `ZeroDivisionError`.

**Fix:** Guard against zero: `if resource_cost == 0: return False, "INVALID_RESOURCE"`.

---

## Design & Quality Issues

### 10. Stat mapping duplicated in 4 places

The dictionary `{"Grit": "Integrity", "Weird": "Synthesis", "Cute": "Trust", "Cool": "Efficiency"}` is defined separately in:

- `streamlit_app.py:29`
- `engine_v1_7.py:61`
- `engine_v1_7.py:81`
- `engine_v1_7.py:89`

This is a maintenance hazard. It should be a single constant exported from the engine module.

---

### 11. `engine_state.json` is tracked in git

Mutable runtime state files should not be version-controlled. This leaks session data and causes merge conflicts. Add it to `.gitignore` and ship a template (e.g. `engine_state.example.json`) instead.

---

### 12. `safe_integration.py` is never imported

The SAFE consent module is not wired into `streamlit_app.py` at all. It is entirely dead code in the current application.

---

### 13. `requirements.txt` is incomplete

`safe_integration.py` imports `requests`, which is not listed in `requirements.txt`.

---

### 14. `engine_state.json` contains vestigial `debilities` field

The engine never reads or writes the `debilities` key in the state file. It tracks debilities directly via stat values instead.

---

## Tally

| Severity | Count |
|----------|-------|
| Critical (app crashes) | 4 |
| Moderate bugs | 5 |
| Design / quality | 5 |
| **Total** | **14** |
