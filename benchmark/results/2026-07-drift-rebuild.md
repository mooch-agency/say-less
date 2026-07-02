# Results: rebuilding the style for persistence

The experiment behind the 2026-07 rewrite of `say-less.md`. Question: find
"say less" instructions that stay terse *consistently* (every reply) and
*persistently* (across a long session), and prove it. Raw result JSONs are
gitignored (regenerable); the numbers that matter are here.

## Harnesses

- `ab_style.py` — single-turn. Style files as system prompts; prose words + an
  LLM completeness judge (0-100). Catches a terser style that drops content.
- `drift_session.py` — multi-turn. A fixed 16-turn conversation replayed through
  `claude -p --resume` under the real output style, so the model sees its own
  earlier replies and context grows. The only harness that measures drift.
- Prompts in the drift conversation and `clean_prompts.txt` are held out from
  every style's few-shot examples, so no style wins a turn by copying itself.

## The finding: drift is Opus-specific

`drift_session.py`, 16-turn sessions. Sonnet (3 trials): the old style held
~56 prose words/reply, flat-to-falling (-10% first half to second); default
Claude climbed +23%. **Sonnet does not drift.** Opus does, badly, and a plain
terseness prompt doesn't stop it.

## Variant bake-off (Opus, pooled over the runs below)

Pooled across three Opus runs (2+3+4 trials) on the held-out conversation.
`em/reply` = em dashes per reply; `em-rate` = fraction of replies with >=1;
`compl` = completeness on checkable turns (n samples).

| style  | trials | avg words | 2nd-half | drift% | em/reply | em-rate | compl (n) |
|--------|-------:|----------:|---------:|-------:|---------:|--------:|----------:|
| Default        | 2 | 230.8 | 278.6 | +52.2 | 2.72 | 0.62 | 55.0 (6)  |
| Say Less (old) | 9 |  89.9 | 108.3 | +51.5 | 1.68 | 0.58 | 81.0 (27) |
| sl-v1          | 5 |  92.4 | 106.7 | +36.5 | 1.43 | 0.44 | 81.0 (15) |
| sl-v2          | 5 |  88.9 | 100.7 | +30.6 | 0.86 | 0.26 | 91.3 (15) |
| **sl-v3**      | 7 |  84.4 |  97.9 | +38.1 | 0.66 | 0.23 | 87.0 (21) |
| sl-v4          | 4 |  91.6 | 106.2 | +37.9 | 1.73 | 0.52 | 95.0 (12) |

What each variant tested (all positive-spined + compressed vs the old ban list):

- **sl-v1** — positive spec, no self-check. Cut drift, but no content guard, so
  completeness stayed low (81) with genuine catastrophic misses (judge scores of
  3 and 4 on some checkable turns).
- **sl-v2** — + a self-check ("reread, cut restatements/hedges/openers"). Best
  drift (+30.6) and completeness (91.3), but the reread didn't name em dashes,
  so it barely helped them (0.86/reply).
- **sl-v3** — self-check that *names em dashes* and *protects content* ("keep
  every step, caveat, number, required item"). Fewest em dashes (0.66/reply,
  0.23 rate), tersest overall and tersest late-session, completeness 87.
- **sl-v4** — sl-v3 + an anti-anchoring line ("length is set by this answer, not
  earlier replies"). No drift gain, em dashes got worse. Dropped.

Note: single-run em-dash totals are noisy (sl-v3 read 6 then 68 across two
runs). Pool >=5 sessions and normalize per reply before trusting the metric.

## Decision: sl-v3

sl-v3 beats or ties the old style on every axis with good sample sizes:
tersest (84.4 avg, 97.9 late), ~60% fewer em dashes (1.68 -> 0.66/reply), ~26%
less drift (+51.5 -> +38.1), higher completeness (81 -> 87). Its slightly higher
drift% than sl-v2 is a small-base ratio artifact: it has the lowest absolute
word count throughout. The load-bearing change is the closing self-check; naming
em dashes in it is what tames Opus's habit.

## Single-turn completeness (ab_style, Sonnet, 5 trials, held-out prompts)

Confirms sl-v3 keeps decisions complete, and settles what the pending edit did.

| style   | avg words | completeness | monorepo | msg-queue |
|---------|----------:|-------------:|---------:|----------:|
| HEAD (committed)     | 86.8 | 96.3 | 84.8 | 92.8 |
| working (pending)    | 78.1 | 94.5 | 76.6 | 80.8 |
| sl-v2                | 86.2 | 97.7 | 93.4 | 95.0 |
| **sl-v3**            | 93.5 | 98.4 | 97.4 | 94.4 |

The pending edit was terser but dropped decision completeness (monorepo 85->77,
message-queue 93->81). sl-v3's "give the reasons that change the decision" rule
restores it (77->97, 81->94) at the highest overall completeness. sl-v3 is a bit
wordier single-turn, but that is content restoring completeness, and multi-turn
it is the tersest, so it does not run away.

## Honest limits

- Drift is reduced, not eliminated (+38% remains on Opus).
- Em dashes drop to ~23% of replies, not 0. Opus is em-dash-prone regardless.
- Completeness and em-dash counts are noisy at n<5; treat single runs as
  directional and pool.

## Regenerate

```bash
# multi-turn drift on the model that drifts
python3 benchmark/drift_session.py "Default" "Say Less" --model opus --trials 4 --judge --workers 3

# single-turn terseness + completeness on held-out prompts
python3 benchmark/ab_style.py OLD.md say-less.md --prompts benchmark/clean_prompts.txt --trials 5
```

Run each in a subscription session (the harnesses strip `ANTHROPIC_API_KEY`).
Keep `--workers` at ~3: more thrashes the CLI cold-start and runs slower.
