#!/usr/bin/env python3
"""
position_test.py — Instruction placement experiment (TOP vs BOTTOM).

Question: do identical low-verbosity rules produce terser, more rule-adherent
replies when placed in the SYSTEM PROMPT (top of context) vs APPENDED to each
user message (bottom, simulating a UserPromptSubmit re-injection every turn)?
And does top placement DRIFT — get more verbose over a long conversation —
relative to bottom re-injection?

Four conditions, same neutral base system prompt for all:
  none    no rules anywhere (baseline verbosity)
  top     rules in the system prompt only
  bottom  rules appended to every user turn (re-injected each turn)
  both    rules in system prompt AND appended every turn

Each condition runs a fixed multi-turn conversation N times (trials). The
assistant's real replies are fed back into history, so the model sees its own
prior output and can drift. We measure words per reply and a few AI-tics
(em dashes, throat-clearing openers, gift-wrapped closers) per turn.

Usage:
  ANTHROPIC_API_KEY=sk-... python3 benchmark/position_test.py \
      [--trials 3] [--model claude-sonnet-4-6] [--out results.json] [--workers 6]

Stdlib only (urllib). The key is read from the environment, never hardcoded.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

# Compact essence of the Say Less / vl rules. Same text wherever it is placed,
# so the only variable is POSITION.
RULES = (
    "Reply in low-verbosity mode. Fewest words for a clear, complete answer. "
    "Lead with the answer. Cut preamble, summary scaffolding, and narration of "
    'your own work. No throat-clearing openers (no "Let me", "Sure", "Great '
    'question", "Here\'s what"). No gift-wrapped endings (no "Hope this helps", '
    '"In summary", "Let me know if"). No em dashes. No sycophancy. No hedging on '
    "things you know. Keep code and exact values verbatim. Reason fully "
    "internally; only the final reply is terse."
)

BASE_SYSTEM = "You are a helpful coding and technical assistant."

# Verbosity-tempting prompts: a mix of one-line-answerable facts and explainers,
# so we measure both the floor and the ceiling of verbosity.
PROMPTS = [
    "What's the default PostgreSQL port?",
    "Should I use REST or GraphQL for a new internal API?",
    "Explain how a bloom filter works.",
    "What's the difference between TCP and UDP?",
    "How do I undo the last git commit but keep the changes staged?",
    "Is it worth adding Redis to cache database reads?",
    "Walk me through the OAuth2 authorization code flow.",
    "What are the tradeoffs between optimistic and pessimistic locking?",
]

CONDITIONS = ["none", "top", "bottom", "both"]

# Drift-isolation set: ~20 questions of roughly equal (small) difficulty, each
# answerable in 1-3 sentences. Constant difficulty means any rise in word count
# across turns reflects instruction DECAY, not harder prompts. Used by --mode drift.
LEVEL_PROMPTS = [
    "What's the default port for Redis?",
    "What does the git stash command do?",
    "What's the difference between == and === in JavaScript?",
    "What HTTP status code means Not Found?",
    "What does chmod 644 set?",
    "What's a foreign key in a database?",
    "What does the useEffect hook do in React?",
    "What's the difference between a process and a thread?",
    "What does SELECT DISTINCT do in SQL?",
    "What's the purpose of a .gitignore file?",
    "What does the await keyword do?",
    "What's the difference between PUT and PATCH?",
    "What does a load balancer do?",
    "What's the difference between null and undefined in JavaScript?",
    "What does docker build do?",
    "What's a database index for?",
    "What does the CSS flex property do?",
    "What's the difference between let and const?",
    "What does a reverse proxy do?",
    "What's the purpose of a JWT?",
]

# --- tic detectors ----------------------------------------------------------

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


# Prose-aware counting (mirrors the standalone `wordcount` CLI; duplicated on
# purpose so this benchmark stays self-contained for open-sourcing). Low
# verbosity is about prose padding, so code/commands/values are excluded from
# the primary count. Kept in sync with ~/.local/bin/wordcount by hand.
_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WORD = re.compile(r"[0-9A-Za-z]")  # a token counts only if it has an alphanumeric char


def _count(text):
    return sum(1 for tok in text.split() if _WORD.search(tok))


def prose_words(text):
    """Words excluding fenced code, inline code, and link URLs."""
    t = _FENCED.sub(" ", text)
    t = _MD_IMAGE.sub(" ", t)
    t = _MD_LINK.sub(r"\1", t)
    t = _INLINE_CODE.sub(" ", t)
    return _count(t)


def total_words(text):
    """All words, but pure-punctuation tokens (e.g. bare `-` bullets) don't count."""
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
        "words": prose_words(text),        # primary: prose only (padding lives here)
        "total_words": total_words(text),  # secondary: incl. code/commands
        "em_dashes": count_em_dashes(text),
        "opener": has_opener(text),
        "closer": has_closer(text),
    }


# --- API --------------------------------------------------------------------

