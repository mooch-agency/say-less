# Results: re-validated the headline number after the how-to-rule fix, 63% -> 71%

Session of 2026-07-25, ahead of the private beta. The published 63%
average / 86% best claim was measured before the how-to-rule commit
(explain/how-to prompts got a "single best move, not a ranked list" rule;
see that commit's message for the Opus/Sonnet spot deltas). Needed a fresh
paired run before shipping the numbers to a wider audience.

## Method

`benchmark/paired.py` (new script, written this session): 10 held-out
prompts (spot.py's set) x 3 trials x 2 arms, hermetic
(`--setting-sources project`), `claude-sonnet-5`, `total_words`. Same
methodology as the original 63%/86% figures
(`2026-07-total-words-and-formatting.md`); the only thing that changed is
the style file. Per prompt, each arm's 3 trials are collapsed to a median
before pairing, which is what the earlier hermetic-baseline finding says a
noisy Default arm requires.

The paired-batch generator behind the original numbers wasn't a committed
script (results doc says "generator in the session log"), so this number
previously couldn't be reproduced with one command. `paired.py` fixes that;
`python3 benchmark/paired.py` reruns it.

## Result

| metric | Default | Say Less |
|---|---|---|
| median | 171 | 50 |
| mean | 170.6 | 49.4 |

Shorter on **10/10** prompts. Per-prompt cut range **61% to 80%** (was 41%
to 86%). Overall (median of medians): **71%** (was 63%).

| prompt | default | say less | cut |
|---|---|---|---|
| MongoDB port | 5 | 1 | 80% |
| UUIDs vs integers | 234 | 56 | 76% |
| Async loop bug | 79 | 31 | 61% |
| NoneType traceback | 125 | 40 | 68% |
| Soft-delete diff review | 232 | 62 | 73% |
| Eventual consistency | 332 | 98 | 70% |
| Docker image size | 213 | 75 | 65% |
| Redis vs Memcached | 144 | 31 | 78% |
| Slow SQL (DATE() wrap) | 179 | 46 | 74% |
| Test private methods | 163 | 54 | 67% |

## Why it moved

The floor moved up more than the ceiling moved down: worst case went from
41% to 61%. The two prompts most likely to have been the old floor are
exactly the shapes the how-to rule targeted (Docker's ranked-list overflow,
eventual consistency's explain-shaped answer) — both land mid-pack here
(65%, 70%), not at the bottom. Not a controlled before/after (the per-prompt
numbers behind the old 41%/86% weren't preserved, only the aggregate), so
this is the best available account, not a proven causal claim.

One caveat carried forward, not resolved by this run: Default's per-prompt
variance is documented as large (paired sd ~52 in
`2026-07-hermetic-baseline.md`). This run used the same 3-trial-per-prompt
median as the numbers it replaces, so it's at the same confidence level as
every previously published figure here, no better and no worse. More trials
would tighten it further if the number needs to survive more scrutiny than
a private beta.

## Effect on published numbers

- README, marketplace.json, plugin.json: 63%/86% -> **71%/80%**.
- `words-per-reply.svg`: 129/42 -> **171/50**.
- INSTALL.md's Default reference figure: ~130 -> **~170**.
