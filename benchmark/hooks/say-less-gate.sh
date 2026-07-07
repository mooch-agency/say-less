#!/usr/bin/env bash
# UserPromptSubmit hook for the Say Less output style: holds terseness across a
# long session, which the static style can't do on its own.
#
# Why it works: Opus drift is a recall-adherence dissociation — late in a session
# the model still RECALLS the terseness rule (Claude Code's built-in output-style
# reminder keeps it in context) but stops APPLYING it, because its own lengthening
# earlier replies anchor it long. Static prompt rules can't fight this (sl-v4 and
# sl-v5 both failed). This hook injects a fresh, recency-placed, application-framed,
# anti-anchoring directive at the newest user turn — the one spot the static style
# can't reach — to force re-application every turn. Measured on Opus: late-session
# prose words -26% to -41%, drift gap -35% to -40%, em dashes to ~0, completeness
# held. See benchmark/results/2026-07-drift-persistence-hook.md.
#
# stdin: JSON {session_id, cwd, prompt, transcript_path, hook_event_name}.
# stdout on a firing turn is added to the model's context for THIS turn.
set -euo pipefail

input=$(cat)
field() { printf '%s' "$input" | python3 -c "import sys,json;print(json.load(sys.stdin).get('$1',''))" 2>/dev/null || true; }

sid=$(field session_id); [ -z "$sid" ] && sid="x"

# Per-session turn counter, kept in $TMPDIR (auto-cleaned by the OS, never litters
# a project dir). Its value is also the firing evidence if you need to verify.
ctr="${TMPDIR:-/tmp}/slgate_${sid}"
n=$(( $(cat "$ctr" 2>/dev/null || echo 0) + 1 ))
printf '%s' "$n" > "$ctr"

# From turn 2 on (turn 1 has no earlier reply to anchor to), inject the nudge.
if [ "$n" -ge 2 ]; then
  printf '%s\n' "[Say Less] Later turn. Match the brevity of your FIRST reply this session: lead with the answer, fewest complete lines, no em dashes. Do not let your recent, longer replies set the length; length is set by THIS question alone. Keep every step, number, and caveat."
fi
exit 0
