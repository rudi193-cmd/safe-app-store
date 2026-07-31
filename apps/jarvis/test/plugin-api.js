// Static conformance: does every Capacitor API the bridge calls actually exist?
//
// This exists because of a specific gap. The native branches of
// src/platform.js cannot be executed here — no Android SDK, no Xcode — so the
// usual gate does not reach them. The realistic way that code is wrong is not
// subtle logic, it is a method that does not exist: a plausible-sounding
// `LocalNotifications.scheduleAt()`, a `Preferences.getItem()`, a permission
// field called `granted` instead of `display`. Those fail on a device, weeks
// later, in a build nobody can reproduce.
//
// So: read the installed plugins' own type definitions and assert every
// symbol the bridge uses is really there.
//
// Be exact about the strength of this. It catches an *invented* API. It does
// not catch a *wrong* one — passing the right method the wrong argument
// shape, or misreading what a return value means, sails straight through.
// It is a spelling check against the real package, not evidence the wrap
// works. Only a device gives you that.

import fs from 'node:fs/promises';
import path from 'node:path';

/**
 * Every Capacitor symbol src/platform.js depends on.
 *
 * Kept as data rather than scraped out of the source, so that adding a call
 * to the bridge without declaring it here is itself caught: the drift check
 * at the bottom greps platform.js for plugin calls and fails on anything
 * missing from this table.
 */
export const REQUIRED = [
  {
    plugin: 'LocalNotifications',
    package: '@capacitor/local-notifications',
    methods: ['schedule', 'cancel', 'getPending', 'checkPermissions', 'requestPermissions', 'checkExactNotificationSetting'],
    // Field paths the bridge reads off results or writes into options.
    fields: [
      ['LocalNotificationSchema', 'id'],
      ['LocalNotificationSchema', 'title'],
      ['LocalNotificationSchema', 'body'],
      ['LocalNotificationSchema', 'schedule'],
      ['Schedule', 'at'],
      ['Schedule', 'allowWhileIdle'],
      ['ScheduleOptions', 'notifications'],
      ['PendingResult', 'notifications'],
      ['PermissionStatus', 'display'],
      ['SettingsPermissionStatus', 'exact_alarm'],
    ],
  },
  {
    plugin: 'Preferences',
    package: '@capacitor/preferences',
    methods: ['get', 'set', 'remove'],
    fields: [
      ['GetResult', 'value'],
      ['SetOptions', 'key'],
      ['SetOptions', 'value'],
    ],
  },
  {
    plugin: 'Haptics',
    package: '@capacitor/haptics',
    methods: ['impact'],
    fields: [['ImpactOptions', 'style']],
  },
];

/** Capacitor globals the bridge calls. These live on the core type, not a plugin. */
export const REQUIRED_CORE = ['getPlatform', 'isNativePlatform', 'isPluginAvailable', 'registerPlugin'];

async function readDefs(root, pkg) {
  const file = path.join(root, 'node_modules', pkg, 'dist', 'esm', 'definitions.d.ts');
  return fs.readFile(file, 'utf8');
}

function hasMethod(src, name) {
  // Matches a method signature inside an interface: `  name(opts): Promise<T>;`
  return new RegExp(`^\\s+${name}\\s*\\(`, 'm').test(src);
}

function hasField(src, iface, field) {
  const block = src.match(new RegExp(`export interface ${iface}\\b[^{]*\\{([\\s\\S]*?)\\n\\}`, 'm'));
  if (!block) return false;
  return new RegExp(`^\\s+${field}\\??\\s*[:?]`, 'm').test(block[1]);
}

