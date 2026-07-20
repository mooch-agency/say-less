#!/usr/bin/env python3
"""
spot.py — the cheap eyeball test. One style, ~10 prompts, no judges, no scores.

Replaces the heavy harnesses for day-to-day iteration: glance_bench and
drift_session burn tokens on LLM judges and paired baselines we already have on
file (see results/). This just generates the replies and prints them with a
word count, for a human (and Claude, in-session) to judge against the target:
the examples in the style file itself.

Usage:
  python3 benchmark/spot.py "Say Less v3"                  # sonnet, all 10
  python3 benchmark/spot.py "Say Less v3" --model opus -n 5
"""

import argparse
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from drift_session import claude_turn, prose_words

# 10 prompts shaped like a real Claude Code session: facts, decisions, pasted
# code/traces, a review, an explain. Held out from every style's examples.
PROMPTS = [
    "What's the default port for MongoDB?",
    "Should I use UUIDs or auto-increment integers for primary keys in Postgres?",
    "What's wrong here?\n\nasync function getUsers() {\n  const ids = await getIds();\n  const users = [];\n  for (const id of ids) {\n    users.push(await fetchUser(id));\n  }\n  return users;\n}",
    "What's causing this?\n\nTypeError: 'NoneType' object is not subscriptable\n  File \"report.py\", line 12, in build\n    total = data['rows'][0]",
    "Is this safe to merge?\n\n@@ def delete_account(user_id):\n-    db.delete(user_id)\n+    user = db.get(user_id)\n+    user.deleted_at = now()\n+    db.save(user)",
    "Explain what eventual consistency means for a web app.",
    "Our Docker image is 2.1GB. How do I make it smaller?",
    "Redis or Memcached for basic session caching?",
    "This SQL is slow on 10M rows:\n\nSELECT * FROM events WHERE DATE(created_at) = '2026-07-01';",
    "Should we write unit tests for private methods?",
]


def gen(style, prompt, model):
    with tempfile.TemporaryDirectory(prefix="spot_") as cwd:
        reply, _ = claude_turn(prompt, style, model, cwd)
    return reply


def main():
    ap = argparse.ArgumentParser(description="Cheap spot check: print replies + word counts, judge by eye.")
    ap.add_argument("style", help='Output-style name (frontmatter name:), e.g. "Say Less v3"')
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("-n", type=int, default=len(PROMPTS), help="How many prompts (default all).")
    args = ap.parse_args()

    prompts = PROMPTS[: args.n]
    with ThreadPoolExecutor(max_workers=5) as ex:
        replies = list(ex.map(lambda p: gen(args.style, p, args.model), prompts))

    words = []
    for q, a in zip(prompts, replies):
        w = prose_words(a)
        words.append(w)
        print("=" * 72)
        print(f"Q: {q.splitlines()[0]}")
        print(f"A ({w} prose words):\n{a.strip() or '<EMPTY>'}\n")
    print("=" * 72)
    print(f"{args.style} on {args.model}: median {sorted(words)[len(words)//2]} words, "
          f"range {min(words)}-{max(words)}. Target: example-length (roughly 5-40).")


if __name__ == "__main__":
    main()