def call_api(api_key, model, system, messages, max_retries=5):
    payload = json.dumps({
        "model": model,
        "max_tokens": 1024,
        "temperature": 1.0,
        "system": system,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(API_URL, data=payload, method="POST")
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", API_VERSION)
    req.add_header("content-type", "application/json")
    backoff = 2.0
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            return "".join(b.get("text", "") for b in data.get("content", []))
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="ignore")
            if e.code in (429, 500, 529) and attempt < max_retries - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise RuntimeError(f"HTTP {e.code}: {body[:300]}")
        except (urllib.error.URLError, TimeoutError):
            if attempt < max_retries - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise
    raise RuntimeError("exhausted retries")


def run_conversation(api_key, model, condition, prompts):
    """One full multi-turn conversation under a condition. Returns per-turn scores."""
    system = BASE_SYSTEM
    if condition in ("top", "both"):
        system = BASE_SYSTEM + "\n\n" + RULES
    messages = []
    turns = []
    for prompt in prompts:
        user_text = prompt
        if condition in ("bottom", "both"):
            user_text = prompt + "\n\n[reminder] " + RULES
        messages.append({"role": "user", "content": user_text})
        reply = call_api(api_key, model, system, messages)
        messages.append({"role": "assistant", "content": reply})
        turns.append(score_reply(reply))
    return turns


# --- aggregation ------------------------------------------------------------

def _slope(ys):
    """Least-squares slope of ys over x=0..n-1 (words gained per turn)."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return round(sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom, 2)


def aggregate(results, prompts):
    """results: {condition: [trial][turn] -> score dict}. Returns summary."""
    summary = {}
    n_turns = len(prompts)
    half = n_turns // 2
    for cond, trials in results.items():
        all_words, all_total, all_em, all_open, all_close = [], [], [], [], []
        first_half, second_half = [], []
        per_turn_words = [[] for _ in range(n_turns)]
        for trial in trials:
            for i, t in enumerate(trial):
                all_words.append(t["words"])
                all_total.append(t.get("total_words", t["words"]))
                all_em.append(t["em_dashes"])
                all_open.append(t["opener"])
                all_close.append(t["closer"])
                per_turn_words[i].append(t["words"])
                (first_half if i < half else second_half).append(t["words"])
        n = len(all_words) or 1
        summary[cond] = {
            "avg_words": round(sum(all_words) / n, 1),          # prose (primary)
            "avg_total_words": round(sum(all_total) / n, 1),    # incl. code (secondary)
            "median_words": sorted(all_words)[len(all_words) // 2] if all_words else 0,
            "em_dashes_total": sum(all_em),
            "opener_rate": round(sum(all_open) / n, 3),
            "closer_rate": round(sum(all_close) / n, 3),
            "first_half_avg": round(sum(first_half) / (len(first_half) or 1), 1),
            "second_half_avg": round(sum(second_half) / (len(second_half) or 1), 1),
            "drift_pct": round((sum(second_half) / (len(second_half) or 1) -
                                sum(first_half) / (len(first_half) or 1)) /
                               (sum(first_half) / (len(first_half) or 1)) * 100, 1)
            if first_half else 0.0,
            "per_turn_avg_words": [round(sum(w) / (len(w) or 1), 1) for w in per_turn_words],
            "slope_words_per_turn": _slope([sum(w) / (len(w) or 1) for w in per_turn_words]),
            "replies_scored": n,
        }
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["bench", "drift"], default="bench",
                    help="bench: 4 conditions, mixed-difficulty prompts. "
                         "drift: top vs bottom only, 20 constant-difficulty prompts to isolate decay.")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Set ANTHROPIC_API_KEY in the environment.")

    if args.mode == "drift":
        prompts, conditions = LEVEL_PROMPTS, ["top", "bottom"]
    else:
        prompts, conditions = PROMPTS, CONDITIONS
    out_path = args.out or os.path.join(
        os.path.dirname(__file__), f"position_results_{args.mode}.json")

    jobs = [(c, t) for c in conditions for t in range(args.trials)]
    raw = {c: [None] * args.trials for c in conditions}
    print(f"[{args.mode}] Running {len(jobs)} conversations "
          f"({len(conditions)} conditions x {args.trials} trials x {len(prompts)} turns), "
          f"model={args.model}\n", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_conversation, api_key, args.model, c, prompts): (c, t)
                for c, t in jobs}
        for fut in as_completed(futs):
            c, t = futs[fut]
            raw[c][t] = fut.result()
            print(f"  done: {c} trial {t + 1}/{args.trials}", flush=True)

    summary = aggregate(raw, prompts)
    out = {"mode": args.mode, "model": args.model, "trials": args.trials,
           "prompts": prompts, "rules": RULES, "summary": summary, "raw": raw}
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print("\n=== SUMMARY (words = prose; tot = incl. code) ===")
    hdr = (f"{'cond':7} {'prose':>6} {'tot':>6} {'med':>5} {'em':>3} {'open':>5} {'close':>5} "
           f"{'1st_h':>6} {'2nd_h':>6} {'drift%':>6} {'slope':>6}")
    print(hdr)
    for c in conditions:
        s = summary[c]
        print(f"{c:7} {s['avg_words']:>6} {s['avg_total_words']:>6} {s['median_words']:>5} "
              f"{s['em_dashes_total']:>3} {s['opener_rate']:>5} {s['closer_rate']:>5} "
              f"{s['first_half_avg']:>6} {s['second_half_avg']:>6} {s['drift_pct']:>6} "
              f"{s['slope_words_per_turn']:>6}")
    print(f"\nFull results: {out_path}")


if __name__ == "__main__":
    main()
