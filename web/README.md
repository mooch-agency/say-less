# Say Less, as a web page

A live demo: type a question, Claude answers it twice side by side. Left gets no
system prompt, right gets the Say Less style. Same model, same settings, both
streaming at once.

Built to drop into [mooch.agency](https://mooch.agency), whose `api/rewrite.js`
this follows closely: raw `fetch` (no new dependency), SSE, and the same cost
controls. It runs standalone on any Vercel project too.

## Deploy into mooch.agency

```bash
cp web/say-less.html            ../mooch.agency/say-less.html
cp web/api/say-less.js          ../mooch.agency/api/say-less.js
cp web/api/say-less-system.md   ../mooch.agency/api/say-less-system.md
```

Then add the key, once:

```bash
cd ../mooch.agency
printf 'sk-ant-...' | vercel env add ANTHROPIC_API_KEY production
vercel --prod
```

`cleanUrls` is already on, so it serves at `/say-less`. The site's CSP needs no
change: the page uses inline styles and script (both allowed), fetches only
same-origin `/api/say-less` (`connect-src 'self'`), and loads Instrument Serif
from Google Fonts (already allowed).

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Server-side only; never reaches the browser. |
| `SAY_LESS_MODEL` | `claude-opus-4-8` | Model for both arms. |
| `SAY_LESS_DISABLED` | unset | Set to `1` to pause the demo and return 503. |

## Cost controls

A public endpoint that calls a model is a public endpoint that spends money.
Guards, in order:

- **Origin check** — browser requests must come from mooch.agency or a preview.
- **Rate limit** — 6/min and 40/day per IP, best-effort per warm instance.
- **Prompt cap** — 200 words, rejected before the API is called.
- **`max_tokens` 1500** per arm, and `effort: low`.
- **Kill switch** — `SAY_LESS_DISABLED=1`.

Two model calls per request, so budget double a normal demo. The rate limit is
in-memory and resets when the instance recycles: it stops casual loops, not a
determined one. Set a spend limit in the Anthropic console as the real backstop,
and move the limiter to Vercel KV if it ever gets abused.

## Fairness

Both arms send an identical request body, differing only in `system`. The test
asserts this, so an accidental change to one arm fails the build rather than
quietly skewing the demo.

Adaptive thinking is on for both. With thinking off, Opus can spill reasoning
into the visible reply, which would pad the no-style arm and flatter Say Less.

Note the left arm is **Claude with no system prompt**, which is not the same as
Claude Code's default (that ships its own system prompt). The repo's headline
benchmark numbers measure Claude Code; this page measures the style in isolation.

## Tests

```bash
node web/test_say_less.js
```

Stubs the Anthropic endpoint, so it is free and offline. Covers the guards, the
SSE contract between server and page (the page's parser is duplicated in the
test, so protocol drift on either side fails), thinking-delta suppression, and
the both-arms-identical check.

## Keeping the prompt in sync

`api/say-less-system.md` is generated. After editing the style, run:

```bash
python3 benchmark/sync_web_prompt.py
```
