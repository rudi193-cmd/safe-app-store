#!/usr/bin/env node
/* ============================================================================
 *  DATA VALIDATOR  —  node scripts/validate.js
 * ----------------------------------------------------------------------------
 *  Checks for:
 *    • missing / malformed required fields on a course
 *    • duplicate course ids
 *    • prerequisites that point at a non-existent course
 *    • dependency cycles
 *    • a course assigned to a field that isn't defined
 *    • fields missing label / abbr / family / hue, or an unknown family
 *    • resources missing a title
 * ==========================================================================*/

const fs = require("fs");
const path = require("path");

const dataDir = path.join(__dirname, "..", "js", "data");
const errors = [];
const warnings = [];
const err = m => errors.push(m);
const warn = m => warnings.push(m);

// --- Load the data files (config first), sharing globals like the browser --
global.window = {};
let fileList;
try {
  fileList = fs.readdirSync(dataDir).filter(f => f.endsWith(".js"));
} catch (e) {
  console.error(`Could not read ${dataDir}: ${e.message}`);
  process.exit(1);
}
// _config.js must run first (it defines FIELDS, R() and registerCourses()).
fileList.sort((a, b) =>
  a === "_config.js" ? -1 : b === "_config.js" ? 1 : a.localeCompare(b));

for (const f of fileList) {
  const code = fs.readFileSync(path.join(dataDir, f), "utf8");
  try {
    // Indirect eval → runs in global scope, so `var`/`function` declarations in
    // one file are visible to the next (matches how <script> tags behave).
    (0, eval)(code);
  } catch (e) {
    console.error(`\n✗ Syntax error while loading js/data/${f}:\n  ${e.message}\n`);
    process.exit(1);
  }
}

const KM = global.window.KNOWLEDGE_MAP;
if (!KM || !KM.FIELDS || !KM.COURSES) {
  console.error("✗ js/data/_config.js did not set window.KNOWLEDGE_MAP correctly.");
  process.exit(1);
}
const { FIELDS, FAMILIES, COURSES } = KM;

// --- Fields ---------------------------------------------------------------
const familyKeys = new Set((FAMILIES || []).map(f => f.key));
for (const [key, f] of Object.entries(FIELDS)) {
  if (!f.label) err(`field "${key}" is missing a label`);
  if (!f.abbr) err(`field "${key}" is missing an abbr (badge text)`);
  if (typeof f.hue !== "number" || f.hue < 0 || f.hue > 360)
    err(`field "${key}" has an invalid hue (${f.hue}); use 0–360`);
  if (FAMILIES) {
    if (!f.family) err(`field "${key}" is missing a family`);
    else if (!familyKeys.has(f.family))
      err(`field "${key}" has unknown family "${f.family}"`);
  }
}

// --- Courses --------------------------------------------------------------
const ids = new Set();
const byId = new Map();
const REQUIRED = ["id", "title", "field", "desc", "requires", "topics", "free", "paid"];

for (const c of COURSES) {
  if (!c || typeof c !== "object") { err(`a course entry is not an object`); continue; }
  const label = c.id || c.title || "(unnamed course)";

  for (const k of REQUIRED)
    if (!(k in c)) err(`"${label}" is missing required key "${k}"`);

  if (typeof c.id !== "string" || !/^[a-z0-9-]+$/.test(c.id || ""))
    err(`"${label}" has an invalid id (use lowercase-kebab-case)`);
  if (ids.has(c.id)) err(`duplicate id "${c.id}"`);
  ids.add(c.id);
  byId.set(c.id, c);

  if (c.field && !FIELDS[c.field]) err(`"${label}" uses undefined field "${c.field}"`);
  if (!Array.isArray(c.requires)) err(`"${label}".requires must be an array`);
  if (!Array.isArray(c.topics)) err(`"${label}".topics must be an array`);
  if (typeof c.desc === "string" && c.desc.length < 15)
    warn(`"${label}" has a very short description`);

  for (const kind of ["free", "paid"]) {
    if (!Array.isArray(c[kind])) { err(`"${label}".${kind} must be an array`); continue; }
    for (const r of c[kind]) {
      if (!r || !r.t) err(`"${label}" has a ${kind} resource with no title`);
      if (r && r.url && !/^https?:\/\//.test(r.url))
        warn(`"${label}" resource "${r && r.t}" has a URL that isn't http(s)`);
    }
  }
}

// --- Prerequisites: dangling references -----------------------------------
for (const c of COURSES) {
  if (!Array.isArray(c.requires)) continue;
  for (const r of c.requires)
    if (!ids.has(r)) err(`"${c.id}" requires unknown course "${r}"`);
}

// --- Prerequisites: cycles (DFS) ------------------------------------------
const state = {}; // 0/undef = unvisited, 1 = on stack, 2 = done
const cycles = [];
function dfs(id, stack) {
  state[id] = 1; stack.push(id);
  for (const r of (byId.get(id)?.requires || [])) {
    if (!ids.has(r)) continue;
    if (state[r] === 1) cycles.push(stack.slice(stack.indexOf(r)).concat(r).join(" → "));
    else if (!state[r]) dfs(r, stack);
  }
  stack.pop(); state[id] = 2;
}
for (const c of COURSES) if (!state[c.id]) dfs(c.id, []);
for (const cy of cycles) err(`dependency cycle: ${cy}`);

// --- Report ---------------------------------------------------------------
const perField = {};
for (const c of COURSES) perField[c.field] = (perField[c.field] || 0) + 1;

console.log(`\nAtlas of Knowledge — data validation`);
console.log(`  ${COURSES.length} courses across ${Object.keys(FIELDS).length} fields\n`);

if (warnings.length) {
  console.log(`⚠  ${warnings.length} warning(s):`);
  warnings.forEach(w => console.log(`   - ${w}`));
  console.log("");
}

if (errors.length) {
  console.log(`✗ ${errors.length} error(s):`);
  errors.forEach(e => console.log(`   - ${e}`));
  console.log("\nValidation FAILED. Please fix the errors above.\n");
  process.exit(1);
}

console.log("✓ All checks passed. The catalog is well-formed.\n");
process.exit(0);
