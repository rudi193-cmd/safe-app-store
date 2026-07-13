/* ============================================================================
 *  jeles-progress.js — seed The Catalog's completion from Ask Jeles history.
 * ----------------------------------------------------------------------------
 *  Additive companion, loaded AFTER app.js. Fetches the locally-generated
 *  data/jeles-progress.json (produced by `python -m askjeles.atlas_progress`)
 *  and unions its course ids into completion via the app's KnowledgeMap hook.
 *
 *  No-op when the file is absent — hosted deploys and fresh installs carry no
 *  learning history, so the Catalog behaves exactly as upstream.
 * ==========================================================================*/

(function () {
  var PROGRESS_URL = "data/jeles-progress.json";

  function apply(data) {
    if (!data || !window.KnowledgeMap || typeof window.KnowledgeMap.applyCompleted !== "function") {
      return;
    }
    var ids = Array.isArray(data.completed_course_ids) ? data.completed_course_ids : [];
    if (!ids.length) return;

    var added = window.KnowledgeMap.applyCompleted(ids);
    if (added > 0 && typeof window.KnowledgeMap.toast === "function") {
      window.KnowledgeMap.toast(
        "Jeles filed " + added + " subject" + (added === 1 ? "" : "s") + " from your learning history ✦"
      );
    }
  }

  function boot() {
    fetch(PROGRESS_URL, { cache: "no-store" })
      .then(function (r) { return r && r.ok ? r.json() : null; })
      .then(apply)
      .catch(function () { /* nothing on hand — the Catalog stands as-is */ });
  }

  if (window.KnowledgeMap) boot();
  else window.addEventListener("load", boot);
})();
