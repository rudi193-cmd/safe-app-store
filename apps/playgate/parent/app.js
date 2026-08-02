async function getJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function el(tag, text) {
  const n = document.createElement(tag);
  if (text) n.textContent = text;
  return n;
}

let catalogById = {};

async function loadCatalog() {
  const { apps } = await getJSON("/api/catalog");
  catalogById = Object.fromEntries(apps.map((a) => [a.id, a]));
}

const DISMISSAL_WORDS = {
  immediate: "closes immediately",
  after_delay: "closes after a forced delay",
  unskippable: "cannot be closed",
  deceptive_close: "close target is easy to miss and opens the ad",
};

function evidence(app) {
  // What the parent is deciding on. Four facts and the provenance state,
  // unweighted — the decision about whether this is acceptable for this child
  // is not one the software is entitled to an opinion about.
  const wrap = el("p");
  wrap.className = "evidence";
  if (!app) {
    wrap.textContent = "This app is no longer in the catalog.";
    return wrap;
  }
  const i = app.interruption;
  if (i.provenance === "assumed") {
    wrap.textContent =
      "Interruptions: nobody has checked. Ten minutes with the child is the " +
      "only way to change that.";
    return wrap;
  }
  const bits = [`about ${i.count_per_10min} per 10 minutes of play`];
  if (i.dismissal && DISMISSAL_WORDS[i.dismissal]) bits.push(DISMISSAL_WORDS[i.dismissal]);
  bits.push(
    i.provenance === "measured"
      ? `observed on ${i.observed_at} by ${i.observed_by} (build ${i.observed_version})`
      : `derived, not observed — ${i.note || "no rule stated"}`,
  );
  wrap.textContent = "Interruptions: " + bits.join(" · ") + ".";
  return wrap;
}

async function render() {
  const ul = document.getElementById("inbox");
  ul.innerHTML = "";
  const { requests } = await getJSON("/api/requests?view=open");
  if (!requests.length) {
    ul.appendChild(el("li", "No open requests."));
    return;
  }
  for (const r of requests) {
    const li = el("li");
    li.appendChild(el("strong", r.app_id + " for " + r.subject_id));
    li.appendChild(document.createElement("br"));
    li.appendChild(el("span", "asked by " + r.asked_by + " · due " + r.due_by));
    li.appendChild(evidence(catalogById[r.app_id]));

    const reason = document.createElement("input");
    reason.className = "reason";
    // Required on grant as well as refuse. Every app store logs installs and
    // none of them logs why.
    reason.placeholder = "Reason (required, either way)";

    const row = el("div");
    row.className = "actions";
    const grant = el("button", "Grant and install");
    grant.className = "grant";
    const refuse = el("button", "Refuse");
    refuse.className = "refuse";
    grant.addEventListener("click", () => answer(r.request_id, true, reason.value, grant));
    refuse.addEventListener("click", () => answer(r.request_id, false, reason.value, refuse));
    row.appendChild(grant);
    row.appendChild(refuse);

    li.appendChild(reason);
    li.appendChild(row);
    ul.appendChild(li);
  }
}

async function answer(requestId, granted, reason, btn) {
  const msg = document.getElementById("msg");
  const by = document.getElementById("parent").value.trim();
  if (!reason.trim()) {
    msg.textContent = "Enter a reason first — for a grant as well as a refusal.";
    return;
  }
  btn.disabled = true;
  msg.textContent = granted ? "Verifying and installing…" : "Recording…";
  try {
    const res = await fetch("/api/requests/" + requestId + "/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ granted, by, reason: reason.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed");

    if (!data.install) {
      msg.textContent = "Recorded: " + data.request.disposition + ".";
    } else if (data.install.ok) {
      msg.textContent = "Granted and installed. " + data.install.detail;
    } else {
      // The failure is shown and it is also already in the log. A grant that
      // did not install and a grant that did are different facts.
      msg.textContent = "Granted, but the install failed: " + data.install.detail;
    }
  } catch (e) {
    msg.textContent = e.message;
  } finally {
    btn.disabled = false;
    render();
  }
}

document.getElementById("refresh").addEventListener("click", render);

loadCatalog()
  .then(render)
  .catch((e) => {
    document.getElementById("msg").textContent =
      "Could not reach the Playgate host: " + e.message;
  });
