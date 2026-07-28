# Say Less persistence hook

The output style alone does not hold terseness across a long Opus session. Two
independent prompt-content experiments (sl-v4's anti-anchoring line, sl-v5's
numbered self-check) failed to beat the shipped style's ~+37% verbosity drift.
The lever that works is **re-injecting the rule at the newest turn**, which the
static system-prompt style cannot do and Claude Code's built-in output-style
reminder does too weakly on Opus.

`say-less-gate.sh` is a `UserPromptSubmit` hook. From the 2nd turn of a session
on, it prints a short, recency-placed, application-framed, anti-anchoring
directive that is added to the model's context for that turn:

> [Say Less] Later turn. Match the brevity of your FIRST reply this session:
> lead with the answer, fewest complete lines, no em dashes. Do not let your
> recent, longer replies set the length; length is set by THIS question alone.
> Keep every step, number, and caveat.

## Measured effect (Opus, paired, same batch — see ../results/2026-07-drift-persistence-hook.md)

| metric | style alone | style + hook | change |
|---|---|---|---|
| 2nd-half prose words | 95.0 | 69.8 | **−26%** |
| drift gap (2nd − 1st half) | 21.5 | 14.0 | **−35%** |
| slope (words/turn) | 2.62 | 1.77 | **−32%** |
| em dashes (96 replies) | 114 | 0 | **→ 0** |
| completeness (excl. judge misfires) | 98.2 | 94.8 | flat (within noise) |

Holds on a second, longer (28-turn) coding/debugging session shape too (see the
results doc). The win is both terser overall AND a genuinely flatter climb, so
late-session replies stop drifting back toward verbose.

## Why it targets the mechanism

Drift is a *recall–adherence dissociation*: late in a session Opus still recalls
the terseness rule (it stays in context) but stops applying it, because its own
lengthening earlier replies anchor it long. A fresh directive at the newest user
turn forces re-application at generation time and explicitly tells the model not
to anchor on its recent replies. That is the one spot a system-prompt style
can't reach.

## Install

**Per project (safe, fires only in this repo):** add this to
`.claude/settings.json` at the repo root. That file is gitignored, so it isn't
shipped and you have to create it yourself:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command",
        "command": "bash \"${CLAUDE_PROJECT_DIR:-.}/benchmark/hooks/say-less-gate.sh\"", "timeout": 5 } ] }
    ]
  }
}
```

**Globally (fires in every session, every project):** copy the script somewhere
stable and add the hook to `~/.claude/settings.json`:

```bash
mkdir -p ~/.claude/hooks
cp benchmark/hooks/say-less-gate.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/say-less-gate.sh
```

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command",
        "command": "bash \"$HOME/.claude/hooks/say-less-gate.sh\"", "timeout": 5 } ] }
    ]
  }
}
```

**Caveat for global install:** the hook fires on every turn regardless of the
active output style, so it nudges toward terseness even when Say Less is not the
active style. Install globally only if you want terseness as a standing default.
To scope it to Say Less, keep it per-project, or gate the script on your own
signal (e.g. an env var you set alongside the style).

## Test / reproduce

```bash
# style-alone vs style+hook, paired in one batch, on the model that drifts
python3 benchmark/drift_session.py "Say Less" "Say Less+hook" \
    --model opus --judge --trials 6 --workers 3 --out benchmark/drift_opus_hook.json
python3 benchmark/analyze_drift.py benchmark/drift_opus_hook.json --baseline "Say Less"

# robustness: same on the longer coding/debugging session shape
python3 benchmark/drift_session.py "Say Less" "Say Less+hook" \
    --model opus --judge --trials 5 --conversation coding --out benchmark/drift_opus_hook_coding.json
```

The `+hook` suffix on a style name is understood by `drift_session.py`: it runs
that output style plus this hook, copied into the session's temp cwd and wired in
via `--settings`, so one batch compares style-alone vs style+hook under identical
conditions.
