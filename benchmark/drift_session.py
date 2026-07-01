#!/usr/bin/env python3
"""
drift_session.py — multi-turn PERSISTENCE test on the real output style.

Runs a fixed N-turn conversation through headless `claude -p --resume`, so the
model sees its own prior replies and the context grows turn over turn. That is
the real condition under which a terseness style DRIFTS back toward verbose:
the model's own long earlier answers become few-shot examples pulling it long.

How this differs from the other two harnesses:
  ab_style.py       single-turn; measures wording (terseness + completeness).
  position_test.py  multi-turn but API-based, and tests a COMPACT rules string
                    placed top/bottom — it isolates PLACEMENT, not the real style.
  drift_session.py  multi-turn, and exercises the ACTUAL output style exactly as
                    Claude Code delivers it: appended to the system prompt, with
                    Claude Code's own (opaque) adherence reminders firing as the
                    conversation grows. This is the only harness that measures
                    whether the shipped style holds up across a whole session.

Each condition is an output-style NAME resolved from ~/.claude/output-styles/
(the frontmatter `name:`), selected per-run with --settings '{"outputStyle":...}'.
Use "Default" for the no-style baseline. Subscription billing only: any
ANTHROPIC_API_KEY is stripped from the child env, matching ab_style.py.

The conversation is built to INDUCE drift: floor/decision/checkable/explain
prompts are interleaved with context-growers (pasted code, a stack trace, a
diff-review — the exact "wall of text" trigger). The pattern repeats so the
first and second halves hold comparable prompt types; any rise in the second
half is decay, not harder questions. Checkable turns (ACID=4, CAP=3, methods=5)
are spread early AND late so --judge can catch completeness dropping over time.

Usage:
  python3 benchmark/drift_session.py "Default" "Say Less" [NAME ...] \
      [--trials 3] [--model sonnet] [--workers 6] [--judge] [--out results.json]

Notes:
- Runs each session in an isolated empty dir so the agent isn't tempted into
  tool use. User-scope ~/.claude/CLAUDE.md still applies, but it applies EQUALLY
  to every condition, so relative comparisons (which style drifts least) hold.
- --resume is sequential within a session; independent sessions run in parallel.
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))

# --- the conversation -------------------------------------------------------
# kind: fact | decision | checkable | explain | grow  (grow = context-grower)
# check: expected-content note for the completeness judge (checkable turns only)
_FUNC = (
    "def dedupe(items):\n"
    "    seen = []\n"
    "    for x in items:\n"
    "        if x not in seen:\n"
    "            seen.append(x)\n"
    "    return seen\n"
)
_TRACE = (
    "Traceback (most recent call last):\n"
    '  File "app.py", line 42, in handler\n'
    "    total = sum(cart[i].price for i in ids)\n"
    "KeyError: 'price'\n"
)
_DIFF = (
    "@@ def charge(user, amount):\n"
    "-    stripe.charge(user.card, amount)\n"
    "+    if amount <= 0:\n"
    "+        raise ValueError('amount must be positive')\n"
    "+    stripe.charge(user.card, amount)\n"
    "+    log.info(f'charged {user.id} {amount}')\n"
)

# Prompts are held out from every candidate style's few-shot EXAMPLES so no style
# can win a turn by copying its own example verbatim. (Avoided: Postgres port,
# REST vs GraphQL, TCP vs UDP, OAuth flow, git-undo, "what does this PR change".)
CONVERSATION = [
    {"kind": "fact",      "prompt": "What's the default port for Redis?"},
    {"kind": "decision",  "prompt": "Should I use a monorepo or separate repos for three related services?"},
    {"kind": "checkable", "prompt": "Name the four pillars of object-oriented programming and define each in one line.",
     "check": "encapsulation, abstraction, inheritance, polymorphism"},
    {"kind": "explain",   "prompt": "Explain how a hash map handles collisions."},
    {"kind": "grow",      "prompt": "What does this function do, and is there a performance problem?\n\n" + _FUNC},
    {"kind": "fact",      "prompt": "What HTTP status code means Unauthorized?"},
    {"kind": "decision",  "prompt": "Is it worth adding a message queue just to send emails asynchronously?"},
    {"kind": "checkable", "prompt": "What are the first three database normal forms (1NF, 2NF, 3NF)? Define each.",
     "check": "1NF atomic values, 2NF no partial dependency, 3NF no transitive dependency"},
    {"kind": "explain",   "prompt": "Explain how merge sort works."},
    {"kind": "grow",      "prompt": "What's causing this error and how do I fix it?\n\n" + _TRACE},
    {"kind": "fact",      "prompt": "What does chmod 755 set?"},
    {"kind": "decision",  "prompt": "MySQL or Postgres for a new analytics-heavy application?"},
    {"kind": "checkable", "prompt": "List the five main HTTP methods and what each is for.",
     "check": "GET, POST, PUT, PATCH, DELETE"},
    {"kind": "explain",   "prompt": "Explain the difference between a process and a thread."},
    {"kind": "grow",      "prompt": "Review this change.\n\n" + _DIFF},
    {"kind": "fact",      "prompt": "What's the difference between let and const in JavaScript?"},
]

# --- prose-aware counting + tic detectors (shared with the other harnesses) --

_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WORD = re.compile(r"[0-9A-Za-z]")

OPENERS = [
    "let me", "sure,", "sure!", "great question", "great,", "here's", "here is",
    "so,", "well,", "certainly", "of course", "i'd be happy", "happy to",
    "absolutely", "to answer", "in order to answer",
]
CLOSERS = [
    "hope this helps", "hope that helps", "let me know", "in summary",
    "to summarize", "to sum up", "to recap", "overall,", "in conclusion",
    "feel free to", "don't hesitate", "happy to help",
]


def _count(text):
    return sum(1 for tok in text.split() if _WORD.search(tok))


def prose_words(text):
    t = _FENCED.sub(" ", text)
    t = _MD_IMAGE.sub(" ", t)
    t = _MD_LINK.sub(r"\1", t)
    t = _INLINE_CODE.sub(" ", t)
    return _count(t)


def total_words(text):
    return _count(text)


def count_em_dashes(text):
    return text.count("—") + len(re.findall(r"\s--\s", text))


def has_opener(text):
    head = text.strip().lower()[:60]
    return int(any(head.startswith(o) or head[:25].find(o) != -1 for o in OPENERS))


def has_closer(text):
    tail = text.strip().lower()[-200:]
    return int(any(c in tail for c in CLOSERS))


def score_reply(text):
    return {
        "words": prose_words(text),
        "total_words": total_words(text),
        "em_dashes": count_em_dashes(text),
        "opener": has_opener(text),
        "closer": has_closer(text),
    }


# --- headless claude --------------------------------------------------------

JUDGE_SYS = (
    "You are a strict grader. You are given a QUESTION and an ANSWER. Output "
    "ONLY a single integer from 0 to 100: how completely the answer covers the "
    "content the question requires. Judge ONLY completeness of required content "
    "(all parts of a multi-part question, correct key facts). IGNORE verbosity, "
    "length, style, and politeness entirely. A terse answer that covers "
    "everything scores 100. Output the integer and nothing else."
)


def _env():
    # Force subscription billing, never API-key billing (matches ab_style.py).
    return {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}


def claude_turn(prompt, style, model, cwd, resume=None):
    """One headless turn. Returns (reply_text, session_id)."""
    cmd = [
        "claude", "-p", prompt,
        "--settings", json.dumps({"outputStyle": style}),
        "--model", model,
        "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config",
        "--output-format", "json",
    ]
    if resume:
        cmd += ["--resume", resume]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=300, env=_env(), cwd=cwd)
        data = json.loads(r.stdout)
        return data.get("result", ""), data.get("session_id", resume)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return "", resume


def claude_plain(prompt, system, model, cwd):
    """One-shot judge call with a replacement system prompt."""
    cmd = [
        "claude", "-p", prompt, "--system-prompt", system, "--model", model,
        "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=180, env=_env(), cwd=cwd)
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def judge_completeness(question, answer, model, cwd):
    if not answer.strip():
        return 0
    # Retry on parse failure or an implausible 0 (a non-empty answer to these
    # prompts is never 0% complete; a spurious 0 is a judge misfire, so re-ask).
    last = -1
    for _ in range(3):
        out = claude_plain(f"QUESTION:\n{question}\n\nANSWER:\n{answer}", JUDGE_SYS, model, cwd)
        m = re.findall(r"\d+", out)
        if m:
            last = max(0, min(100, int(m[0])))
            if last > 0:
                return last
    return last


def run_session(style, model, do_judge):
    """One full multi-turn conversation under a style. Returns per-turn scores."""
    # Isolated empty dir so the agent isn't tempted into tool use.
    with tempfile.TemporaryDirectory(prefix="drift_") as cwd:
        sid = None
        turns = []
        for i, step in enumerate(CONVERSATION):
            reply, sid = claude_turn(step["prompt"], style, model, cwd,
                                     resume=sid if i else None)
            s = score_reply(reply)
            s["kind"] = step["kind"]
            s["reply"] = reply  # kept for auditing judge scores / inspecting drift
            if do_judge and step["kind"] == "checkable":
                s["completeness"] = judge_completeness(step["prompt"], reply, model, cwd)
            turns.append(s)
    return turns


# --- aggregation ------------------------------------------------------------

def _slope(ys):
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return round(sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom, 2)


def aggregate(results):
    """results: {style: [trial][turn] -> score}. Returns per-style summary."""
    summary = {}
    n_turns = len(CONVERSATION)
    half = n_turns // 2
    for style, trials in results.items():
        words, ems, opens, closes = [], [], [], []
        first, second = [], []
        per_turn = [[] for _ in range(n_turns)]
        per_kind = {}
        comps = []
        for trial in trials:
            for i, t in enumerate(trial):
                words.append(t["words"])
                ems.append(t["em_dashes"])
                opens.append(t["opener"])
                closes.append(t["closer"])
                per_turn[i].append(t["words"])
                (first if i < half else second).append(t["words"])
                per_kind.setdefault(t["kind"], []).append(t["words"])
                if "completeness" in t and t["completeness"] >= 0:
                    comps.append(t["completeness"])
        n = len(words) or 1
        f_avg = sum(first) / (len(first) or 1)
        s_avg = sum(second) / (len(second) or 1)
        summary[style] = {
            "avg_words": round(sum(words) / n, 1),
            "em_dashes_total": sum(ems),
            "opener_rate": round(sum(opens) / n, 3),
            "closer_rate": round(sum(closes) / n, 3),
            "first_half_avg": round(f_avg, 1),
            "second_half_avg": round(s_avg, 1),
            "drift_pct": round((s_avg - f_avg) / f_avg * 100, 1) if f_avg else 0.0,
            "slope_words_per_turn": _slope([sum(w) / (len(w) or 1) for w in per_turn]),
            "per_turn_avg_words": [round(sum(w) / (len(w) or 1), 1) for w in per_turn],
            "per_kind_avg_words": {k: round(sum(v) / len(v), 1) for k, v in per_kind.items()},
            "avg_completeness": round(sum(comps) / len(comps), 1) if comps else None,
            "sessions": len(trials),
        }
    return summary


def main():
    ap = argparse.ArgumentParser(description="Multi-turn persistence/drift test on real output styles.")
    ap.add_argument("styles", nargs="+", help='Output-style names (frontmatter name:). "Default" = baseline.')
    ap.add_argument("--trials", type=int, default=3, help="Sessions per style.")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--workers", type=int, default=6, help="Parallel sessions.")
    ap.add_argument("--judge", action="store_true", help="Score completeness on checkable turns.")
    ap.add_argument("--out", default=os.path.join(HERE, "drift_session_results.json"))
    args = ap.parse_args()

    jobs = [(st, t) for st in args.styles for t in range(args.trials)]
    raw = {st: [None] * args.trials for st in args.styles}
    print(f"Running {len(jobs)} sessions "
          f"({len(args.styles)} styles x {args.trials} trials x {len(CONVERSATION)} turns), "
          f"model={args.model}, judge={args.judge}", flush=True)
    print(f"styles: {', '.join(args.styles)}\n", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_session, st, args.model, args.judge): (st, t)
                for st, t in jobs}
        done = 0
        for fut in as_completed(futs):
            st, t = futs[fut]
            raw[st][t] = fut.result()
            done += 1
            print(f"  {done}/{len(jobs)} done: {st} trial {t + 1}", flush=True)

    summary = aggregate(raw)
    with open(args.out, "w") as f:
        json.dump({"model": args.model, "trials": args.trials,
                   "conversation": [c["prompt"][:50] for c in CONVERSATION],
                   "summary": summary, "raw": raw}, f, indent=2)

    print("\n=== SUMMARY (words = prose per reply; lower = terser) ===")
    hdr = (f"{'style':16} {'avg':>6} {'1st_h':>6} {'2nd_h':>6} {'drift%':>7} "
           f"{'slope':>6} {'em':>4} {'open':>5} {'close':>5} {'compl':>6}")
    print(hdr)
    for st in args.styles:
        s = summary[st]
        print(f"{st:16} {s['avg_words']:>6} {s['first_half_avg']:>6} {s['second_half_avg']:>6} "
              f"{s['drift_pct']:>7} {s['slope_words_per_turn']:>6} {s['em_dashes_total']:>4} "
              f"{s['opener_rate']:>5} {s['closer_rate']:>5} {str(s['avg_completeness']):>6}")

    print("\n=== per-kind avg prose words ===")
    kinds = ["fact", "decision", "checkable", "explain", "grow"]
    print(f"{'style':16} " + " ".join(f"{k:>10}" for k in kinds))
    for st in args.styles:
        pk = summary[st]["per_kind_avg_words"]
        print(f"{st:16} " + " ".join(f"{pk.get(k, 0):>10}" for k in kinds))

    print(f"\nFull results: {args.out}")


if __name__ == "__main__":
    main()
