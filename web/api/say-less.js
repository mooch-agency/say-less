// Vercel serverless function: run one prompt through Claude twice, side by side.
// Arm A gets no system prompt; arm B gets the Say Less style. Everything else is
// identical, so the only variable is the style. Both streams are proxied back
// over one SSE connection, each token tagged with its arm. The API key stays
// server-side.
//
// Conventions follow api/rewrite.js in this repo: raw fetch (no SDK dependency),
// SSE, and the same cost controls — word cap, conservative max_tokens,
// best-effort per-instance IP rate limit, origin check, kill switch.
//
// System prompt is api/say-less-system.md, generated from the style file by
// benchmark/sync_web_prompt.py in the say-less repo. Regenerate when the style
// changes; do not hand-edit it.

const fs = require("fs");
const path = require("path");

const MODEL = process.env.SAY_LESS_MODEL || "claude-opus-4-8";
const MAX_TOKENS = 1500;            // ceiling per arm; replies are far shorter
const WORD_CAP = 200;               // prompts are questions, not documents
const RATE_PER_MIN = 6;             // 2 model calls per request, so half rewrite's
const RATE_PER_DAY = 40;
const ALLOWED_HOSTS = ["mooch.agency", "localhost", "127.0.0.1"];

// Lazy + cached, so a missing/unbundled prompt returns a clean error from the
// handler rather than throwing at module load (which 500s every request).
let _system = null;
function loadSystem() {
  if (_system === null) {
    _system = fs.readFileSync(path.join(__dirname, "say-less-system.md"), "utf8");
  }
  return _system;
}

// Best-effort in-memory limiter. Resets when the instance recycles, so it stops
// casual loops but isn't durable. The hard cost guards are the word cap,
// max_tokens, the Anthropic spend ceiling, and the kill switch.
const hits = new Map();
function rateLimited(ip) {
  const now = Date.now();
  const rec = hits.get(ip) || { min: [], day: [] };
  rec.min = rec.min.filter((t) => now - t < 60_000);
  rec.day = rec.day.filter((t) => now - t < 86_400_000);
  if (rec.min.length >= RATE_PER_MIN || rec.day.length >= RATE_PER_DAY) {
    hits.set(ip, rec);
    return true;
  }
  rec.min.push(now);
  rec.day.push(now);
  hits.set(ip, rec);
  return false;
}

function originOk(req) {
  const src = req.headers.origin || req.headers.referer || "";
  if (!src) return true; // non-browser clients (curl) aren't the threat; cost is
  let host;
  try { host = new URL(src).hostname; } catch { return false; }
  return (
    ALLOWED_HOSTS.includes(host) ||
    host.endsWith(".mooch.agency") ||
    host.endsWith(".vercel.app")   // preview deployments
  );
}

function readBody(req) {
  if (req.body && typeof req.body === "object") return Promise.resolve(req.body);
  if (typeof req.body === "string") {
    try { return Promise.resolve(JSON.parse(req.body || "{}")); } catch { return Promise.resolve({}); }
  }
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      try { resolve(JSON.parse(raw || "{}")); } catch { resolve({}); }
    });
    req.on("error", () => resolve({}));
  });
}

// One arm: stream Claude and push each text delta to `onToken`. Both arms use
// identical settings (model, max_tokens, thinking, effort) so the system prompt
// is the only difference between them. Adaptive thinking is on deliberately:
// with thinking off, Opus can spill reasoning into the visible reply, which
// would inflate the no-style arm and make the comparison unfair.
async function runArm({ arm, key, system, prompt, onToken }) {
  const body = {
    model: MODEL,
    max_tokens: MAX_TOKENS,
    stream: true,
    thinking: { type: "adaptive" },
    output_config: { effort: "low" },
    messages: [{ role: "user", content: prompt }],
  };
  if (system) body.system = system;

  const upstream = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(body),
  });

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    console.error("anthropic error", arm, upstream.status, detail.slice(0, 500));
    throw new Error("upstream");
  }

  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const events = buf.split("\n\n");
    buf = events.pop() || "";
    for (const ev of events) {
      const line = ev.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const payload = line.slice(5).trim();
      if (!payload || payload === "[DONE]") continue;
      let obj;
      try { obj = JSON.parse(payload); } catch { continue; }
      // Only text deltas. Thinking deltas are a separate delta type and are
      // deliberately not forwarded: the demo compares replies, not reasoning.
      if (obj.type === "content_block_delta" && obj.delta && obj.delta.type === "text_delta") {
        if (obj.delta.text) onToken(obj.delta.text);
      }
    }
  }
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.statusCode = 405;
    return res.end("Method not allowed");
  }
  if (process.env.SAY_LESS_DISABLED === "1") {
    res.statusCode = 503;
    return res.end("The demo is paused. Back shortly.");
  }
  if (!originOk(req)) {
    res.statusCode = 403;
    return res.end("Forbidden");
  }

  const ip = (req.headers["x-forwarded-for"] || "").split(",")[0].trim() || "anon";
  if (rateLimited(ip)) {
    res.statusCode = 429;
    return res.end("Slow down a moment, then try again.");
  }

  const { prompt } = await readBody(req);
  if (!prompt || !prompt.trim()) {
    res.statusCode = 400;
    return res.end("Ask a question first.");
  }
  const words = prompt.trim().split(/\s+/).length;
  if (words > WORD_CAP) {
    res.statusCode = 413;
    return res.end(`Keep it under ${WORD_CAP} words. That was ${words}.`);
  }

  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) {
    res.statusCode = 500;
    return res.end("Server missing API key.");
  }
  let system;
  try { system = loadSystem(); }
  catch (e) { res.statusCode = 500; return res.end("Server misconfigured."); }

  res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
  res.setHeader("Cache-Control", "no-cache, no-transform");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  if (res.flushHeaders) res.flushHeaders();

  res.write(`event: meta\ndata: ${JSON.stringify({ model: MODEL })}\n\n`);

  const send = (arm, text) =>
    res.write(`data: ${JSON.stringify({ arm, t: text })}\n\n`);

  // Both arms run concurrently and interleave on one connection, so the two
  // columns fill at their real relative speeds.
  const arms = [
    runArm({ arm: "default", key, system: null, prompt: prompt.trim(),
             onToken: (t) => send("default", t) })
      .then(() => res.write(`event: armdone\ndata: ${JSON.stringify("default")}\n\n`)),
    runArm({ arm: "sayless", key, system, prompt: prompt.trim(),
             onToken: (t) => send("sayless", t) })
      .then(() => res.write(`event: armdone\ndata: ${JSON.stringify("sayless")}\n\n`)),
  ];

  try {
    await Promise.all(arms);
  } catch (e) {
    res.write(`event: error\ndata: ${JSON.stringify("That run failed. Try again.")}\n\n`);
    return res.end();
  }
  res.write("event: done\ndata: end\n\n");
  res.end();
};
