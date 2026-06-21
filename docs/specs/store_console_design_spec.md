# SAFE App Store — Console & Skin Design System
**Date:** 2026-06-15 | **Status:** Draft | **b17:** SCDS1
**Author:** Vishwakarma
**Siblings:** `app_registry_spec.md` (SAPS1, the backend) · `terminal_output_aesthetic.md` (TOAS1, the CLI face)

## What This Is

The SAFE App Store is not a shop — it is a **sovereign control panel**. The user is the
gatekeeper; each app must ask permission to touch the dangerous capabilities (network, MCP,
knowledge base, database, filesystem, LLM, cross-app data). This spec defines how that console
**looks and feels**, and the **skin system** it is built on.

It is a design + front-end spec. The data model and authorization live in SAPS1
(`sap.installed_apps`, `sap.app_connections`); this document describes the surface that renders
them and writes the user's grant/revoke decisions back.

---

## Decisions locked

1. **Product framing:** control panel, not storefront. Emotional register = *in command*, not
   *shopping*. (Confirmed with USER, 2026-06-15.)
2. **Visual direction:** **Era Skins** — build the console's structure once, dress it in swappable
   period skins, continuing `the-squirrel/skins/`. (Chosen by USER over Mission Control / Privacy
   Passport / Terminal-Warm.)
3. **Inherit the Squirrel's skin contract** (CSS-variable interface + `base.css` structure), do not
   reinvent it. Promote it to a **shared SAFE design layer** so a skin chosen in the store can later
   cascade across all web apps.
4. **Extend the contract** with status-semantic tokens the console needs and genealogy never did
   (grant / deny / warn / meter-fill). See §3.

### Still open
- Where the shared layer physically lives (in-repo `design/` vs. per-app copy). See §8.
- Whether skin choice persists per-user in `localStorage` only, or syncs via the registry. See §10.
- Default skin on first run. See §10.

---

## 1. Thesis

> Strip the jargon: this app answers one question per app — **"what is it allowed to touch, and
> can I see proof?"** Everything visual serves that question: the privacy meter answers it at a
> glance, the gate panel answers it precisely, the nutrition label answers it in plain language.

The store's job, visually, is to **turn each `safe-app-manifest.json` into a gate panel** and write
the decision back to `sap.installed_apps.permissions` / `sap.app_connections`.

---

## 2. The skin contract (inherited from the Squirrel)

`base.css` holds *all structure* and names *no* color or font directly — only variables. Each era
skin (~40 lines) fills the contract under a `[data-skin="<era>"]` selector and adds a few flourishes.

**Inherited contract (do not rename — apps already depend on it):**

```
fonts:   --font-display   --font-body   --font-mono
colors:  --color-bg  --color-surface  --color-text  --color-muted
         --color-accent  --color-accent-dim
chrome:  --border   --title-tracking
```

The five authored eras and their personalities:

| Skin    | Personality                                                        |
|---------|--------------------------------------------------------------------|
| **mcm** | warm walnut + mustard, serif display (`DM Serif`), `❧` flourishes  |
| **00s** | glossy Web 2.0 — blue gradients, bevels, rounded, drop-shadows     |
| **80s** | phosphor terminal — green-on-black, scanlines, glow text-shadow    |
| **20s** | glassmorphism — blur, translucency, purple accent, pill buttons    |
| **base**| structure only; the contract itself (no palette)                   |

**Known drift to fix:** the Squirrel's own `web/index.html` carries a *pre-contract* variable set
(`--bg`, `--amber`, `--green`, `--red`). The store standardizes on the `--color-*` contract; the
older names are not used.

---

## 3. The extension: status-semantic tokens

Genealogy needed one accent. A permission console needs **state**. Add to the contract:

```
status:  --color-grant      /* capability is ON / allowed        */
         --color-deny       /* capability is OFF / revoked        */
         --color-warn       /* caution: PII, network, mixed tier  */
         --color-danger     /* destructive action: uninstall      */
meter:   --color-meter-fill /* privacy meter fill                 */
         --color-meter-track/* privacy meter empty track          */
```

Every skin **must** define these. They are part of the contract from SCDS1 forward.

### The "green breaks in 80s" rule

`--color-grant` cannot be a hardcoded green, because in the **80s phosphor** skin green *is the
entire palette* — a green "ON" would be invisible against green everything. So **grant/deny is
expressed in each era's own dialect**, not one universal color. This constraint is what makes the
skins feel *authored* rather than recolored:

