// The native bridge.
//
// This file is the whole of the Capacitor wrap as far as the app is
// concerned. Everything else in src/ is unchanged and unaware: the app asks
// this module to schedule a reminder or store a key, and gets back a result
// that says which implementation answered. Same code runs in a browser tab
// and in a native shell, and the difference is reported rather than assumed.
//
// The seam is the same ordered-ladder-with-notes shape used in
// capability.js, for the same reason. A wrap that silently falls back to the
// web implementation when a plugin is missing is worse than one that fails,
// because "your reminder is set" means two completely different things
// depending on which rung answered, and the user cannot tell which they got.
//
// ────────────────────────────────────────────────────────────────────────
// NOTHING IN THE NATIVE BRANCHES OF THIS FILE HAS EVER EXECUTED.
//
// There is no Android SDK and no Xcode in the environment this was written
// in, so no APK and no IPA was ever produced, installed, or run. The web
// branches are covered by the suite in real Chromium. The native branches
// are covered by a static check that the plugin methods called here exist in
// the installed plugins' type definitions — which catches an invented API,
// and cannot catch a wrong one. Treat every native path as unverified until
// it has run on a device. See README, "What the wrap does not prove".
// ────────────────────────────────────────────────────────────────────────

// Plugins are reached through `Capacitor.registerPlugin`, not by importing
// the npm package and not through `Capacitor.Plugins`.
//
// Importing `@capacitor/local-notifications` is the documented path, but it
// is a bare specifier — it needs a bundler, and this app deliberately has no
// build step. `Capacitor.Plugins` does exist at runtime and would work, but
// it is absent from the `CapacitorGlobal` type definition, which makes it an
// undocumented field that can be removed without it being a breaking change.
// `registerPlugin` is on the public typed contract, returns the same native
// bridge proxy, and is exactly what the plugin packages call internally.
//
// The npm packages are still installed, for two reasons that are not about
// this file: `npx cap sync` copies their native halves into the Android and
// iOS projects, and the conformance check in test/plugin-api.js reads their
// type definitions to verify the method names used below actually exist.
const PLUGIN_NAMES = ['LocalNotifications', 'Preferences', 'Haptics'];

/** True only inside a Capacitor native shell. False in every browser. */
export function isNative() {
  const cap = globalThis.Capacitor;
  return Boolean(cap && typeof cap.isNativePlatform === 'function' && cap.isNativePlatform());
}

export function platformName() {
  const cap = globalThis.Capacitor;
  if (cap && typeof cap.getPlatform === 'function') return cap.getPlatform();
  return 'web';
}

/**
 * Is a specific Capacitor plugin actually present?
 *
 * Checked through Capacitor's own registry rather than by whether the import
 * resolves. A plugin's JS package installs fine on any platform; what decides
 * whether calling it does anything is whether the native half was built into
 * the shell. `isPluginAvailable` is the question that actually matters, and
 * getting this wrong is how you ship an app that reports reminders as durable
 * and silently drops them.
 */
export function hasPlugin(name) {
  const cap = globalThis.Capacitor;
  if (!cap || typeof cap.isPluginAvailable !== 'function') return false;
  return cap.isPluginAvailable(name);
}

function loadPlugin(name) {
  if (!PLUGIN_NAMES.includes(name)) return null;
  // Both guards matter and they answer different questions. `isNative` asks
  // whether there is a native shell at all; `hasPlugin` asks whether this
  // particular plugin's native half was compiled into it. A JS package
  // installs cleanly regardless, so skipping the second check is how you ship
  // a build that reports reminders as durable and silently drops them.
  if (!isNative() || !hasPlugin(name)) return null;
  try {
    return globalThis.Capacitor.registerPlugin(name);
  } catch {
    return null;
  }
}

// --- reminders ---------------------------------------------------------------

/**
 * Reminder scheduling.
 *
 * The one capability where the wrap changes what the product can honestly
 * promise. On the web a reminder is an in-page timer: close the tab and it
 * never fires. Natively it is an OS-scheduled local notification, which fires
 * with the app closed and needs no server. That is the whole reason to wrap
 * this rather than leave it a web app.
 *
 * `durable` is the machine-readable version of that difference and is what
 * the capability panel and the model's own confirmation wording both read.
 */
export class Reminders {
  #plugin = null;
  #ready = null;

  constructor() {
    this.rung = 'in-page timer';
    this.durable = false;
    this.notes = [];
  }

