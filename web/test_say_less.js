// Contract test for api/say-less.js. Stubs the Anthropic endpoint, so it runs
// offline and costs nothing, and checks the two things that actually break:
// the request guards, and whether the SSE the handler emits is the SSE the page
// knows how to parse. The page's parser is duplicated here verbatim from
// say-less.html — if the protocol drifts on either side, this fails.
//
//   node web/test_say_less.js

const assert = require("assert");
const path = require("path");

const HANDLER = path.join(__dirname, "api", "say-less.js");

function anthropicSSE(chunks) {
  // Minimal shape of a real Anthropic stream: text deltas plus one thinking
  // delta, which the handler must ignore.
  const frames = [
    'data: {"type":"message_start"}',
    'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"hmm"}}',
    ...chunks.map((c) =>
      "data: " + JSON.stringify({ type: "content_block_delta", delta: { type: "text_delta", text: c } })),
    'data: {"type":"message_stop"}',
  ];
  const body = frames.join("\n\n") + "\n\n";
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(body));
      controller.close();
    },
  });
}

function fakeRes() {
  return {
    statusCode: 200,
    headers: {},
    chunks: [],
    ended: false,
    setHeader(k, v) { this.headers[k] = v; },
    flushHeaders() {},
    write(s) { this.chunks.push(s); return true; },
    end(s) { if (s) this.chunks.push(s); this.ended = true; },
    get output() { return this.chunks.join(""); },
  };
}

function fakeReq(body, { method = "POST", headers = {} } = {}) {
  return { method, headers: { origin: "https://mooch.agency", ...headers }, body };
}

// Verbatim from say-less.html — server and client must agree on this.
function parseSSE(raw) {
  const out = { default: "", sayless: "", meta: null, error: null, done: false };
  for (const chunk of raw.split("\n\n")) {
    const evLine = chunk.split("\n").find((l) => l.startsWith("event:"));
    const dataLine = chunk.split("\n").find((l) => l.startsWith("data:"));
    if (!dataLine) continue;
    const name = evLine ? evLine.slice(6).trim() : "message";
    const rawData = dataLine.slice(5).trim();
    if (name === "done") { out.done = true; continue; }
    let payload;
    try { payload = JSON.parse(rawData); } catch { continue; }
    if (name === "meta") out.meta = payload;
    else if (name === "error") out.error = payload;
    else if (name === "message" && payload.arm) out[payload.arm] += payload.t;
  }
  return out;
}

function countWords(t) {
  return String(t || "").split(/\s+/).filter((w) => /[0-9A-Za-z]/.test(w)).length;
}

let passed = 0;
async function test(name, fn) {
  try { await fn(); console.log("  ok   " + name); passed++; }
  catch (e) { console.log("  FAIL " + name + "\n       " + e.message); process.exitCode = 1; }
}

