# Results: delivery channel barely matters for drift (output style vs persona)

Question: does the SAME Say Less rule text hold terseness differently when
delivered as an output style (system prompt + Claude Code's built-in adherence
reminders) vs as persona memory (the `# claudeMd` block: hard "MUST follow"
framing, no re-injection)?

## Setup

- `drift_session.py` gained a `SayLess-persona` condition: the say-less.md body
  (frontmatter stripped) written as `CLAUDE.md` into each session's isolated
  temp cwd, output style set to Default. Byte-identical words, other channel.
  Project CLAUDE.md is a position-faithful proxy for `~/.claude/PERSONA.md`
  (both land in the claudeMd context block); a global symlink would leak into
  every condition.
- One paired batch: Default / Say Less (output style) / SayLess-persona.
  Opus, 16-turn default conversation, 5 trials, --judge.
- Hypothesis going in: persona drifts MORE (no re-injection reminder).

## Result: within noise on every drift metric. Hypothesis refuted.

`drift_opus_persona.json`, read with `analyze_drift.py --baseline "Say Less"`:

| channel | 2nd-half | gap | slope | drift% | em | compl |
|---|---|---|---|---|---|---|
| Default | 78.9 | 20.6 | 2.51 | 35.3 | 33 | 78.7 |
| Say Less (output style) | 69.8 | 14.2 | 1.80 | 25.6 | 0 | 65.3 (5 judge 0s; ~98 excl.) |
| SayLess-persona (CLAUDE.md) | 67.5 | 13.8 | 1.77 | 25.7 | 0 | 92.9 (0 zeros) |

Paired deltas persona vs style (noise unit ~0.9 words): d_gap −0.4,
d_slope −0.03, d_drift% +0.1. The persona's −2.3 2nd-half words is a uniform
general-terseness shift (1st half −1.8 too), not reduced drift. Em dashes 0 in
both. Completeness fine in both (the style's 65.3 is judge misfires).

## Reading

- Claude Code's built-in output-style adherence reminder buys **no measurable
  persistence** over a once-injected CLAUDE.md on Opus. Consistent with round 2
  (results/2026-07-drift-persistence-hook.md): that reminder is too weak; the
  explicit UserPromptSubmit hook is what moves drift.
- The claudeMd block's aggressive framing ("OVERRIDE... MUST follow exactly")
  buys nothing over the style's soft framing. Framing strength is not a lever
  (matches RESEARCH.md's over-forcing note).
- Practical: run Say Less through either channel; pick on ergonomics. The
  drift lever remains the re-injection hook, which composes with both.

## Caveats

- One 5-trial batch, 16-turn Q&A shape only; the 28-turn coding shape not run.
- Proxy caveat: PERSONA.md is @-imported into the user CLAUDE.md; the test used
  a project CLAUDE.md. Same block, same turn-1 position; import indirection
  untested but implausible as a drift lever given the above.
