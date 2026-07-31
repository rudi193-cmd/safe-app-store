// Voice in and out.
//
// Speech recognition is a one-shot-per-press listener rather than a
// continuous one. Continuous mode sounds better in a demo and is worse in
// use: it picks up the assistant's own synthesised reply and feeds it back as
// the next question. Press to talk, release to send.

import { probeSpeechInput, probeSpeechOutput } from './capability.js';

export class Listener {
  #recognition = null;
  #onPartial;
  #onFinal;
  #onError;
  #listening = false;

  constructor({ onPartial = () => {}, onFinal = () => {}, onError = () => {} } = {}) {
    this.#onPartial = onPartial;
    this.#onFinal = onFinal;
    this.#onError = onError;
    this.capability = probeSpeechInput();
  }

  get available() {
    return this.capability.available;
  }

  get listening() {
    return this.#listening;
  }

  #construct() {
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new Ctor();
    rec.lang = navigator.language || 'en-US';
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    return rec;
  }

  start() {
    if (!this.available || this.#listening) return false;
    const rec = this.#construct();
    let finalText = '';

    rec.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) finalText += result[0].transcript;
        else interim += result[0].transcript;
      }
      this.#onPartial((finalText + interim).trim());
    };
    rec.onerror = (event) => {
      // 'aborted' and 'no-speech' are ordinary outcomes of press-and-release,
      // not failures worth showing the user.
      if (event.error !== 'aborted' && event.error !== 'no-speech') this.#onError(event.error);
    };
    rec.onend = () => {
      this.#listening = false;
      this.#recognition = null;
      const text = finalText.trim();
      if (text) this.#onFinal(text);
    };

    this.#recognition = rec;
    this.#listening = true;
    rec.start();
    return true;
  }

  stop() {
    if (this.#recognition) this.#recognition.stop();
  }

  cancel() {
    if (this.#recognition) {
      this.#recognition.onend = null;
      this.#recognition.abort();
      this.#recognition = null;
      this.#listening = false;
    }
  }
}

export class Speaker {
  #queue = [];
  #speaking = false;
  enabled = true;

  constructor() {
    this.capability = probeSpeechOutput();
  }

  get available() {
    return this.capability.available;
  }

  /**
   * Queue a sentence. Called incrementally as the model streams, so replies
   * start being spoken before generation finishes.
   */
  say(text) {
    const clean = String(text || '').trim();
    if (!clean || !this.enabled || !this.available) return;
    this.#queue.push(clean);
    this.#drain();
  }

  #drain() {
    if (this.#speaking || !this.#queue.length) return;
    const next = this.#queue.shift();
    const utterance = new SpeechSynthesisUtterance(next);
    utterance.lang = navigator.language || 'en-US';
    utterance.rate = 1.05;
    this.#speaking = true;
    const done = () => {
      this.#speaking = false;
      this.#drain();
    };
    utterance.onend = done;
    utterance.onerror = done;
    window.speechSynthesis.speak(utterance);
  }

  stop() {
    this.#queue.length = 0;
    this.#speaking = false;
    if (this.available) window.speechSynthesis.cancel();
  }
}

/**
 * Split streamed text into speakable chunks at sentence boundaries.
 *
 * Returns the complete sentences found and whatever tail is left over, so the
 * caller can carry the tail into the next chunk. Speaking token-by-token
 * produces robotic word salad; waiting for the whole reply defeats streaming.
 */
export function sentences(buffer) {
  const out = [];
  let rest = buffer;
  const boundary = /[.!?]["')\]]?\s+/;
  for (;;) {
    const match = rest.match(boundary);
    if (!match) break;
    const end = match.index + match[0].length;
    out.push(rest.slice(0, end).trim());
    rest = rest.slice(end);
  }
  return { spoken: out.filter(Boolean), rest };
}
