async function getJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

const SUBJECT_KEY = "playgate.subject";

async function loadRoster() {
  // The roster comes from the host, which was started with an explicit
  // --subject list. There is no text box here on purpose: a consent log whose
  // subject is a name the requester typed records an assertion, not an
  // identity.
  //
  // Nor is there a default. The picker used to select the first child on the
  // roster, which meant a reload silently reattributed the next request to a
  // sibling — the roster stopped a child TYPING a false name while quietly
  // supplying one, and the resulting row was indistinguishable from a true
  // one. The placeholder below carries an empty value, so "nobody chose" is a
  // state the host can refuse rather than a state it cannot see.
  const select = document.getElementById("subject");
  const { subjects } = await getJSON("/api/roster");
  select.innerHTML = "";

  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "choose your name";
  select.appendChild(placeholder);

  for (const id of subjects) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = id;
    select.appendChild(option);
  }

  // Remembered so a child does not re-pick on every reload — which is what
  // made the default tempting in the first place. Only honoured if the host
  // still lists them: a roster is the host's to change.
  let remembered = null;
  try {
    remembered = window.localStorage.getItem(SUBJECT_KEY);
  } catch (e) {
    remembered = null;              // private browsing, or storage disabled
  }
  select.value = subjects.includes(remembered) ? remembered : "";
}

function currentSubject() {
  return document.getElementById("subject").value;
}

function rememberSubject(id) {
  try {
    if (id) window.localStorage.setItem(SUBJECT_KEY, id);
    else window.localStorage.removeItem(SUBJECT_KEY);
  } catch (e) {
    /* storage is a convenience here; the picker still works without it */
  }
}

async function loadStates() {
  // What this child asked for and what happened — including the answers. A
  // surface that shows only what is still pending tells a child who was
  // refused that nothing was ever asked.
  const subject = currentSubject();
  if (!subject) return {};
  const { requests } = await getJSON(
    "/api/requests?subject=" + encodeURIComponent(subject),
  );
  const byApp = {};
  for (const r of requests) byApp[r.app_id] = r;   // newest row wins
  return byApp;
}

async function loadApps(q) {
  const url = "/api/catalog" + (q ? "?q=" + encodeURIComponent(q) : "");
  const { apps } = await getJSON(url);
  return apps;
}

const DISMISSAL_WORDS = {
  immediate: "you can close it right away",
  after_delay: "you have to wait before you can close it",
  unskippable: "you cannot close it",
  deceptive_close: "the close button is easy to miss and opens the ad",
};

function interruptionLine(interruption) {
  // Four facts, unweighted. No badge, no colour scale, no score — a single
  // number here would be somebody's weights wearing the clothes of a
  // measurement, and it would become the thing publishers optimise.
  const p = document.createElement("p");
  p.className = "interruption";

  if (interruption.provenance === "assumed") {
    p.textContent = "Interruptions: nobody has checked this one yet.";
    return p;
  }

  const parts = [
    `stops you about ${interruption.count_per_10min} times in 10 minutes`,
  ];
  if (interruption.dismissal && DISMISSAL_WORDS[interruption.dismissal]) {
    parts.push(DISMISSAL_WORDS[interruption.dismissal]);
  }
  if (interruption.provenance === "measured") {
    parts.push(`someone watched this on ${interruption.observed_at}`);
  } else {
    parts.push("worked out from what the app contains, not from watching it");
  }
  p.textContent = "Interruptions: " + parts.join(" — ") + ".";
  return p;
}

// A child reads these, so they say what happened in words a child uses.
// Deliberately no colour-coding and no icons: "your parent said no" is not an
// error state, it is an answer, and dressing it in red would teach that asking
// was the mistake.
const STATE_WORDS = {
  open: "Waiting for a parent to answer.",
  granted: "A parent said yes.",
  installed: "A parent said yes — it is on your tablet.",
  install_failed: "A parent said yes, but it did not install. Tell them.",
  refused: "A parent said no.",
  expired: "Nobody answered in time. You can ask again.",
};

function stateLine(state) {
  const p = document.createElement("p");
  p.className = "state";
  let text = STATE_WORDS[state.disposition] || "";
  // The reason is shown to the child, not just logged for the adult. A refusal
  // a child cannot read is indistinguishable to them from being ignored.
  if (state.disposition === "refused" && state.reason) {
    text += " " + state.reason;
  }
  p.textContent = text;
  return p;
}

function render(apps, states) {
  states = states || {};
  // textContent throughout rather than innerHTML: the catalog is a local file
  // an operator wrote, but a renderer that only works on trusted input is one
  // catalog source away from not working.
  const ul = document.getElementById("apps");
  ul.innerHTML = "";
  for (const app of apps) {
    const li = document.createElement("li");

    const h2 = document.createElement("h2");
    h2.textContent = app.title;
    li.appendChild(h2);

    const blurb = document.createElement("p");
    blurb.textContent = app.blurb;
    li.appendChild(blurb);

    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `ages ${app.age_band} · ${app.abi}`;
    li.appendChild(meta);

    li.appendChild(interruptionLine(app.interruption));

    const state = states[app.id];
    if (state) li.appendChild(stateLine(state));

    const btn = document.createElement("button");
    btn.textContent = "Ask a parent";
    // Two reasons a child cannot ask right now, and the button says which:
    // nobody has picked a name, or this one is already waiting on an adult.
    // A refused or expired request does NOT lock the button — appending a new
    // request is the designed path, and the answer above stays visible so a
    // second ask is made knowing the first was declined.
    if (!currentSubject()) {
      btn.disabled = true;
      btn.title = "Choose your name first";
    } else if (state && state.disposition === "open") {
      btn.disabled = true;
      btn.title = "Already asked — waiting for a parent";
    }
    btn.addEventListener("click", () => requestApp(app.id, btn));
    li.appendChild(btn);

    ul.appendChild(li);
  }
}

async function requestApp(appId, btn) {
  const status = document.getElementById("status");
  const subject = currentSubject();
  if (!subject) {
    // Belt and braces: the button is already disabled without a name. The host
    // refuses an empty subject too — this is the third layer, not the only one.
    status.textContent = "Choose your name first, so a parent knows who asked.";
    return;
  }
  btn.disabled = true;
  try {
    const res = await fetch("/api/requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subject_id: subject,
        app_id: appId,
        asked_by: subject,
        within_hours: 48,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    status.textContent = "Asked. A parent will answer by " + data.request.due_by + ".";
    await refresh();          // the card now shows "waiting", and survives a reload
  } catch (e) {
    status.textContent = "Could not ask: " + e.message;
    btn.disabled = false;
  }
}

async function refresh() {
  const [apps, states] = await Promise.all([
    loadApps(document.getElementById("q").value),
    loadStates(),
  ]);
  render(apps, states);
}

let timer;
document.getElementById("q").addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(() => refresh().catch(showHostError), 200);
});

document.getElementById("subject").addEventListener("change", (ev) => {
  rememberSubject(ev.target.value);
  // Re-rendered rather than left alone: the cards carry this child's answers,
  // so they are wrong the instant the child changes.
  refresh().catch(showHostError);
});

function showHostError(e) {
  document.getElementById("status").textContent =
    "Could not reach the Playgate host: " + e.message;
}

loadRoster()
  .then(refresh)
  .catch(showHostError);