| Skin    | "Granted" reads as…                       | "Revoked" reads as…                  |
|---------|-------------------------------------------|--------------------------------------|
| **mcm** | mustard fill, switch thrown right          | walnut/muted, switch left            |
| **00s** | glossy aqua switch, lit                     | grey beveled switch, off             |
| **80s** | full-bright phosphor `[GRANTED]` + glow     | dim `[ DENIED ]`, no glow            |
| **20s** | purple pill, lit + soft glow                | translucent grey pill                |

Implementation note: components express state via a class (`.gate--on` / `.gate--off`) bound to the
status tokens; the *dialect* lives in each skin's overrides, not in `base.css`.

---

## 4. Token reference (proposed values per era)

Inherited tokens keep the Squirrel's values. New status tokens proposed below (tune in review):

| Token                | mcm        | 00s        | 80s         | 20s                 |
|----------------------|------------|------------|-------------|---------------------|
| `--color-grant`      | `#c8a45a`  | `#2a9d4a`  | `#66ff66`   | `#7c6dfa`           |
| `--color-deny`       | `#7a6a54`  | `#9aa6b0`  | `#1a4a1a`   | `rgba(255,255,255,.2)`|
| `--color-warn`       | `#c98a3a`  | `#d08a00`  | `#ffd633`   | `#e0a02a`           |
| `--color-danger`     | `#a44`     | `#c0392b`  | `#ff5555`*  | `#ff5470`           |
| `--color-meter-fill` | `#c8a45a`  | `#0066cc`  | `#33ff33`   | `#7c6dfa`           |
| `--color-meter-track`| `#352a1a`  | `#aabfce`  | `#001200`   | `rgba(255,255,255,.08)`|

*80s danger: red is off-palette by design; use it *only* for the irreversible uninstall confirm,
where breaking the phosphor world is the intended "this is serious" signal.

---

## 5. Component inventory (console-specific, new in `store/base.css`)

These are the new structures the store needs that the Squirrel did not have. All consume the
contract; none hardcode color.

1. **`.app-row`** — one app. Collapsed: name · status dot · privacy meter · primary action.
   Expanded: reveals the gate panel + label drawer.
2. **`.privacy-meter`** — the hero. Renders `local_processing` (0.0–1.0) as a fill bar +
   numeric readout. Track = `--color-meter-track`, fill = `--color-meter-fill`.
