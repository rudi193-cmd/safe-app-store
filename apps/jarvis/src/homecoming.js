// Tier 0 homecoming — the phone is a removable volume.
//
// The session-end deposit is the payload. This module shapes the phone seat's
// IndexedDB facts into that deposit. It does not invent a second vault sync,
// does not push, and does not carry vault.key. Home base pulls
// (`nestor import --apply` for pairs; review this JSON as a deposit).
//
// See willows-grove docs/design/phone-tier0-sync.md.

export function memoryDeposit(facts, { writtenAt = new Date().toISOString(), product = 'Willow' } = {}) {
  const rows = Array.isArray(facts) ? facts : [];
  return {
    kind: 'phone-seat-deposit',
    version: 1,
    product,
    transport: 'tier0-usb',
    written_at: writtenAt,
    import_hint: 'nestor import --apply for decision pairs; this file is the session-end deposit, not a second vault protocol',
    key_stays_home: true,
    facts: rows.map((f) => ({
      id: f.id,
      subject: f.subject,
      text: f.text,
      kind: f.kind,
      provenance: f.provenance,
      aliases: f.aliases || [],
      createdAt: f.createdAt,
      live: f.live,
      supersedes: f.supersedes ?? null,
    })),
  };
}

export function depositJson(facts, options) {
  return `${JSON.stringify(memoryDeposit(facts, options), null, 2)}\n`;
}
