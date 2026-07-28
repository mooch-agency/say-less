# The comparison UI

`say-less.html` is the only interface. Ask Claude Code anything and watch it
answer twice, side by side, streaming: left is stock Claude Code, right is the
same model with the Say Less style on. Word counts update live.

```bash
python3 benchmark/serve_compare.py     # http://localhost:8787
```

The page is served by [`benchmark/serve_compare.py`](../benchmark/serve_compare.py),
which re-reads `say-less.html` on every request, so edits show on refresh.

Each column runs its own clock. Both start ticking together, which is what makes
the parallelism visible: the Say Less arm usually finishes first and then sits
there done while the default arm keeps writing. Expect two to three seconds of
quiet before the first words, which is two `claude` sessions booting.

Closing the tab or pressing Stop kills both `claude` processes within a couple of
seconds, so an abandoned run doesn't keep burning usage. An arm that fails shows
its error in place and the other one still finishes.

## Why it runs locally

The left column has to be real Claude Code, and Claude Code's system prompt
lives inside the CLI. It cannot be reproduced from an API key, so an
API-key-backed version could only ever compare "Claude with no style", which is
a weaker claim than the one the benchmarks make. Running the CLI keeps the
comparison honest.

The upside: no API key, and no per-request cost beyond your Claude subscription.
The tradeoff: it can't be deployed to a public site as-is.

[mooch.agency/say-less](https://mooch.agency/say-less) is the deployed variant,
and it is a different claim: both arms there are Anthropic API calls, stock
Claude vs Claude with the style as a system prompt. It's a feel test anyone can
run in a browser. This page is the one that compares real Claude Code, which is
why the benchmark numbers come from here.

## Fairness

Both arms run hermetically (`--setting-sources project`): no user `CLAUDE.md`,
no user settings, no user-scope plugins. Without that, the Say Less plugin is
installed user-scope with `force-for-plugin`, so it would apply to the "Default"
arm too and the comparison would be meaningless.

Everything else is identical: same model, same flags, same prompt. The output
style is the only variable.

## Options

```bash
python3 benchmark/serve_compare.py --port 9000 --model claude-opus-5
```

Model defaults to `claude-sonnet-5`, matching the benchmarks in `benchmark/results/`.
