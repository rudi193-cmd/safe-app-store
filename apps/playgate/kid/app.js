async function getJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function loadRoster() {
  // The roster comes from the host, which was started with an explicit
  // --subject list. There is no text box here on purpose: a consent log whose
  // subject is a name the requester typed records an assertion, not an
  // identity.
  const select = document.getElementById("subject");
  const { subjects } = await getJSON("/api/roster");
  select.innerHTML = "";
  for (const id of subjects) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = id;
    select.appendChild(option);
  }
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

function render(apps) {
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

    const btn = document.createElement("button");
    btn.textContent = "Ask a parent";
    btn.addEventListener("click", () => requestApp(app.id, btn));
    li.appendChild(btn);

    ul.appendChild(li);
  }
}

async function requestApp(appId, btn) {
  const status = document.getElementById("status");
  const subject = document.getElementById("subject").value;
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
  } catch (e) {
    status.textContent = "Could not ask: " + e.message;
    btn.disabled = false;
  }
}

let timer;
document.getElementById("q").addEventListener("input", (ev) => {
  clearTimeout(timer);
  timer = setTimeout(
    () => loadApps(ev.target.value).then(render).catch(showHostError),
    200,
  );
});

function showHostError(e) {
  document.getElementById("status").textContent =
    "Could not reach the Playgate host: " + e.message;
}

loadRoster()
  .then(() => loadApps(""))
  .then(render)
  .catch(showHostError);
