# Results: scope-budget hook, round 1 — null on small-task reports; workload didn't reproduce the failure

Test of the round-3 hypothesis (RESEARCH.md): residual verbosity is content
selection, worst on task-report turns, and the lever is a structural scope
budget re-injected at recency.

## Setup

- New `report` conversation in drift_session.py: 14 turns, 8 real edit tasks in
  a seeded 2-file workspace (Edit/Write allowed, Bash denied), reports balanced
  4/4 across halves, Q&A interleaved.
- New hook `hooks/say-less-scope.sh` = say-less-gate.sh + a structural scope
  block (outcome in 1-2 sentences, max one list, no headers, no step narration,
  detail behind a named offer), scope firing from turn 1.
- Paired batch: Say Less / +hook / +scopehook. Opus, 4 trials, --judge.
- `drift_opus_report_scope.json`; 0/168 empty replies.

## Result: no scope-hook gain, and the workload is the reason

| condition | avg | 2nd-half | gap | report-kind avg |
|---|---|---|---|---|
| Say Less | 33.8 | 30.7 | −6.3 | 30.4 |
| +hook | 27.1 | 20.8 | −12.8 | 24.2 |
| +scopehook | 27.1 | 23.0 | −8.1 | 22.3 |

- vs +hook (noise unit ~3.7 words): d_report −1.9, d_2nd_h +2.2. Within noise
  both ways. No win.
- Drift is NEGATIVE here: replies shorten across the session in all conditions.
- The headline fact: **style-alone report turns average ~30 prose words.** The
  300-word structured-report failure mode (tables, sections, offers) never
  appeared. Single-file micro-edits give Opus nothing to over-report.

## Reading

The hypothesis is untested, not refuted: scope budgets can't show value where
scope is already minimal. Real verbose reports follow MULTI-STEP work with many
findings (audits, experiments, refactors), where the model chooses how many of
its results to narrate. Round 2 of this test needs heavy-result tasks, e.g.:

- a seeded repo with 6-10 files and real issues; "review everything and fix the
  top 3" / "run the audit and tell me where it stands" style asks
- turns that follow tool-heavy work, since attention-dilution predicts worse
  adherence after large tool outputs
- possibly measuring TOTAL words (tables/lists included), since structured
  overhead is exactly what prose_words strips

Also observed: +hook beats style-alone on this shape too (avg −6.7), consistent
with prior rounds; and prose_words under-counts code-styled answers (a `-i`
answer scores 0), which suppresses fact/checkable numbers on coding content.

## Round 2: heavy-result tasks — scope hook REFUTED (it backfired)

`report2` conversation: 7-file seeded app (SQL injection, plaintext passwords,
N+1, hardcoded secret + DEBUG, off-by-one pagination, mutable default, dead
code, bare except, 200-for-bad-creds, README falsely claiming bcrypt), 16
heavy-result turns (audits, whole-repo "top 5" review, status summary), 2
completeness guards. Opus, 4 trials. `drift_opus_report2_scope.json`.

Report-turn avg prose words: Say Less 51.1, **+hook 44.2**, +scopehook **56.9**.
Total words: same ranking. The scope hook was the LONGEST on the exact turns it
targeted, above even plain style.

- The structural budget ("outcome in 1-2 sentences, one list, a named offer")
  acts as a TARGET the model fills out to, and the offer clause adds a line.
  Length budgets as targets backfire (RESEARCH.md lever 6), now confirmed on the
  intended workload, not just refuted-by-absence.
- Completeness held: all conditions listed 5/5 on the "top 5" guard turn, so the
  scope text added words without protecting content. No trade, pure loss.
- +hook (anti-anchoring only, no structural budget) stays best across every
  shape (default / coding / report / report2).

Conclusion: prescribing report STRUCTURE via the hook fails. The residual is
real (heavy-result reports do run long), but the lever is a sharper OBJECTIVE in
the style spec, not more rules in the hook. Next: the glance benchmark
(`glance_bench.py`) + `say-less-v2.md`, which reframe the target as "outcome in
line 1, reader can stop there, detail on pull" and measure it directly. See
2026-07-glance-v2.md (pending).
