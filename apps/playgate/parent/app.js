async function fetchOpen() {
  const res = await fetch("/api/requests?view=open");
  const data = await res.json();
  return data.requests || [];
}

function el(tag, text) {
  const n = document.createElement(tag);
  if (text) n.textContent = text;
  return n;
}

async function render() {
  const ul = document.getElementById("inbox");
  ul.innerHTML = "";
  const reqs = await fetchOpen();
  if (!reqs.length) {
    ul.appendChild(el("li", "No open requests."));
    return;
  }
  for (const r of reqs) {
    const li = el("li");
    li.appendChild(el("strong", r.app_id + " for " + r.subject_id));
    li.appendChild(document.createElement("br"));
    li.appendChild(el("span", "from " + r.asked_by + " · due " + r.due_by));
    const reason = document.createElement("input");
    reason.className = "reason";
    reason.placeholder = "Reason (required)";
    const row = el("div");
    row.className = "actions";
    const grant = el("button", "Grant");
    grant.className = "grant";
    const refuse = el("button", "Refuse");
    refuse.className = "refuse";
    grant.addEventListener("click", () => answer(r.request_id, true, reason.value));
    refuse.addEventListener("click", () => answer(r.request_id, false, reason.value));
    row.appendChild(grant);
    row.appendChild(refuse);
    li.appendChild(reason);
    li.appendChild(row);
    ul.appendChild(li);
  }
}

async function answer(requestId, granted, reason) {
  const msg = document.getElementById("msg");
  const by = document.getElementById("parent").value.trim();
  if (!reason.trim()) {
    msg.textContent = "Enter a reason first.";
    return;
  }
  const res = await fetch("/api/requests/" + requestId + "/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ granted, by, reason: reason.trim() }),
  });
  const data = await res.json();
  if (!res.ok) {
    msg.textContent = data.error || "Failed";
    return;
  }
  msg.textContent =
    "Recorded " +
    data.request.disposition +
    ". If granted, run: python3 -m playgate install --request-id " +
    requestId;
  render();
}

document.getElementById("refresh").addEventListener("click", render);
render();
