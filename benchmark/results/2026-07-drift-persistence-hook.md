# Results: the persistence lever is a re-injection hook, not more prompt

Follow-up to [2026-07-drift-rebuild.md](2026-07-drift-rebuild.md). That round
shipped sl-v3 (positive spec + closing self-check) and left Opus drift at ~+37%.
This round asked: what actually pushes it lower, across session types, lengths,
and inputs? A self-critiquing multi-agent workflow explored prompt, config,
context-management, external-research, and measurement lenses, then converged and
adversarially audited its own recommendation. Two things came out of it: a
corrected test protocol, and the finding that the remaining lever is not in the
prompt at all.

## Corrected protocol (from the audit)

The prior round compared against frozen single-run constants and gated on
`drift_pct` and a raw completeness mean. All three are traps:

- **Pair the baseline in the same batch.** sl-v3 run-to-run swung em dashes
  68→6 and completeness 82→93. A candidate judged against a frozen number can
  win or lose on the baseline's noise alone. Every run below re-runs the
  baseline in the same batch.
- **Judge on second-half absolute words + slope + the first→second gap, never
  `drift_pct` alone.** `drift_pct` is a ratio on a small base: a change that
  trims *every* reply leaves it flat while genuinely helping (this is exactly how
  sl-v4 looked). [analyze_drift.py](../analyze_drift.py) reports all of them plus
  a kind×half decomposition.
- **Completeness is a trials-trigger, not a hard gate.** It rests on ~18–24
  checkable-turn scores and the judge misfires to 0 on complete answers; one 0
  moves the mean ~4 points. Read `mean_excl_zeros` and eyeball the raw replies.

Noise unit for the stop rule: the baseline's second-half trial-mean SD (~5–11
words depending on batch).

## The prompt lever is plateaued (two refutations)

