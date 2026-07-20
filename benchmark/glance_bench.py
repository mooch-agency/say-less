#!/usr/bin/env python3
"""
glance_bench.py — does the reader get the OUTCOME at a glance?

The drift harnesses measure whether terseness persists. This measures a
different thing the other harnesses can't see: whether a reply serves an
overwhelmed reader who wants the decision/answer NOW, regardless of how much
input they pasted. A style can score perfect on adherence (0 em dashes, 0
openers) and still fail this if line 1 doesn't carry the outcome.

Single-turn (no drift): each prompt runs once per style through headless
`claude -p` under the real output style, exactly as Claude Code delivers it.
Three scores per reply:

  outcome_first  a judge sees ONLY the FIRST LINE + the question and answers
                 YES/NO: does the first line already state the outcome/decision/
                 direct answer, such that a busy reader could stop there? This is
                 the glance metric. (0/100)
  words          prose words (code stripped). Lower = less to read.
  completeness   the existing content judge on the FULL reply (0-100): guards
                 that leading with the outcome didn't drop required content.

Headline per style: glance_pass = fraction of replies that are BOTH
outcome_first AND complete (>= COMPLETE_MIN). That's the objective to maximize:
the reader gets the outcome at a glance AND nothing required was lost. avg_words
is the cost to do it at.

Prompts are held out from both styles' few-shot examples, and half carry a heavy
INPUT (code, a trace, a diff, logs) to test "outcome-first regardless of input".

Usage:
  python3 benchmark/glance_bench.py "Say Less" "Say Less v2" \
      [--trials 3] [--model opus] [--workers 6] [--out glance.json]
"""

import argparse
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from drift_session import (claude_turn, claude_plain, prose_words, total_words,
                           count_em_dashes, _env)

HERE = os.path.dirname(os.path.abspath(__file__))
import tempfile

COMPLETE_MIN = 85  # a reply below this dropped required content; can't count as a glance win

_CODE = (
    "def apply_discount(price, pct):\n"
    "    return price - price * pct\n"
    "# called as apply_discount(100, 20) expecting 80\n"
)
_TRACE = (
    "Traceback (most recent call last):\n"
    '  File "sync.py", line 31, in run\n'
    "    users[uid].sync()\n"
    "KeyError: 4021\n"
)
_DIFF = (
    "@@ def withdraw(acct, amount):\n"
    "-    acct.balance -= amount\n"
    "+    if amount > acct.balance:\n"
    "+        raise ValueError('insufficient funds')\n"
    "+    acct.balance -= amount\n"
    "+    audit.log(acct.id, amount)\n"
)
_LOG = (
    "504 Gateway Timeout  upstream=payments  latency=30001ms\n"
    "504 Gateway Timeout  upstream=payments  latency=30002ms\n"
    "200 OK               upstream=payments  latency=120ms\n"
)

# kind is for reading the results only; every prompt HAS a discernible outcome
# (a value, a pick, a verdict, a fix) that line 1 should carry.
PROMPTS = [
    {"kind": "fact",     "prompt": "What's the default port for PostgreSQL?"},
    {"kind": "fact",     "prompt": "In Python, is a tuple mutable?"},
    {"kind": "decision", "prompt": "For a 3-person startup's first backend, should we go serverless or a single always-on server?"},
    {"kind": "decision", "prompt": "Should I store money as floats or integer cents in a payments table?"},
    {"kind": "decision", "prompt": "We have flaky end-to-end tests. Delete them or fix them?"},
    {"kind": "debug",    "prompt": "This returns 20, not 80. What's wrong?\n\n" + _CODE},
    {"kind": "debug",    "prompt": "What's causing this and how do I fix it?\n\n" + _TRACE},
    {"kind": "review",   "prompt": "Is this safe to merge?\n\n" + _DIFF},
    {"kind": "debug",    "prompt": "Our checkout is intermittently failing. Here are the logs. What's going on?\n\n" + _LOG},
    {"kind": "decision", "prompt": "Postgres JSONB column or a separate table for user settings that we rarely query?"},
    {"kind": "explain",  "prompt": "Explain what a database index costs you, in return for faster reads."},
    {"kind": "explain",  "prompt": "Explain how a bloom filter can say 'definitely not' but only 'probably yes'."},
    {"kind": "fact",     "prompt": "What git command discards all uncommitted changes in the working tree?"},
    {"kind": "decision", "prompt": "Should a small internal CRUD app add Redis caching now or wait?"},
    {"kind": "review",   "prompt": "Anything wrong here?\n\ntoken = jwt.encode(payload, 'secret123', algorithm='HS256')"},
    {"kind": "debug",    "prompt": "This loop is O(n^2) on a 50k-row list and times out. What's the fix?\n\nfor a in rows:\n    if a in seen: continue\n    seen.append(a)"},
]

OUTCOME_SYS = (
    "You are grading whether the FIRST LINE of an answer gives a busy reader the "
    "bottom line. You get a QUESTION and only the FIRST LINE of the answer. Answer "
    "YES if that first line already states the outcome: the decision, the direct "
    "answer, the verdict, or the fix, such that a reader could act and stop there. "
    "Answer NO if the first line is preamble, a restatement of the question, setup, "
    "background, or hedging that makes them read on to learn the outcome. Output "
    "ONLY the word YES or NO."
)
COMPLETE_SYS = (
    "You are a strict grader. Given a QUESTION and an ANSWER, output ONLY an integer "
    "0-100: how completely the answer covers the content the question requires "
    "(all parts, correct key facts, any critical caveat). IGNORE verbosity, length, "
    "style, ordering, and politeness. A terse answer that covers everything is 100. "
    "An answer that omits a required part or a safety-critical caveat is low. Output "
    "the integer and nothing else."
)


