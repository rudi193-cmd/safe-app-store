async function loadApps(q) {
  const url = "/api/catalog" + (q ? "?q=" + encodeURIComponent(q) : "");
  const res = await fetch(url);
  const data = await res.json();
  return data.apps || [];
}

function render(apps) {
  const ul = document.getElementById("apps");
  ul.innerHTML = "";
  for (const app of apps) {
    const li = document.createElement("li");
    li.innerHTML =
      "<h2>" + escapeHtml(app.title) + "</h2>" +
      "<p>" + escapeHtml(app.blurb) + "</p>" +
      "<p><small>ages " + escapeHtml(app.age_band) + " · " + escapeHtml(app.abi) + "</small></p>";
    const btn = document.createElement("button");
    btn.textContent = "Ask parent";
    btn.addEventListener("click", () => requestApp(app.id, btn));
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function requestApp(appId, btn) {
  const status = document.getElementById("status");
  btn.disabled = true;
  const body = {
    subject_id: document.getElementById("subject").value.trim(),
    app_id: appId,
    asked_by: document.getElementById("asked_by").value.trim(),
    within_hours: 48,
  };
  try {
    const res = await fetch("/api/requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    status.textContent =
      "Request sent. Status: " + data.request.disposition + " (due " + data.request.due_by + ")";
  } catch (e) {
    status.textContent = "Could not send request: " + e.message;
    btn.disabled = false;
  }
}

let timer;
document.getElementById("q").addEventListener("input", (ev) => {
  clearTimeout(timer);
  timer = setTimeout(() => loadApps(ev.target.value).then(render), 200);
});

loadApps("").then(render);