export async function checkPluginApi(root) {
  const results = [];

  for (const spec of REQUIRED) {
    let src;
    try {
      src = await readDefs(root, spec.package);
    } catch (err) {
      results.push({ name: `${spec.plugin}: type definitions readable`, pass: false, error: err.message });
      continue;
    }

    for (const method of spec.methods) {
      results.push({
        name: `${spec.plugin}.${method}() exists`,
        pass: hasMethod(src, method),
        error: `not found in ${spec.package} definitions — the bridge calls a method this plugin does not have`,
      });
    }
    for (const [iface, field] of spec.fields) {
      results.push({
        name: `${spec.plugin} ${iface}.${field} exists`,
        pass: hasField(src, iface, field),
        error: `not found in ${spec.package} — the bridge reads or writes a field this plugin does not define`,
      });
    }
  }

  // Core globals.
  try {
    const core = await fs.readFile(path.join(root, 'node_modules', '@capacitor', 'core', 'types', 'definitions.d.ts'), 'utf8');
    const block = core.match(/export interface CapacitorGlobal\b[^{]*\{([\s\S]*?)\n\}/m);
    for (const name of REQUIRED_CORE) {
      results.push({
        name: `Capacitor.${name} is on the public typed contract`,
        pass: Boolean(block) && new RegExp(`^\\s+${name}[?]?\\s*[:(]`, 'm').test(block[1]),
        // Capacitor.Plugins is the trap here: it exists at runtime but is not
        // on this interface, so code depending on it can break without that
        // being a breaking change.
        error: 'not declared on CapacitorGlobal — depending on it means depending on an undocumented runtime field',
      });
    }
  } catch (err) {
    results.push({ name: 'Capacitor core type definitions readable', pass: false, error: err.message });
  }

  // Drift: does the bridge call anything this file does not know about?
  try {
    const bridge = await fs.readFile(path.join(root, 'src', 'platform.js'), 'utf8');
    const declared = new Set(REQUIRED.flatMap((s) => s.methods));
    const called = new Set();
    for (const m of bridge.matchAll(/this\.#plugin\.([a-zA-Z]+)\(/g)) called.add(m[1]);
    for (const m of bridge.matchAll(/\bplugin\.([a-zA-Z]+)\(/g)) called.add(m[1]);
    const undeclared = [...called].filter((n) => !declared.has(n));
    results.push({
      name: 'every plugin call in the bridge is declared here',
      pass: undeclared.length === 0,
      error: `undeclared plugin calls: ${undeclared.join(', ')} — add them to REQUIRED so they are checked`,
    });
  } catch (err) {
    results.push({ name: 'bridge source readable', pass: false, error: err.message });
  }

  return results;
}

/**
 * The packaged app, not the source tree.
 *
 * Two things here are silent-failure shaped, which is why they are gates
 * rather than instructions in a README:
 *
 *   * `www/` is what actually ships. If the packaging whitelist drifts, the
 *     native app installs fine and shows a blank screen.
 *   * `SCHEDULE_EXACT_ALARM` is not merged in by the plugin. Without it,
 *     Android 12+ downgrades every reminder to inexact — nothing errors,
 *     nothing warns, the reminders just arrive late. That silently undoes the
 *     main reason for wrapping the app at all.
 */
export async function checkPackaging(root) {
  const results = [];

  const config = path.join(root, 'capacitor.config.json');
  let webDir = null;
  try {
    const parsed = JSON.parse(await fs.readFile(config, 'utf8'));
    webDir = parsed.webDir;
    results.push({
      name: 'capacitor.config.json is valid and names a webDir',
      pass: Boolean(webDir),
      error: 'no webDir — Capacitor would not know what to package',
    });
  } catch (err) {
    results.push({ name: 'capacitor.config.json is valid', pass: false, error: err.message });
    return results;
  }

  for (const rel of ['index.html', 'src/app.js', 'src/platform.js', 'styles.css', 'vendor/anthropic.js']) {
    let present = false;
    try {
      await fs.access(path.join(root, webDir, rel));
      present = true;
    } catch {
      /* reported below */
    }
    results.push({
      name: `packaged app contains ${rel}`,
      pass: present,
      error: `missing from ${webDir}/ — run npm run build:www; the installed app would be blank`,
    });
  }

  // node_modules inside the payload would mean shipping the whole dev tree.
  let leaked = false;
  try {
    await fs.access(path.join(root, webDir, 'node_modules'));
    leaked = true;
  } catch {
    /* good */
  }
  results.push({
    name: 'packaged app does not include node_modules',
    pass: !leaked,
    error: `${webDir}/node_modules exists — the packaging whitelist has been replaced by something leakier`,
  });

  // The Android manifest, when the platform has been added.
  const manifest = path.join(root, 'android', 'app', 'src', 'main', 'AndroidManifest.xml');
  try {
    const xml = await fs.readFile(manifest, 'utf8');
    results.push({
      name: 'android manifest declares SCHEDULE_EXACT_ALARM',
      pass: xml.includes('android.permission.SCHEDULE_EXACT_ALARM'),
      error: 'absent — Android 12+ will silently deliver every reminder late, which is the thing the wrap exists to fix',
    });
  } catch {
    results.push({
      name: 'android platform present (skipped — run npx cap add android)',
      pass: true,
    });
  }

  return results;
}