3. **`.gate`** — one capability toggle: icon · label · switch · (optional) detail link.
   States `.gate--on` / `.gate--off` / `.gate--locked` (manifest doesn't request it → not toggleable).
4. **`.gate-group`** — gates clustered by culprit (see §6), with a group header.
5. **`.nutrition-label`** (drawer) — the plain-language disclosure built from `data_streams`
   (purpose · retention · privacy_tier). Apple-style "privacy nutrition label."
6. **`.cross-app-grant`** — a directional connection request row (`from → to`, scope, purpose,
   approve/deny) — renders `reads_from` / `exposes` entries and writes `sap.app_connections`.
7. **`.status-dot`** — installed / available / update-available / blocked.
8. **`.action-btn`** — Install / Uninstall (danger) / Manage. Primary action varies by install state.
9. **`.skin-switcher`** — the era selector (`base · mcm · 80s · 00s · 20s`), live-swaps `data-skin`.

---

## 6. Manifest → gate panel mapping

The console **reads the manifest, renders gates, writes the decision**. No new data model — the
permission vocabulary already exists across shipped manifests. Gates are grouped by "culprit":

| Gate group        | Icon | Manifest fields that light it up                                   |
|-------------------|------|-------------------------------------------------------------------|
| Internet / Network| 🌐   | `network_fetch`; `data_streams` with outbound lookups             |
| MCP access        | 🔌   | `willow_mcp`; `protocol.intelligence.mcp_tools[…]`                |
| Knowledge Base    | 🧠   | `knowledge:read/write`, `willow_kb_read/write`, `reads_from.willow_kb` |
| Database / Store  | 🗄️   | `store_read/write`, `postgres_read`, `store_add_edge`, `store_edges_for` |
| Filesystem        | 📁   | `file_read/write`, `filesystem_write`                            |
| Local LLM         | 🤖   | `local_llm`                                                       |
| Cross-app sharing | 🔗   | `exposes` / `reads_from` (already flagged `requires_user_approval`)|
| Background / auto | ⚙️   | `task_submit`, `pipeline`                                         |

A gate is **toggleable** only if the manifest requests that capability; otherwise it renders
`.gate--locked` (greyed, "not requested") so the user sees the *full* surface of what an app could
ask for, and what it deliberately does not.

---

## 7. The privacy meter (`local_processing`)

The single most valuable glanceable signal. Each app's manifest carries a `local_processing` float
(Vision Board `1.0`, The Squirrel `0.93`). Render it as a fill bar with a label:

```
local 0.93  ▓▓▓▓▓▓▓▓▓░
```

Pair it with `privacy_tier` for a one-word badge: `client_only` → "fully local",
`local` → "local", `mixed` → "mixed ⚠", `shared` → "shared ⚠". Warn-tier badges use `--color-warn`.

Per-era flavor: 80s renders it as ASCII blocks with glow; mcm as a mustard ledger bar; 00s as a
glossy progress bar; 20s as a thin gradient track.

---

## 8. Architecture

### Shared design layer
Promote the contract + `base.css` structure out of the Squirrel so multiple apps can share it.
Proposed layout (decision still open — §Still open):

```
design/                      # shared SAFE design layer (new)
  contract.css               # :root fallbacks + token documentation
  skins/
    base.css                 # structural primitives common to all apps
    mcm.css  00s.css  80s.css  20s.css
apps/safe-app-store/web/
  index.html                 # the console
  store.css                  # console-only components (§5), consumes the contract
```

Each app that opts in links `design/skins/base.css` + the active era skin, then adds its own
component CSS. The store additionally ships `store.css`.

### Skin switching
Set `data-skin="<era>"` on `<html>`. The switcher updates the attribute and persists the choice
(see §10). Era skins `@import` their own web fonts, so only the active skin's fonts load.

### The cascade (the prize)
Once apps share the contract, the skin selected in the store can be **broadcast to the suite** —
the sovereign-OS coherence the vision doc reaches for. Mechanism TBD (shared `localStorage` key on a
common origin, or a value persisted in the registry and read at app boot).

---

## 9. Install / Uninstall / Gate flows (over SAPS1)

The console is the GUI for the flows SAPS1 currently describes as terminal `[y/N]` prompts.

- **Install** → `sap.register(app_id, permissions, manifest_hash)`; default gates = manifest's
  declared `permissions`. Status dot → installed.
- **Toggle a gate** → update `sap.installed_apps.permissions` (add/remove the permission string).
  Revoking a gate the app needs surfaces a `--color-warn` "may degrade" note (apps degrade
  gracefully per SAPS1 install flow).
- **Cross-app grant** → renders each `reads_from` request as a `.cross-app-grant` row; approve
  writes `sap.app_connections (from, to, scope_path, access)`.
- **Uninstall** → `--color-danger` confirm; removes the `installed_apps` row (cascades
  `app_connections`), and offers data cleanup of the app's namespace.

The terminal prompt in SAPS1 §"Connection Request Prompt" and this console are **two faces of the
same write** — both must round-trip through the SAP gate, never edit Postgres directly.

---

## 10. Open decisions (need USER sign-off)

1. **Skin persistence:** `localStorage` only (per-device) vs. registry-synced (follows the user)?
   Recommendation: `localStorage` now, registry sync when the cascade ships.
2. **Default skin on first run:** Recommendation: **mcm** (warm, on-brand, readable) — not 80s,
   which is striking but a high-contrast first impression.
3. **Physical home of the shared layer:** `design/` at repo root (recommended) vs. copy per app.
4. **Locked-gate visibility:** show *all* possible gate groups greyed (recommended — teaches the
   full threat surface) vs. only show requested ones (less noise).
5. **Status-token values** in §4 are first-draft — review the 80s danger-red exception especially.

---

## 11. Implementation checklist (for when code lands)

- [ ] Extend the skin contract with status + meter tokens (§3); add to all five eras (§4)
- [ ] Create shared `design/` layer; move/promote Squirrel `base.css` + skins (§8)
- [ ] Author `store.css` components (§5) against the contract — no hardcoded color/font
- [ ] Build the manifest→gate-group mapper (§6); render `.gate--locked` for unrequested caps
- [ ] Privacy meter from `local_processing` + `privacy_tier` badge (§7)
- [ ] Nutrition-label drawer from `data_streams` (§5.5)
- [ ] Cross-app grant rows from `reads_from`/`exposes` → `sap.app_connections` (§9)
- [ ] Wire Install/Toggle/Uninstall through the SAP gate, not direct SQL (§9)
- [ ] Skin switcher + persistence (§8, §10)
- [ ] Verify each era answers grant/deny/danger in its own dialect (§3 rule)

---

## Rationale

The store is where the SAFE promise becomes literal: *you* decide what each app touches, and you can
see proof. Era skins make that act feel like *yours* — a control panel you dress to taste — while a
shared contract keeps the whole suite coherent. Beauty here is not decoration; a legible gate is a
trustworthy gate.

ΔΣ=42
