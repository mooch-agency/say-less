# Results: the baseline was contaminated, and one of my explanations was wrong

Session of 2026-07-25. Triggered by Tahi asking whether the "Default" arm was
really default, or was still picking up user-scope brevity rules.

## The contamination

It was. Every headless run in this repo's history loaded user scope, including
`~/.claude/CLAUDE.md`, which carries its own verbosity guidance ("Always aim to
be clear, concise and compelling", "No running commentary").

Proof, not inference: the probe prompt "What is your name?" returned
**"I am moochbot"** with no flags, and **"I am Claude"** with
`--setting-sources project`. The persona file was in context the whole time.

## The fix

`claude_turn` now passes `--setting-sources project`, so only project-scope
settings load: no user CLAUDE.md, no user-scope plugins, no user settings.json.
This also hides user-installed output styles, so `run_session` (and
`compare.py`) copy the style file into `<cwd>/.claude/output-styles/` per run.
It works on a subscription; no API key needed.

Second contaminant found the same day: the Say Less **plugin** is installed
user-scope with `force-for-plugin: true`, so it was overriding the Default arm
too. A first data run showed Default at median 24 words. Anything measuring a
Default baseline must run hermetically or with the plugin disabled.

## 2x2 paired batch (the real numbers)

4 arms x 10 prompts x 3 trials = 120 calls, all in one batch, all hermetic.
`/tmp/paired_2x2.json`, generator in the session log.

| arm | median | mean |
|---|---|---|
| Default | 70 | 91 |
| Default + CLAUDE.md | 82 | 98 |
| Say Less | 31 | 41 |
| Say Less + CLAUDE.md | 31 | 38 |

Stock vs Say Less, hermetic: **55% fewer words by total, 56% by median.** Best
single prompt 86%. Not a clean sweep: on 2 of 10 prompts Say Less came out
longer, and on the 1-word MongoDB-port prompt the percentage is meaningless
(tiny denominator).

## What I got wrong

I claimed the user's CLAUDE.md had been *shortening the Default arm*, so the
true gap would be wider. The paired test says no:

| arm | CLAUDE.md effect (paired, per prompt) | se | mean/se |
|---|---|---|---|
| Default | +7.0 words | 16.6 | +0.42 (noise) |
| Say Less | **-3.3 words** | 1.5 | -2.17 (real, small) |

On Default it does nothing measurable, and the sign is the opposite of my
claim. On Say Less it does shorten replies by ~3 words, which confirms Tahi's
reading: with the style *and* CLAUDE.md both pushing for brevity, Say Less was
double-enforced. Remove CLAUDE.md and it runs slightly longer. That is the only
part of the earlier story that survived.

Method note for the next round: the unpaired single-run comparison that
produced the wrong claim (Default 84 vs 92 across two separate runs) is exactly
the trap `2026-07-drift-persistence-hook.md` warned about. Default's per-prompt
spread is enormous (mean 91 vs median 70, paired sd 52), so single runs cannot
resolve effects of this size. Pair, and use 3+ trials.

## Effect on published numbers

- README and chart: 59%/81% -> **55% average, 86% best**, median 70 -> 31.
- Comparison artifact: summary restated from the 3-trial batch, with a note
  that Say Less is occasionally longer on short factual answers.
- Everything in `benchmark/results/` before this date used user scope in *all*
  arms. Style-vs-style comparisons still stand (the contamination was equal and
  the harness docstring flagged it), but any absolute Default figure in those
  write-ups is understated and should not be quoted on its own.