def first_line(text):
    for ln in text.strip().splitlines():
        if ln.strip():
            return ln.strip()
    return ""


def judge_yesno(question, line, model, cwd):
    if not line:
        return 0
    for _ in range(3):
        out = claude_plain(f"QUESTION:\n{question}\n\nFIRST LINE:\n{line}", OUTCOME_SYS, model, cwd)
        u = out.strip().upper()
        if "YES" in u and "NO" not in u:
            return 100
        if "NO" in u and "YES" not in u:
            return 0
    return 0


def judge_complete(question, answer, model, cwd):
    if not answer.strip():
        return 0
    last = -1
    for _ in range(3):
        out = claude_plain(f"QUESTION:\n{question}\n\nANSWER:\n{answer}", COMPLETE_SYS, model, cwd)
        m = re.findall(r"\d+", out)
        if m:
            last = max(0, min(100, int(m[0])))
            if last > 0:
                return last
    return last


def run_one(style, step, model, judge_model):
    with tempfile.TemporaryDirectory(prefix="glance_") as cwd:
        reply, _ = claude_turn(step["prompt"], style, model, cwd)
    fl = first_line(reply)
    # Judge with a FIXED reliable grader (default sonnet), never the generation
    # model: opus is a poor grader here (scored "5432." 0% complete, "No." NO).
    # claude_plain is hermetic, so cwd is unused.
    outcome = judge_yesno(step["prompt"], fl, judge_model, None)
    complete = judge_complete(step["prompt"], reply, judge_model, None)
    return {
        "kind": step["kind"], "prompt": step["prompt"], "reply": reply, "first_line": fl,
        "words": prose_words(reply), "total_words": total_words(reply),
        "em_dashes": count_em_dashes(reply),
        "outcome_first": outcome, "completeness": complete,
        "glance_win": int(outcome == 100 and complete >= COMPLETE_MIN),
    }


def main():
    ap = argparse.ArgumentParser(description="Glance test: outcome-in-line-1 + words + completeness.")
    ap.add_argument("styles", nargs="+", help='Output-style names. "Default" = baseline.')
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--model", default="opus", help="Generation model (the style is tested on this).")
    ap.add_argument("--judge-model", default="sonnet",
                    help="Grader model, fixed and separate from --model. Opus grades this task poorly.")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(HERE, "glance_results.json"))
    args = ap.parse_args()

    jobs = [(st, i, t) for st in args.styles for i in range(len(PROMPTS)) for t in range(args.trials)]
    raw = {st: [] for st in args.styles}
    print(f"Running {len(jobs)} replies ({len(args.styles)} styles x {len(PROMPTS)} prompts x "
          f"{args.trials} trials), model={args.model}\n", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, st, PROMPTS[i], args.model, args.judge_model): st for st, i, t in jobs}
        done = 0
        for fut in as_completed(futs):
            raw[futs[fut]].append(fut.result())
            done += 1
            if done % 10 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}", flush=True)

    summary = {}
    for st, rows in raw.items():
        n = len(rows) or 1
        summary[st] = {
            "n": len(rows),
            "outcome_first_rate": round(sum(r["outcome_first"] for r in rows) / n / 100, 3),
            "avg_words": round(sum(r["words"] for r in rows) / n, 1),
            "avg_completeness": round(sum(r["completeness"] for r in rows) / n, 1),
            "glance_pass": round(sum(r["glance_win"] for r in rows) / n, 3),
            "em_total": sum(r["em_dashes"] for r in rows),
            "by_kind": {},
        }
        for k in ["fact", "decision", "debug", "review", "explain"]:
            ks = [r for r in rows if r["kind"] == k]
            if ks:
                summary[st]["by_kind"][k] = {
                    "outcome_first_rate": round(sum(r["outcome_first"] for r in ks) / len(ks) / 100, 2),
                    "avg_words": round(sum(r["words"] for r in ks) / len(ks), 1),
                }

    with open(args.out, "w") as f:
        json.dump({"model": args.model, "judge_model": args.judge_model,
                   "trials": args.trials, "complete_min": COMPLETE_MIN,
                   "summary": summary, "raw": raw}, f, indent=2)

    print("\n=== GLANCE (glance_pass = outcome-in-line-1 AND complete; higher = better) ===")
    print(f"{'style':16} {'glance_pass':>11} {'outcome1st':>11} {'words':>7} {'compl':>6} {'em':>4}")
    for st in args.styles:
        s = summary[st]
        print(f"{st:16} {s['glance_pass']:>11} {s['outcome_first_rate']:>11} "
              f"{s['avg_words']:>7} {s['avg_completeness']:>6} {s['em_total']:>4}")

    print("\n=== outcome_first_rate / avg_words by kind ===")
    kinds = ["fact", "decision", "debug", "review", "explain"]
    print(f"{'style':16} " + " ".join(f"{k:>14}" for k in kinds))
    for st in args.styles:
        bk = summary[st]["by_kind"]
        cells = [f"{bk[k]['outcome_first_rate']:>5}/{bk[k]['avg_words']:<8.0f}" if k in bk else f"{'-':>14}" for k in kinds]
        print(f"{st:16} " + " ".join(cells))

    print(f"\nFull results: {args.out}")


if __name__ == "__main__":
    main()
