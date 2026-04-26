/**
 * session.js — Local session management for NASA Archive
 * All data stays on the user's machine unless they explicitly contribute.
 */

const NASA_SESSION_KEY = 'nasa-session';

/** Create a fresh session for a rally */
function createSession(slug, rallyTitle) {
  return {
    type: 'nasa_memory',
    version: '1.0',
    rally: slug,
    rally_title: rallyTitle,
    session_id: `${slug}-${Date.now()}`,
    timestamp: new Date().toISOString(),
    photos_tagged: [],
    album_claim: null,
    oral_history: [],
    contributed: false,
  };
}

/** Load session from localStorage (or create new) */
function loadSession(slug, rallyTitle) {
  try {
    const raw = localStorage.getItem(`${NASA_SESSION_KEY}-${slug}`);
    if (raw) return JSON.parse(raw);
  } catch (e) { /* ignore */ }
  return createSession(slug, rallyTitle);
}

/** Save session to localStorage */
function saveSession(session) {
  try {
    localStorage.setItem(
      `${NASA_SESSION_KEY}-${session.rally}`,
      JSON.stringify(session)
    );
  } catch (e) { /* ignore */ }
}

/** Download session as JSON file */
function downloadSession(session) {
  const blob = new Blob(
    [JSON.stringify(session, null, 2)],
    { type: 'application/json' }
  );
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `nasa-memory-${session.rally}-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** Check if session has any activity worth saving */
function hasActivity(session) {
  return (
    session.photos_tagged.length > 0 ||
    session.album_claim !== null ||
    session.oral_history.length > 0
  );
}

// Export for use in other scripts
window.NASASession = {
  create: createSession,
  load: loadSession,
  save: saveSession,
  download: downloadSession,
  hasActivity,
};
