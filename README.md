# Say Less

A low-verbosity output style for Claude Code. Full reasoning, terse replies.

Claude keeps all its coding ability and works at full depth. Only the final reply changes: shortest clear answer, plain and direct, none of the AI padding, and it stays that way across a long session instead of creeping back to verbose.

## What it does

- Leads with the answer, one word where that's enough ("5432.").
- States the reasons that actually swing a decision, so terse never means incomplete.
- Cuts the patterns that mark text as AI-written: preamble, hedging, comparative antithesis ("Not X. Y."), sycophancy, promotional adjectives, warm closes, em dashes.
- Keeps code, commands, and exact values verbatim.
- Ends with a one-line reread ("cut restatements, hedges, em dashes; keep every required item") that fights drift and catches em dashes.

The style is a short positive spec first (what a good reply looks like), then a compact list of padding to cut, then examples. That order is deliberate: see [benchmark/RESEARCH.md](benchmark/RESEARCH.md).

## How it holds up

Two things matter: is a single reply terse *and complete*, and does it *stay* terse over a whole session.

**Single reply** (`benchmark/ab_style.py`, headless, prose words + an LLM completeness judge). On held-out prompts the style answers at ~98/100 completeness while cutting words, and it keeps decisions complete: on "monorepo vs separate repos" it scores 97 vs 77 for a terser-but-thinner wording. Terser only counts when completeness holds; this measures the trade.

**Across a session** (`benchmark/drift_session.py`, a fixed 16-turn conversation replayed through `claude -p --resume`, so the model sees its own earlier replies and the context grows). This is where verbosity creeps back. Findings:

- **Sonnet doesn't drift.** With the style on, prose sits at ~56 words/reply and is flat-to-falling over the session; default Claude climbs +23%.
- **Opus drifts hard, and a plain terseness prompt doesn't stop it.** Default Opus climbs +52% first half to second; a prohibition-style "be terse" list climbed +51% (no better) and put an em dash in ~58% of replies.
- **The shipped style cuts that.** Over the same Opus sessions: drift +38%, em dashes down to ~23% of replies, completeness up (81 to 87), and the lowest absolute word count late in the session. The load-bearing change is the closing reread step, which also catches em dashes Opus otherwise leaks.

Numbers are pooled over 7-9 sessions x 16 turns per style on `claude-opus`; regenerate with the commands below. Drift is model-dependent, so test on the model you actually run.

## Install

```bash
ln -sf "$(pwd)/say-less.md" ~/.claude/output-styles/say-less.md
```

Then turn it on: `/config` -> Output style -> Say Less, or add `"outputStyle": "Say Less"` to `~/.claude/settings.json`. Takes effect in a new session.

`keep-coding-instructions: true` in the frontmatter means all default coding behaviour stays; only the prose style changes.

## How output styles work

The style body is appended to the system prompt and re-sent every turn, and Claude Code fires its own periodic reminders to stay on-style ([docs](https://code.claude.com/docs/en/output-styles)). So it isn't injected once and left to decay. The reminder cadence is undocumented, and the drift numbers above show it isn't enough on Opus by itself, which is why the style leads with one quotable directive and ends with a self-check the reminder can reinforce.

## Benchmarks

Three harnesses, all headless (`claude -p`, subscription, no API key), prose-word counts (code/commands/link URLs excluded, since padding lives in prose):

- `benchmark/ab_style.py A.md B.md [...]` — single-turn: compares style files as system prompts, reports prose words + completeness.
- `benchmark/drift_session.py "Default" "Say Less" [...]` — multi-turn persistence on the real output style (selected via `--settings outputStyle`); reports per-turn words, first vs second half drift, em-dash rate, and completeness. `--model opus` for the case that drifts.
- `benchmark/position_test.py` — API-based placement test (rules in the system prompt vs re-injected each turn). Needs `ANTHROPIC_API_KEY`.

`benchmark/RESEARCH.md` explains why the style is shaped the way it is, with sources.

## Status

Dogfooding. Built and validated, not yet packaged as a plugin or published.
