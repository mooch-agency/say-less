# Results: total words becomes the headline; formatting via examples, not rules

Session of 2026-07-25.

## 1. Count code

Prose-only counting (`prose_words`) was hiding real wins and, on one prompt,
inverting the result. On "our Docker image is 2.1GB":

| | prose words | total words |
|---|---|---|
| Default | 74 | 183 |
| Say Less | **82** | **104** |

Default spent its length on a fenced Dockerfile; Say Less put commands inline
and offered specifics on request. Stripping code scored Say Less as *longer* on
a prompt where it produced half the reading. Code is reading load, so it counts.

`total_words` is now the headline everywhere (spot.py, compare.py,
serve_compare.py, the artifact, README, chart). `prose_words` is kept as a
diagnostic and is still the safer thing to *tune* against: a style optimised to
minimise code learns to describe fixes instead of showing them, which breaks the
style's own "give the fix, not a pointer to it".

## 2. Paired numbers (10 prompts x 3 runs, hermetic, sonnet)

| metric | Default median | Say Less median | overall cut |
|---|---|---|---|
| total words | 129 | 42 | 63% |
| prose words | 99 | 35 | 63% |

Say Less shorter on **10/10** prompts, per-prompt cut 41% to 86% (median 67%),
paired delta -84.2 words (sd 50.5). Under prose counting the worst prompt was
-11% (a loss); under total words every prompt is a win.

## 3. Formatting: v3.3 refuted, v3.4 ships

Goal: stop dense multi-sentence paragraphs (a wall a skimmer skips). Metric:
`walls`, the count of replies containing a paragraph of 3+ sentences, over 13
prompts x 2 runs.

| version | median total words | walls | verdict |
|---|---|---|---|
| v3.2 (baseline) | 39-42 | 6-7 / 26 | - |
| v3.3: added a "break the text up" rule | 56 | 3 / 26 | **rejected**, +14 words |
| v3.4: reshaped examples + one clause | 40 | **1 / 26** | **shipped**, +3 words |

v3.3 repeats the scope-hook failure: an added prescriptive rule lengthened
output. v3.4 changes the examples to show blank-line separated paragraphs and
adds a single clause to the existing style line. Near-total fix (7 walls -> 1)
for a +3.2 word mean (median +1, sd 5.8), i.e. inside noise on length.

Consistent with the standing finding: **examples set the shape, rules inflate it.**
