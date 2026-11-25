// Minimal client of the Research Assistant API.
// EventSource only sends GET without headers, so the run (POST + Authorization header) is read with
// fetch() and a ReadableStream, and the text/event-stream body is parsed here.
const API = new URLSearchParams(location.search).get("api") || "";  // "" = same origin as this page
const $ = (id) => document.getElementById(id);
let sessionId = null;
let runId = null;  // the last run: feedback goes to its trace

const headers = () => ({ "Authorization": `Bearer ${$("user").value}`, "Content-Type": "application/json" });

async function call(path, options = {}) {
  const r = await fetch(API + path, { ...options, headers: headers() });
  const body = await r.json();
  if (!r.ok) throw new Error(`${body.status} ${body.title}: ${body.detail} (request_id ${body.request_id})`);
  return body;
}

async function newSession() {
  const s = await call("/v1/sessions", { method: "POST" });
  sessionId = s.session_id;
  $("session").textContent = `session ${sessionId}`;
  $("feedback").hidden = true;
  $("answer").textContent = ""; $("activity").innerHTML = ""; $("stats").textContent = "";
}

function log(html) {
  const li = document.createElement("li"); li.innerHTML = html; $("activity").appendChild(li);
}

const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
// The answer is short markdown: show **bold** and links, escape everything else.
const render = (md) => esc(md).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
  .replace(/(https?:\/\/[^\s|)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');

function onEvent(name, data) {
  if (name === "metadata") { runId = data.run_id; log(`run <code>${data.run_id}</code> started · trace <code>${data.trace_id.slice(0, 8)}</code>`); }
  else if (name === "step") log(data.node === "model" ? "model answered" : "tools ran");
  else if (name === "tool_call") log(`call <code>${esc(data.name)}</code> ${esc(JSON.stringify(data.args))}`);
  else if (name === "tool_result") log(`result <code>${esc(data.name)}</code> ${data.status}: ${esc(data.preview).slice(0, 80)}`);
  else if (name === "token") $("answer").textContent += data.text;
  else if (name === "done") {
    $("answer").innerHTML = render(data.answer);  // the final text, formatted
    $("stats").textContent = `done in ${data.seconds} s · ${data.model_calls} model calls · ` +
      `${data.input_tokens} input / ${data.output_tokens} output tokens`;
    resetFeedback(); $("feedback").hidden = false;
  } else if (name === "error") {
    $("answer").classList.add("error");
    $("answer").textContent = `${data.status} ${data.title}: ${data.detail} (request_id ${data.request_id})`;
  }
}

function resetFeedback() {
  $("up").classList.remove("chosen"); $("down").classList.remove("chosen");
  $("comment").value = ""; $("feedback-status").textContent = "";
}

// Session 07: thumbs up / down becomes the score "user-feedback" on the run's Langfuse trace.
async function sendFeedback(value) {
  const body = JSON.stringify({ value, comment: $("comment").value || null });
  const saved = await call(`/v1/sessions/${sessionId}/runs/${runId}/feedback`, { method: "POST", body });
  $("up").classList.toggle("chosen", value); $("down").classList.toggle("chosen", !value);
  $("feedback-status").textContent = `saved on trace ${saved.trace_id.slice(0, 8)}`;
}

async function run(message) {
  const r = await fetch(`${API}/v1/sessions/${sessionId}/runs`, {
    method: "POST", headers: headers(), body: JSON.stringify({ message }),
  });
  if (!r.ok) {  // 401, 404, 422: a JSON problem, no stream
    const p = await r.json();
    return onEvent("error", p);
  }
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {  // one SSE event ends with a blank line
      const block = buffer.slice(0, end); buffer = buffer.slice(end + 2);
      let name = "message", data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }                                           // lines starting with ":" are keep-alive pings
      if (data) onEvent(name, JSON.parse(data));
    }
  }
}

$("new").onclick = () => newSession().catch((e) => onEvent("error", { status: "", title: "", detail: e.message }));
$("user").onchange = () => newSession().catch(() => {});
$("ask").onsubmit = async (e) => {
  e.preventDefault();
  $("send").disabled = true;
  $("answer").textContent = ""; $("answer").classList.remove("error"); $("activity").innerHTML = ""; $("stats").textContent = "";
  $("feedback").hidden = true;
  try {
    if (!sessionId) await newSession();
    await run($("message").value);
  } catch (err) {
    $("answer").classList.add("error"); $("answer").textContent = String(err);
  } finally { $("send").disabled = false; }
};

const fail = (e) => { $("feedback-status").textContent = String(e); };
$("up").onclick = () => sendFeedback(true).catch(fail);
$("down").onclick = () => sendFeedback(false).catch(fail);

call("/v1/info").then((i) => { $("info").textContent = `v${i.version} · ${i.model} · prompt ${i.prompt}`; })
  .catch((e) => { $("info").textContent = String(e); });
newSession().catch((e) => { $("session").textContent = String(e); });