**sl-v5** — the workflow's rank-1 idea: rewrite the closing self-check as a
numbered pass/fail checklist whose new item 2 is a length-relative, actionable
criterion ("could a reader get the same complete answer in fewer lines? Judge
against the question in front of you, not against anything you wrote earlier").
The actionable-at-send version of the anti-anchoring that sl-v4 asserted as a
declarative body line. Paired vs sl-v3, Opus, 6 trials:

| metric | sl-v3 | sl-v5 | Δ |
|---|---|---|---|
| 2nd-half words | 101.6 | 104.3 | +2.7 (inside ±5.1 noise) |
| drift gap | 26.7 | 30.9 | +4.2 |
| slope | 2.82 | 3.43 | +0.61 |
| em dashes | 60 | 77 | +17 |
| completeness | 86.7 | 76.7 | −10 (mostly judge misfires) |

No improvement on the primary metric (the 2nd-half delta is inside noise), and
the em-dash regression is the sl-v4 failure signature. Together with sl-v4, that
is two independent refutations: **rewriting the static prompt does not move Opus
drift below its floor.** The self-check that drove Say Less→sl-v3 has plateaued.

## The lever that works: recency re-injection via a hook

The external-research lens reframed the problem as a *recall–adherence
dissociation* — late in a session Opus still recalls the terseness rule but stops
applying it, anchored by its own lengthening replies. That predicts the fix is
not more rules but forcing re-application at the newest turn, the one place a
system-prompt style can't reach. Implemented as a `UserPromptSubmit` hook
([say-less-gate.sh](../hooks/say-less-gate.sh)) that, from turn 2 on, injects a
short recency-placed, application-framed, anti-anchoring directive.

Paired sl-v3 vs sl-v3+hook, Opus, 6 trials, same batch (noise unit ±11.1 words):

| metric | style alone | style + hook | Δ |
|---|---|---|---|
| avg prose words | 84.3 | 62.9 | −25% |
| **2nd-half words** | **95.0** | **69.8** | **−25.2 (−26%, >2× noise)** |
| **drift gap (2nd−1st)** | **21.5** | **14.0** | **−7.5 (−35%)** |
| **slope (words/turn)** | **2.62** | **1.77** | **−0.85 (−32%)** |
| em dashes (96 replies) | 114 | 0 | **→ 0** |
| completeness (excl. misfires) | 98.2 | 94.8 | flat, within judge noise |

`drift_pct` only moved 29.2→25.0 because the hook shaved *both* halves — the
small-base ratio artifact the protocol warns about. The real drift signals (the
gap and the slope) both dropped by roughly a third, and late-session verbosity
fell 26%. The kind×half decomposition shows the win is broad and lands on the
drift-prone long-form turns (decision 116→132 becomes 82→82; explain 140→128
becomes 106→82) while `grow` (long code-review turns that legitimately need
words) stays high and completeness holds. The hook makes replies both terser and
flatter: they stop climbing back toward verbose.

Completeness diligence: the low raw means (60/63) are judge misfires — 6–7 of 18
checkable answers scored 0 despite correctly naming every required item
(encapsulation, 1NF/2NF, GET/POST all present). Excluding misfires, 98.2 vs 94.8,
and the hook produced *fewer* zeros. No content regression.

## Robustness across session type and length

The 16-turn mixed-Q&A conversation can't prove the fix holds across session
*type* or *length*, so the harness gained a second shape: a 28-turn
coding/debugging-heavy conversation (`--conversation coding`, +75% length,
`grow` turns dominant), prompts disjoint from every style's examples.

Paired sl-v3 vs sl-v3+hook, Opus, 5 trials, `coding` conversation (noise ±7.9):

| metric | style alone | style + hook | Δ |
|---|---|---|---|
| avg prose words | 101.1 | 59.9 | −41% |
| **2nd-half words** | **121.1** | **72.0** | **−49.1 (−41%, >6× noise)** |
| **drift gap (2nd−1st)** | **40.0** | **24.1** | **−15.9 (−40%)** |
| **slope (words/turn)** | **2.72** | **1.59** | **−1.13 (−42%)** |
| em dashes | 105 | 2 | −103 |
| completeness (excl. misfires) | 94.7 | 95.6 | flat / marginally better |

The win is *larger* on the longer, harder session (2nd-half −41% vs −26% on the
16-turn shape), so it holds across session type and length. `drift_pct` is flat
(+0.9) — again the ratio artifact: the hook shaved both halves proportionally
(1st −41%, 2nd −41%) while the absolute gap dropped 40%.

Completeness diligence (again): the raw mean drops 72.0→53.5, but that is 11 vs 6
judge misfires-to-0 on *terser* answers, not content loss. Every zero-scored hook
reply is complete for its question — "Name the three pillars of observability" →
"Logs, Metrics, Traces"; "List the four SQL isolation levels" → all four in
order; "Name the five SOLID principles" → all five; and "define each" questions
still get full definitions. Excluding misfires, 95.6 vs 94.7 — the hook is
marginally *more* complete. The judge is simply more likely to misfire on a short
answer, which is a harness limitation, not a hook regression.

## Decision

Ship the hook as the persistence lever; keep sl-v3 as the shipped output style
unchanged (sl-v5 rejected). Install and reproduce: [../hooks/README.md](../hooks/README.md).

## Honest limits

- The hook fires on every turn regardless of active output style; global install
  nudges terseness everywhere (fine if that's the standing default, otherwise
  scope it per-project). Per-project via the repo `.claude/settings.json` is safe.
- Completeness is measured on a noisy 18–24-sample judge; the "no regression"
  claim rests on `mean_excl_zeros` + a raw eyeball, not the raw mean.
- Em-dash totals are noisy run-to-run (baseline hit 60 then 114 across batches);
  the hook driving them to exactly 0 is unambiguous, but the baseline level is not.
- Effect sizes are from 5–6 trials. Large and well outside the noise band, but
  not tight confidence intervals.

## Regenerate

```bash
python3 benchmark/drift_session.py "Say Less" "sl-v5" --model opus --judge --trials 6 --out benchmark/drift_opus_v5.json
python3 benchmark/drift_session.py "Say Less" "Say Less+hook" --model opus --judge --trials 6 --out benchmark/drift_opus_hook.json
python3 benchmark/drift_session.py "Say Less" "Say Less+hook" --model opus --judge --trials 5 --conversation coding --out benchmark/drift_opus_hook_coding.json
python3 benchmark/analyze_drift.py <results.json> --baseline "Say Less"
```
