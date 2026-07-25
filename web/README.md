# The comparison UI

`say-less.html` is the only interface. Ask Claude Code anything and watch it
answer twice, side by side, streaming: left is stock Claude Code, right is the
same model with the Say Less style on. Word counts update live.

```bash
python3 benchmark/serve_compare.py     # http://localhost:8787
```

The page is served by [`benchmark/serve_compare.py`](../benchmark/serve_compare.py),
which re-reads this file on every request, so edits show on refresh.

## Why it runs locally

The left column has to be real Claude Code, and Claude Code's system prompt
lives inside the CLI. It cannot be reproduced from an API key, so an
API-key-backed version could only ever compare "Claude with no style", which is
a weaker claim than the one the benchmarks make. Running the CLI keeps the
comparison honest.

The upside: no API key, and no per-request cost beyond your Claude subscription.
The tradeoff: it can't be deployed to a public site as-is.

## Fairness

Both arms run hermetically (`--setting-sources project`): no user `CLAUDE.md`,
no user settings, no user-scope plugins. Without that, the Say Less plugin is
installed user-scope with `force-for-plugin`, so it would apply to the "Default"
arm too and the comparison would be meaningless.

Everything else is identical — same model, same flags, same prompt. The output
style is the only variable.

## Options

```bash
python3 benchmark/serve_compare.py --port 9000 --model claude-opus-4-8
```

Model defaults to `claude-sonnet-5`, matching the benchmarks in `benchmark/results/`.