(async () => {
  process.env.ANTHROPIC_API_KEY = "sk-ant-test-not-a-real-key";
  delete process.env.SAY_LESS_DISABLED;

  console.log("\napi/say-less.js\n");

  // --- guards: each must reject before any upstream call is made ------------
  let upstreamCalls = 0;
  global.fetch = async () => { upstreamCalls++; throw new Error("should not be called"); };

  await test("rejects non-POST with 405", async () => {
    const handler = require(HANDLER);
    const res = fakeRes();
    await handler(fakeReq({ prompt: "hi" }, { method: "GET" }), res);
    assert.strictEqual(res.statusCode, 405);
  });

  await test("rejects a foreign origin with 403", async () => {
    const handler = require(HANDLER);
    const res = fakeRes();
    await handler(fakeReq({ prompt: "hi" }, { headers: { origin: "https://evil.example" } }), res);
    assert.strictEqual(res.statusCode, 403);
  });

  await test("rejects an empty prompt with 400", async () => {
    const handler = require(HANDLER);
    const res = fakeRes();
    await handler(fakeReq({ prompt: "   " }), res);
    assert.strictEqual(res.statusCode, 400);
  });

  await test("rejects an over-long prompt with 413", async () => {
    const handler = require(HANDLER);
    const res = fakeRes();
    await handler(fakeReq({ prompt: "word ".repeat(300) }), res);
    assert.strictEqual(res.statusCode, 413);
  });

  await test("honours the kill switch with 503", async () => {
    process.env.SAY_LESS_DISABLED = "1";
    const handler = require(HANDLER);
    const res = fakeRes();
    await handler(fakeReq({ prompt: "hi" }), res);
    assert.strictEqual(res.statusCode, 503);
    delete process.env.SAY_LESS_DISABLED;
  });

  await test("no guard rejection reached the API", async () => {
    assert.strictEqual(upstreamCalls, 0, `made ${upstreamCalls} upstream calls`);
  });

  // --- happy path: both arms stream, page parses what the server emits ------
  await test("streams both arms and the page can parse them", async () => {
    delete require.cache[require.resolve(HANDLER)];   // reset the rate limiter
    const seen = [];
    global.fetch = async (_url, opts) => {
      const body = JSON.parse(opts.body);
      seen.push(body);
      const isSayLess = Boolean(body.system);
      return {
        ok: true,
        body: anthropicSSE(isSayLess
          ? ["Integer cents.", " Floats round wrong."]
          : ["You should probably", " use integer cents,", " because floats round wrong", " in ways that compound."]),
      };
    };
    const handler = require(HANDLER);
    const res = fakeRes();
    await handler(fakeReq({ prompt: "floats or integer cents?" }), res);

    const parsed = parseSSE(res.output);
    assert.ok(parsed.done, "stream never signalled done");
    assert.strictEqual(parsed.error, null, "unexpected error event: " + parsed.error);
    assert.ok(parsed.meta && parsed.meta.model, "no meta/model event");
    assert.strictEqual(parsed.sayless, "Integer cents. Floats round wrong.");
    assert.ok(parsed.default.startsWith("You should probably"), "default arm text wrong");
    assert.ok(!parsed.default.includes("hmm") && !parsed.sayless.includes("hmm"),
      "thinking deltas leaked into the reply");
    assert.ok(countWords(parsed.default) > countWords(parsed.sayless),
      "word counts did not come through");
  });

  // The whole comparison rests on this one.
  await test("only the system prompt differs between arms", async () => {
    delete require.cache[require.resolve(HANDLER)];
    const bodies = [];
    global.fetch = async (_url, opts) => {
      bodies.push(JSON.parse(opts.body));
      return { ok: true, body: anthropicSSE(["x"]) };
    };
    const handler = require(HANDLER);
    await handler(fakeReq({ prompt: "same question" }), fakeRes());
    assert.strictEqual(bodies.length, 2, "expected exactly 2 upstream calls");
    const plain = bodies.find((b) => !b.system);
    const styled = bodies.find((b) => b.system);
    assert.ok(plain && styled, "expected one arm with a system prompt and one without");
    for (const k of ["model", "max_tokens", "stream", "messages"]) {
      assert.deepStrictEqual(JSON.stringify(plain[k]), JSON.stringify(styled[k]),
        `arms differ on ${k}, which would make the comparison unfair`);
    }
    assert.deepStrictEqual(plain.thinking, styled.thinking, "arms differ on thinking");
    assert.deepStrictEqual(plain.output_config, styled.output_config, "arms differ on effort");
    assert.ok(styled.system.includes("Line 1 is the outcome"), "style prompt not loaded");
  });

  await test("surfaces an upstream failure as an error event", async () => {
    delete require.cache[require.resolve(HANDLER)];
    global.fetch = async () => ({ ok: false, status: 429, text: async () => "rate limited" });
    const handler = require(HANDLER);
    const res = fakeRes();
    await handler(fakeReq({ prompt: "hi" }), res);
    assert.ok(parseSSE(res.output).error, "no error event emitted");
  });

  await test("rate limits a burst from one IP", async () => {
    delete require.cache[require.resolve(HANDLER)];
    global.fetch = async () => ({ ok: true, body: anthropicSSE(["x"]) });
    const handler = require(HANDLER);
    let limited = false;
    for (let i = 0; i < 9; i++) {
      const res = fakeRes();
      await handler(fakeReq({ prompt: "hi" }, { headers: { "x-forwarded-for": "1.2.3.4" } }), res);
      if (res.statusCode === 429) { limited = true; break; }
    }
    assert.ok(limited, "burst was never rate limited");
  });

  console.log(`\n${passed} passed\n`);
})();
