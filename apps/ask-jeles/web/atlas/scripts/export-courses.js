/* ============================================================================
 *  export-courses.js — flatten the browser course data into a machine-readable
 *  index that non-browser tooling (e.g. Ask Jeles' atlas_progress bridge) can
 *  read without parsing JavaScript.
 *
 *  Runs the same js/data/*.js files the page loads, inside a tiny vm context
 *  that stands in for `window`, then dumps id/title/field/topics/requires to
 *  data/courses.json.
 *
 *      node scripts/export-courses.js
 *
 *  The result is a derivative of the CC BY-SA 4.0 course data — see
 *  LICENSE-DATA.md.
 * ==========================================================================*/

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dataDir = path.join(__dirname, "..", "js", "data");
const outDir = path.join(__dirname, "..", "data");

// _config.js defines window.KNOWLEDGE_MAP, R() and registerCourses(); the field
// files then call registerCourses([...]). We only need `window` to pre-exist.
const ctx = { window: {} };
vm.createContext(ctx);

const fieldFiles = fs
  .readdirSync(dataDir)
  .filter((f) => f.endsWith(".js") && f !== "_config.js")
  .sort();

for (const f of ["_config.js", ...fieldFiles]) {
  const src = fs.readFileSync(path.join(dataDir, f), "utf8");
  vm.runInContext(src, ctx, { filename: f });
}

const km = ctx.window.KNOWLEDGE_MAP;
if (!km || !Array.isArray(km.COURSES)) {
  console.error("No KNOWLEDGE_MAP.COURSES produced — did the data files change shape?");
  process.exit(1);
}

const courses = km.COURSES.map((c) => ({
  id: c.id,
  title: c.title,
  field: c.field,
  topics: Array.isArray(c.topics) ? c.topics : [],
  requires: Array.isArray(c.requires) ? c.requires : [],
}));

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(
  path.join(outDir, "courses.json"),
  JSON.stringify({ generated_from: "js/data/*.js", fields: km.FIELDS, courses }, null, 2) + "\n"
);

console.log(`Wrote ${courses.length} courses across ${Object.keys(km.FIELDS).length} fields to data/courses.json`);
