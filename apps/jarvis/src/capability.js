// Capability probing.
//
// Every capability this app wants is optional somewhere: speech recognition
// is Chrome/Safari-only, notifications need a grant, geolocation needs a
// grant and a fix. The shape used here is an ordered ladder per capability
// plus a `notes[]` recording why each rung was skipped, so a degraded session
// reports its degradation as a fact instead of quietly behaving differently.
//
// The failure this is written against: a probe that answers "yes" because the
// symbol exists, when the mechanism behind it has never once run. `speak` and
// `listen` are therefore probed by construction — we build the object the API
// would actually use and catch the throw — not by `'x' in window`.

/** @typedef {{ name: string, available: boolean, rung: string|null, notes: string[] }} Capability */

function ladder(name, rungs) {
  const notes = [];
  for (const { rung, test } of rungs) {
    let ok = false;
    let why = null;
    try {
      ok = test();
    } catch (err) {
      why = err && err.message ? err.message : String(err);
    }
    if (ok) return { name, available: true, rung, notes };
    notes.push(`${rung}: ${why || 'not available in this browser'}`);
  }
  return { name, available: false, rung: null, notes };
}

export function probeSpeechInput() {
  return ladder('speech-input', [
    {
      rung: 'SpeechRecognition',
      test: () => {
        if (typeof window.SpeechRecognition !== 'function') return false;
        new window.SpeechRecognition();
        return true;
      },
    },
    {
      rung: 'webkitSpeechRecognition',
      test: () => {
        if (typeof window.webkitSpeechRecognition !== 'function') return false;
        new window.webkitSpeechRecognition();
        return true;
      },
    },
  ]);
}

export function probeSpeechOutput() {
  return ladder('speech-output', [
    {
      rung: 'speechSynthesis',
      test: () => {
        if (!('speechSynthesis' in window)) return false;
        if (typeof window.SpeechSynthesisUtterance !== 'function') return false;
        new window.SpeechSynthesisUtterance('');
        return true;
      },
    },
  ]);
}

export function probeNotifications() {
  return ladder('notifications', [
    {
      rung: 'Notification (granted)',
      test: () => typeof Notification === 'function' && Notification.permission === 'granted',
    },
    {
      rung: 'Notification (grantable)',
      test: () => {
        if (typeof Notification !== 'function') return false;
        // Reported as available-but-ungranted rather than unavailable: the
        // mechanism exists, the user simply has not been asked yet.
        if (Notification.permission === 'denied') throw new Error('permission denied by user');
        return Notification.permission === 'default';
      },
    },
    { rung: 'in-page banner', test: () => true },
  ]);
}

export function probeStorage() {
  return ladder('storage', [
    { rung: 'indexedDB', test: () => typeof indexedDB !== 'undefined' && !!indexedDB.open },
  ]);
}

/**
 * Whether reminders survive the page being closed — the *web* baseline.
 *
 * On the web they do not. Firing is driven by an in-page timer, so a closed
 * tab fires nothing and a reopened tab delivers everything overdue at once.
 * This is reported rather than papered over, because a reminder you believe is
 * armed and is not is worse than no reminder at all.
 *
 * In a Capacitor shell this is replaced at boot by the answer from
 * src/platform.js, which knows whether the OS actually took the notification.
 * This function is the floor, not the final word — do not read it directly to
 * decide what to tell the user; read `platform.reminders.durable`.
 */
export function probeReminderDurability() {
  return {
    name: 'reminder-durability',
    available: false,
    rung: null,
    durable: false,
    notes: [
      'in-page timer: fires only while this tab is open; overdue reminders are delivered on next open',
      'service worker + periodic sync: not implemented — needs an installed PWA and is Chromium-only',
    ],
  };
}

export function probeAll() {
  return {
    storage: probeStorage(),
    speechInput: probeSpeechInput(),
    speechOutput: probeSpeechOutput(),
    notifications: probeNotifications(),
    reminderDurability: probeReminderDurability(),
  };
}

/** One-line human summary of everything that is not fully working. */
export function degradations(caps) {
  const out = [];
  for (const cap of Object.values(caps)) {
    if (!cap.available) out.push(`${cap.name}: unavailable (${cap.notes[cap.notes.length - 1] || 'no reason recorded'})`);
  }
  return out;
}
