# Why the style is shaped the way it is

Notes behind the design, from primary sources. The problem we're solving isn't
"can a prompt make one reply terse" (easy) but "does terseness *hold* across a
long session" (hard). Adherence to any style instruction decays as a
conversation grows, mainly because the model imitates its own earlier, longer
replies. These are the levers that fight that decay, ranked by expected impact.

## Levers (ranked)

1. **Re-inject the rule near the latest turn.** Biggest persistence lever.
   Restating requirements late in a chat recovers most multi-turn degradation
   (Laban et al., *LLMs Get Lost in Multi-Turn Conversation*, 2025,
   arxiv.org/abs/2505.06120: a recap turn lifted GPT-4o 59.1→76.6). Claude Code
   already does this: "All output styles trigger reminders for Claude to adhere
   to the output style instructions during the conversation"
   (code.claude.com/docs/en/output-styles). Implication: keep the **core
   directive to one short, quotable line** the reminder can reinforce.

2. **Frame positively, not as prohibitions.** Anthropic, for verbosity
   specifically: "Positive examples ... tend to be more effective than negative
   examples or instructions that tell the model what not to do"
   (Opus 4.8 prompting guide). Negation reliability doesn't improve with scale
   and can worsen (Jang et al. 2022, arxiv 2209.12711; Truong et al. 2023,
   arxiv 2306.08189). A *specific* ban ("no em dashes") is fine; a *vague* one
   ("don't ramble") fails. So: lead with a positive spec, keep concrete bans as
   a compact secondary reference.

3. **Motivate the load-bearing rules.** "Claude is smart enough to generalize
   from the explanation" (Anthropic best-practices). Keep the "why" (say less,
   let the reader pull more) so the model extends it to cases the rules don't
   list.

4. **Primacy first, echo last.** Instructions are followed most reliably when
   they come first (IFScale, Jaroslawicz et al. 2025, arxiv 2507.11538); the
   middle is weakest (Liu et al., *Lost in the Middle*, TACL 2024, arxiv
   2307.03172). Put the one rule that matters most at the very top; echo its
   essence at the very end.

5. **Keep the rule set small.** Adherence drops from ~100% at 10 instructions to
   <69% at 500 (IFScale). A 14-item co-equal ban list works against itself;
   collapse to a few principles with bans as examples under them.

6. **Length budget as a ceiling, not a target.** Models undershoot length
   *targets* but honor short *caps* (LIFEBENCH, Zhang et al. 2025, arxiv
   2505.16234). Use "fewest sentences that answer," not "write N sentences."

7. **Terse, low-markdown examples.** "Examples are one of the most reliable ways
   to steer output" (Anthropic). Prompt style bleeds into output style, so
   write the style file itself tersely.

8. **Self-check only if bound to a countable criterion.** Self-Refine helps when
   feedback is specific (Madaan et al. 2023, arxiv 2303.17651); open-ended
   self-correction *degrades* output (Huang et al., ICLR 2024, arxiv
   2310.01798). A "cut restatements/hedges/openers" check may help; a vague
   "make sure that was concise" hurts and costs latency. Tested as v2.

## What not to do

- Rely on one strong opening instruction to persist (it decays).
- Build the style mainly from prohibitions.
- Pile up many co-equal rules.
- Bury the key rule mid-prompt.
- Add an open-ended "double-check you were concise" step.
- Over-force with CRITICAL/ALWAYS/NEVER caps (Anthropic: aggressive language now
  over-triggers; "you can use more normal prompting").
- Set a fixed length target (undershooting is the failure mode).

## How we test it

- `ab_style.py` — single-turn wording: prose words + an LLM completeness judge,
  so a terser style that drops required content shows as lower completeness, not
  a false win.
- `drift_session.py` — the persistence test: a fixed multi-turn conversation via
  `claude -p --resume` under the real output style, measuring per-turn words and
  first-half vs second-half drift. This is the one that reflects the levers above.
