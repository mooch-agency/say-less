#!/usr/bin/env bash
# UserPromptSubmit hook: say-less-gate.sh PLUS a structural scope budget.
#
# Round-3 hypothesis (results/2026-07-channel-comparison.md, RESEARCH.md round 3):
# the wording levers are exhausted; residual verbosity is CONTENT SELECTION,
# worst on task-report turns ("here's what I did"). Word-count budgets fail for
# a perceptual reason (models can't count their own words, LARFT 2603.19255),
# so the budget is stated in COUNTABLE STRUCTURE: outcome sentences, one list
# max, no headers, detail behind a named offer. Injected at recency because
# hooks are the only per-turn mechanism (nothing static re-injects).
#
# Delta vs say-less-gate.sh is the scope block ONLY, so a paired run isolates
# the scope budget's contribution. Scope fires from turn 1 (reports are verbose
# immediately, not only after drift); the anti-anchoring line still starts at
# turn 2 (turn 1 has no earlier reply to anchor to).
#
# stdin: JSON {session_id, cwd, prompt, transcript_path, hook_event_name}.
# stdout on a firing turn is added to the model's context for THIS turn.
set -euo pipefail

input=$(cat)
field() { printf '%s' "$input" | python3 -c "import sys,json;print(json.load(sys.stdin).get('$1',''))" 2>/dev/null || true; }

sid=$(field session_id); [ -z "$sid" ] && sid="x"

ctr="${TMPDIR:-/tmp}/slscope_${sid}"
n=$(( $(cat "$ctr" 2>/dev/null || echo 0) + 1 ))
printf '%s' "$n" > "$ctr"

printf '%s\n' "[Say Less] Scope: include only what this request needs. Lead with the outcome in 1-2 sentences. Use at most ONE list or table, no section headers, and do not narrate the steps you took unless asked. If real detail remains, end with one short named offer (\"want X?\"). Keep every number, caveat, and required item."

if [ "$n" -ge 2 ]; then
  printf '%s\n' "[Say Less] Later turn. Match the brevity of your FIRST reply this session: lead with the answer, fewest complete lines, no em dashes. Do not let your recent, longer replies set the length; length is set by THIS question alone. Keep every step, number, and caveat."
fi
exit 0
