# Say Less

A low-verbosity output style for Claude Code. Full reasoning, terse replies.

Claude keeps all its coding ability and works at full depth. Only the final reply changes: shortest clear answer, plain and direct, none of the AI padding. Keeping it terse across a *long* session (not creeping back to verbose) takes one more piece on Opus: an optional re-injection hook, [below](#holding-it-across-a-session-the-hook).

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

### Holding it across a session (the hook)

The style alone plateaus at ~+37% Opus drift, and sharpening the prompt further doesn't help: two follow-ups (a declarative anti-anchoring line, a numbered self-check) both failed to beat it. The lever that works isn't in the prompt. It's re-injecting the rule at the newest turn, which a system-prompt style can't do and Claude Code's built-in reminder does too weakly on Opus.

`benchmark/hooks/say-less-gate.sh` is a `UserPromptSubmit` hook that, from the 2nd turn on, adds a short recency-placed, application-framed, anti-anchoring nudge ("match the brevity of your first reply; length is set by this question, not your recent replies"). Paired against the style alone on Opus, it cuts **late-session prose words −26% to −41%, the first→second-half drift gap −35% to −40%, the per-turn climb −32% to −42%, and em dashes to ~0**, with no completeness loss, on both a 16-turn Q&A and a 28-turn coding/debugging session. Why it works and how it's measured: [benchmark/results/2026-07-drift-persistence-hook.md](benchmark/results/2026-07-drift-persistence-hook.md). Install it below.

## Install

```bash
ln -sf "$(pwd)/say-less.md" ~/.claude/output-styles/say-less.md
```

Then turn it on: `/config` -> Output style -> Say Less, or add `"outputStyle": "Say Less"` to `~/.claude/settings.json`. Takes effect in a new session.

`keep-coding-instructions: true` in the frontmatter means all default coding behaviour stays; only the prose style changes.

**Persistence hook (recommended for long Opus sessions).** Per-project, it's already wired via this repo's `.claude/settings.json`. To use it everywhere, install it globally:

```bash
mkdir -p ~/.claude/hooks && cp benchmark/hooks/say-less-gate.sh ~/.claude/hooks/ && chmod +x ~/.claude/hooks/say-less-gate.sh
```

Then add the `UserPromptSubmit` hook from [benchmark/hooks/README.md](benchmark/hooks/README.md) to `~/.claude/settings.json`. Note: installed globally it nudges toward terseness every session regardless of the active style, so install globally only if that's your standing default; otherwise keep it per-project.

## How output styles work

The style body is appended to the system prompt and re-sent every turn, and Claude Code fires its own periodic reminders to stay on-style ([docs](https://code.claude.com/docs/en/output-styles)). So it isn't injected once and left to decay. The reminder cadence is undocumented, and the drift numbers above show it isn't enough on Opus by itself. That's the gap the persistence hook fills: a `UserPromptSubmit` hook puts a fresh directive in the newest *user* turn, where it grips harder than a system-prompt reminder the model has learned to skim.

## Benchmarks

Three harnesses, all headless (`claude -p`, subscription, no API key), prose-word counts (code/commands/link URLs excluded, since padding lives in prose):

- `benchmark/ab_style.py A.md B.md [...]` — single-turn: compares style files as system prompts, reports prose words + completeness.
- `benchmark/drift_session.py "Default" "Say Less" [...]` — multi-turn persistence on the real output style (selected via `--settings outputStyle`); reports per-turn words, first vs second half drift, em-dash rate, and completeness. `--model opus` for the case that drifts. `--conversation coding` runs a longer 28-turn coding/debugging session (robustness). A `+hook` suffix on a style name (e.g. `"Say Less+hook"`) runs it with the persistence hook, so one paired batch compares style-alone vs style+hook.
- `benchmark/analyze_drift.py results.json --baseline "Say Less"` — the corrected read-out: second-half absolute words + slope + first→second gap (not `drift_pct` alone, which a general-terseness change games), a kind×half breakdown, and completeness with judge-misfire flags.
- `benchmark/position_test.py` — API-based placement test (rules in the system prompt vs re-injected each turn). Needs `ANTHROPIC_API_KEY`.

`benchmark/RESEARCH.md` explains why the style is shaped the way it is, with sources. `benchmark/results/` holds one dated write-up per experiment round: [2026-07-drift-rebuild.md](benchmark/results/2026-07-drift-rebuild.md) is the bake-off behind the style, and [2026-07-drift-persistence-hook.md](benchmark/results/2026-07-drift-persistence-hook.md) is the round that found the hook.

## Status

Dogfooding. Built and validated, not yet packaged as a plugin or published.
