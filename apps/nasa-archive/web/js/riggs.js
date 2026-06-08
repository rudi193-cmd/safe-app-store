/**
 * riggs.js — Riggs chat interface for NASA Archive
 * Dual backend: Willow SSE (primary) → standalone fallback
 */

(function () {
  var WILLOW_URL = window.WILLOW_URL || 'http://localhost:8420';
  var STANDALONE_URL = window.RIGGS_URL || 'http://localhost:8421';
  var messagesEl = document.getElementById('chat-messages');
  var inputEl = document.getElementById('chat-input');
  var sendBtn = document.getElementById('chat-send');
  var saveBtn = document.querySelector('.riggs-save');

  if (!messagesEl || !inputEl || !sendBtn) return;

  var history = [];
  var slug = document.body.dataset.slug || '';
  var pageType = document.body.dataset.pageType || 'general';

  // Context-aware placeholder
  var placeholders = {
    rally: 'Tell me what you remember\u2026',
    photo: 'What\u2019s the story behind this one?',
    club: 'Know anything about this club?',
    patch: 'Got a patch story?',
    general: 'Tell me what you remember\u2026'
  };
  inputEl.placeholder = placeholders[pageType] || placeholders.general;

  /** Append a message to the chat */
  function appendMessage(role, content) {
    var div = document.createElement('div');
    div.className = 'msg msg-' + (role === 'user' ? 'user' : 'riggs');

    var label = document.createElement('span');
    label.className = 'msg-label';
    label.textContent = role === 'user' ? 'You' : 'Riggs';

    var text = document.createElement('span');
    text.textContent = content;

    div.appendChild(label);
    div.appendChild(text);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return text;
  }

  /** Show typing indicator */
  function showTyping() {
    var div = document.createElement('div');
    div.className = 'msg msg-riggs msg-typing';
    div.id = 'riggs-typing';

    var label = document.createElement('span');
    label.className = 'msg-label';
    label.textContent = 'Riggs';

    var dots = document.createElement('span');
    dots.className = 'typing-dots';
    dots.textContent = '\u2026';

    div.appendChild(label);
    div.appendChild(dots);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function hideTyping() {
    var el = document.getElementById('riggs-typing');
    if (el) el.remove();
  }

  /** Build the prompt with context */
  function buildPrompt(message) {
    var ctx = '';
    if (pageType === 'rally' && slug) {
      ctx = ' [User is viewing rally: ' + slug.replace(/-/g, ' ') + ']';
    } else if (pageType === 'photo') {
      ctx = ' [User is viewing a rally photo]';
    } else if (pageType === 'club') {
      ctx = ' [User is browsing scooter clubs]';
    } else if (pageType === 'patch') {
      ctx = ' [User is browsing rally patches]';
    }

    var historyText = '';
    var recent = history.slice(-8);
    for (var i = 0; i < recent.length; i++) {
      var h = recent[i];
      historyText += (h.role === 'user' ? 'User' : 'Riggs') + ': ' + h.content + '\n';
    }

    return (historyText ? historyText + '\n' : '') +
      '[Do not address the user by name. Just talk naturally.]\n' +
      'User: ' + message + ctx;
  }

  /** Try Willow SSE endpoint */
  function tryWillow(message) {
    return new Promise(function (resolve, reject) {
      var prompt = buildPrompt(message);
      var controller = new AbortController();
      var timeout = setTimeout(function () { controller.abort(); }, 45000);

      fetch(WILLOW_URL + '/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt, persona: 'NASA_Riggs' }),
        signal: controller.signal
      }).then(function (res) {
        clearTimeout(timeout);
        if (!res.ok) { reject(new Error('Willow ' + res.status)); return; }

        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var chunks = [];
        hideTyping();
        var textEl = appendMessage('assistant', '');

        function cleanResponse(text) {
          // Strip tier prefix like "[Tier 4: Free cloud (Gemini)]"
          text = text.replace(/^\[Tier \d+:.*?\]\s*/, '');
          // Strip coherence metadata JSON that Willow appends
          text = text.replace(/\{["\s]*coherence_index[\s\S]*$/, '');
          // Strip any trailing JSON blocks (shiva logs, etc)
          text = text.replace(/\{["\s]*(?:log_success|log_file|delta_e|state)[\s\S]*$/, '');
          return text;
        }

        function read() {
          reader.read().then(function (result) {
            if (result.done) {
              var full = cleanResponse(chunks.join(''));
              textEl.textContent = full;
              resolve(full);
              return;
            }
            var text = decoder.decode(result.value, { stream: true });
            var lines = text.split('\n');
            for (var i = 0; i < lines.length; i++) {
              var line = lines[i];
              if (line.indexOf('data: ') === 0) {
                var data = line.substring(6);
                if (data === '[DONE]') continue;
                data = data.replace(/^\[Tier \d+:.*?\]/, '');
                if (!data) continue;
                chunks.push(data);
                textEl.textContent = cleanResponse(chunks.join(''));
                messagesEl.scrollTop = messagesEl.scrollHeight;
              }
            }
            read();
          }).catch(reject);
        }
        read();
      }).catch(function (err) {
        clearTimeout(timeout);
        reject(err);
      });
    });
  }

  /** Try standalone server */
  function tryStandalone(message) {
    return fetch(STANDALONE_URL + '/functions/v1/oral-chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        slug: slug,
        page_type: pageType,
        history: history.slice(-8)
      })
    }).then(function (res) {
      return res.json();
    }).then(function (data) {
      var reply = data.reply || 'Something went wrong. Try again.';
      hideTyping();
      appendMessage('assistant', reply);
      return reply;
    });
  }

  /** Send message — Willow first, standalone fallback */
  function sendMessage() {
    var message = inputEl.value.trim();
    if (!message) return;

    inputEl.value = '';
    sendBtn.disabled = true;
    sendBtn.textContent = '\u2026';

    appendMessage('user', message);
    history.push({ role: 'user', content: message });
    showTyping();

    tryWillow(message).then(function (reply) {
      history.push({ role: 'assistant', content: reply });
      saveSession();
    }).catch(function () {
      // Willow failed — try standalone
      tryStandalone(message).then(function (reply) {
        history.push({ role: 'assistant', content: reply });
        saveSession();
      }).catch(function () {
        hideTyping();
        appendMessage('assistant',
          'Riggs is offline right now. If you\u2019re running the archive locally, ' +
          'make sure Willow is up on port 8420. Otherwise, your message has been saved ' +
          'and Riggs will see it next time you\u2019re connected.'
        );
      });
    }).then(function () {
      sendBtn.textContent = '\u2192';
      sendBtn.disabled = false;
      inputEl.focus();
    });
  }

  /** Save to localStorage + session model */
  function saveSession() {
    var key = 'nasa-chat-' + (slug || pageType || 'general');
    try {
      localStorage.setItem(key, JSON.stringify(history));
    } catch (e) {}

    // Sync to session model if available
    if (window.NASASession && slug) {
      var session = window.NASASession.load(slug, slug.replace(/-/g, ' '));
      session.oral_history = history.map(function (h) {
        return { role: h.role, content: h.content, ts: new Date().toISOString() };
      });
      window.NASASession.save(session);
    }
  }

  /** Clean cached messages of any metadata leaks */
  function cleanContent(text) {
    if (!text) return text;
    return text
      .replace(/\{["\s]*coherence_index[\s\S]*$/, '')
      .replace(/\{["\s]*(?:log_success|log_file|delta_e|state)[\s\S]*$/, '')
      .trim();
  }

  /** Restore from localStorage */
  function restoreSession() {
    var key = 'nasa-chat-' + (slug || pageType || 'general');
    try {
      var saved = localStorage.getItem(key);
      if (saved) {
        history = JSON.parse(saved);
        for (var i = 0; i < history.length; i++) {
          // Clean any metadata that leaked into stored messages
          if (history[i].role !== 'user') {
            history[i].content = cleanContent(history[i].content);
          }
          appendMessage(history[i].role, history[i].content);
        }
        // Re-save cleaned version
        saveSession();
      }
    } catch (e) {}
  }

  // Event listeners
  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Save button — download conversation as local file
  if (saveBtn) {
    saveBtn.addEventListener('click', function () {
      if (history.length === 0) return;

      // Use richer session model if available
      var data;
      if (window.NASASession && slug) {
        data = window.NASASession.load(slug, slug.replace(/-/g, ' '));
      } else {
        data = {
          type: 'nasa_oral_history',
          rally: slug,
          page: pageType,
          timestamp: new Date().toISOString(),
          exchanges: history
        };
      }

      var blob = new Blob(
        [JSON.stringify(data, null, 2)],
        { type: 'application/json' }
      );
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'nasa-riggs-' + (slug || pageType) + '-' + Date.now() + '.json';
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  // Forget button — clear local data for this conversation
  var forgetBtn = document.querySelector('.riggs-forget');
  if (forgetBtn) {
    forgetBtn.addEventListener('click', function () {
      var key = 'nasa-chat-' + (slug || pageType || 'general');
      try { localStorage.removeItem(key); } catch (e) {}
      if (window.NASASession && slug) {
        try { localStorage.removeItem('nasa-session-' + slug); } catch (e) {}
      }
      history = [];
      messagesEl.innerHTML = '';
      appendMessage('assistant', 'Conversation cleared. Nothing saved.');
    });
  }

  // Restore prior session
  restoreSession();
})();