  async init() {
    if (this.#ready) return this.#ready;
    this.#ready = (async () => {
      if (!isNative()) {
        this.notes.push('OS local notifications: not a native shell — running in a browser');
        return this;
      }
      const plugin = loadPlugin('LocalNotifications');
      if (!plugin) {
        this.notes.push('OS local notifications: plugin not present in this build');
        return this;
      }

      // Permission is a separate question from plugin availability, and on
      // Android 13+ a refusal is silent at schedule time. Ask, and record the
      // answer as the reason rather than discovering it when nothing fires.
      let status = await plugin.checkPermissions();
      if (status.display !== 'granted') status = await plugin.requestPermissions();
      if (status.display !== 'granted') {
        this.notes.push(`OS local notifications: permission ${status.display}`);
        return this;
      }

      this.#plugin = plugin;
      this.rung = 'OS local notifications';
      this.durable = true;

      // Android 12+ downgrades scheduled alarms to inexact unless the app
      // holds SCHEDULE_EXACT_ALARM *and* the user leaves it enabled. An
      // inexact reminder still fires, just late — so this is a note, not a
      // demotion, and the user can see it.
      try {
        const exact = await plugin.checkExactNotificationSetting();
        if (exact.exact_alarm !== 'granted') {
          this.notes.push(`exact timing: ${exact.exact_alarm} — reminders may fire late`);
        }
      } catch {
        // iOS has no such setting; the call simply does not apply there.
      }
      return this;
    })();
    return this.#ready;
  }

  /**
   * Hand a reminder to the OS. Returns false when this is the web rung, which
   * is the caller's signal to keep driving its own timer.
   */
  async schedule({ id, at, text }) {
    if (!this.#plugin) return false;
    await this.#plugin.schedule({
      notifications: [
        {
          id: Number(id),
          title: 'Willow',
          body: String(text),
          schedule: { at: new Date(at), allowWhileIdle: true },
        },
      ],
    });
    return true;
  }

  async cancel(id) {
    if (!this.#plugin) return false;
    await this.#plugin.cancel({ notifications: [{ id: Number(id) }] });
    return true;
  }

  async pending() {
    if (!this.#plugin) return null;
    const result = await this.#plugin.getPending();
    return result.notifications;
  }
}

// --- key storage -------------------------------------------------------------

/**
 * Where the API key lives.
 *
 * In a browser it is localStorage, readable by any script on the page. In a
 * native shell it is Capacitor Preferences, which is app-private storage
 * (UserDefaults on iOS, SharedPreferences on Android) that other apps cannot
 * read.
 *
 * Be precise about what that does and does not buy: it removes the
 * any-script-on-the-page exposure, which is the realistic threat for a web
 * page. It is NOT Keychain or Keystore — the value is not hardware-backed
 * and not encrypted at rest beyond whatever full-disk encryption the device
 * already does, and it is readable on a rooted or jailbroken device and may
 * be included in a device backup. Calling this "secure storage" would be the
 * kind of guarantee-without-a-mechanism this project exists to refuse.
 */
export class KeyStore {
  #plugin = null;
  #ready = null;

  constructor({ fallback = globalThis.localStorage } = {}) {
    this.rung = 'localStorage';
    this.notes = [];
    this.appPrivate = false;
    this.fallback = fallback;
  }

  async init() {
    if (this.#ready) return this.#ready;
    this.#ready = (async () => {
      const plugin = loadPlugin('Preferences');
      if (!plugin) {
        this.notes.push(
          isNative()
            ? 'app-private preferences: plugin not present in this build'
            : 'app-private preferences: not a native shell — any script on this page can read the key',
        );
        return this;
      }
      this.#plugin = plugin;
      this.rung = 'app-private preferences';
      this.appPrivate = true;
      this.notes.push('not hardware-backed: readable on a rooted or jailbroken device, and may be included in a device backup');
      return this;
    })();
    return this.#ready;
  }

  async get(key) {
    if (this.#plugin) return (await this.#plugin.get({ key })).value;
    return this.fallback?.getItem(key) ?? null;
  }

  async set(key, value) {
    if (this.#plugin) return this.#plugin.set({ key, value: String(value) });
    this.fallback?.setItem(key, String(value));
    return undefined;
  }

  async remove(key) {
    if (this.#plugin) return this.#plugin.remove({ key });
    this.fallback?.removeItem(key);
    return undefined;
  }
}

// --- haptics -----------------------------------------------------------------

/** Tap feedback on press-to-talk. A no-op everywhere it is unavailable. */
export class Haptics {
  #plugin = null;

  async init() {
    this.#plugin = loadPlugin('Haptics');
    return this;
  }

  async tap() {
    if (!this.#plugin) return false;
    try {
      await this.#plugin.impact({ style: 'MEDIUM' });
      return true;
    } catch {
      return false;
    }
  }
}

/** One object for the app to hold, with every rung already resolved. */
export async function createPlatform(options = {}) {
  const reminders = await new Reminders().init();
  const keys = await new KeyStore(options).init();
  const haptics = await new Haptics().init();
  return { native: isNative(), platform: platformName(), reminders, keys, haptics };
}
