/* ============================================================================
 *  KNOWLEDGE MAP — SHARED CONFIG
 * ----------------------------------------------------------------------------
 *  To add a whole new discipline: add a key here (label + an HSL hue for its
 *  accent color + border), then create js/data/<field>.js and list it in
 *  index.html. To add a subject: edit the relevant js/data/<field>.js file.
 * ==========================================================================*/

// Fields belong to families (natural sciences, engineering, social sciences,
// humanities). Their order here sets the left to right lane order in the graph, so
// related disciplines sit next to each other, and each family is given its own
// hue arc so members look visually related. Each field needs a label, a short 
// `abbr` for the node badge, an HSL `hue`, and its `family`.
var FIELDS = {
  // --- Natural & formal sciences — greens & teals ---
  mathematics:      { label: "Mathematics",           abbr: "MATH",  family: "sciences",    hue: 96  },
  physics:          { label: "Physics",               abbr: "PHYS",  family: "sciences",    hue: 120 },
  chemistry:        { label: "Chemistry",             abbr: "CHEM",  family: "sciences",    hue: 150 },
  biology:          { label: "Biology",               abbr: "BIO",   family: "sciences",    hue: 172 },
  cs:               { label: "Computer Science",      abbr: "CS",    family: "sciences",    hue: 190 },

  // --- Engineering — blues & indigo ---
  matsci:           { label: "Materials Science",     abbr: "MATSE", family: "engineering", hue: 205 },
  mecheng:          { label: "Mechanical Eng.",       abbr: "MECH",  family: "engineering", hue: 215 },
  eleceng:          { label: "Electrical Eng.",       abbr: "EE",    family: "engineering", hue: 225 },
  civileng:         { label: "Civil Eng.",            abbr: "CIVE",  family: "engineering", hue: 235 },
  chemeng:          { label: "Chemical Eng.",         abbr: "CHE",   family: "engineering", hue: 245 },
  aeroeng:          { label: "Aerospace Eng.",        abbr: "AERO",  family: "engineering", hue: 255 },
  bioeng:           { label: "Biomedical Eng.",       abbr: "BME",   family: "engineering", hue: 266 },

  // --- Social sciences — violets & purples ---
  economics:        { label: "Economics",             abbr: "ECON",  family: "social",      hue: 278 },
  psychology:       { label: "Psychology",            abbr: "PSYC",  family: "social",      hue: 289 },
  sociology:        { label: "Sociology",             abbr: "SOC",   family: "social",      hue: 300 },
  politicalscience: { label: "Political Science",     abbr: "POLS",  family: "social",      hue: 311 },
  anthropology:     { label: "Anthropology",          abbr: "ANTH",  family: "social",      hue: 322 },
  linguistics:      { label: "Linguistics",           abbr: "LING",  family: "social",      hue: 331 },

  // --- Humanities — warm rose → red → orange ---
  philosophy:       { label: "Philosophy",            abbr: "PHIL",  family: "humanities",  hue: 343 },
  history:          { label: "History",               abbr: "HIST",  family: "humanities",  hue: 351 },
  litstudies:       { label: "Literary Studies",      abbr: "LIT",   family: "humanities",  hue: 359 },
  theology:         { label: "Theology & Religion",   abbr: "THEO",  family: "humanities",  hue: 7   },
  law:              { label: "Law",                   abbr: "LAW",   family: "humanities",  hue: 15  },
  performingarts:   { label: "Performing Arts",       abbr: "PERF",  family: "humanities",  hue: 23  },
  visualarts:       { label: "Visual Arts",           abbr: "ART",   family: "humanities",  hue: 31  },
};

// Family display order & labels for the legend sections.
var FAMILIES = [
  { key: "sciences",    label: "Natural & Formal Sciences" },
  { key: "engineering", label: "Engineering" },
  { key: "social",      label: "Social Sciences" },
  { key: "humanities",  label: "Humanities" },
];

function R(t, by, url) { return { t: t, by: by, url: url || null }; }

// The global registry. Each field file calls registerCourses([...]).
window.KNOWLEDGE_MAP = { FIELDS: FIELDS, FAMILIES: FAMILIES, COURSES: [] };

function registerCourses(list) {
  var arr = window.KNOWLEDGE_MAP.COURSES;
  for (var i = 0; i < list.length; i++) arr.push(list[i]);
}
