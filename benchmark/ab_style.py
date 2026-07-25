#!/usr/bin/env python3
"""
ab_style.py — standardised A/B (or N-way) test for output-style variations.

Give it two or more style files. It runs the SAME prompts through headless
Claude under each style (as the system prompt), then measures:

  1. prose words  — terseness (lower = tighter). Code, commands, and link URLs
                    are excluded, since padding lives in prose, not content.
  2. completeness — an LLM judge scores 0-100 whether the answer still covers
                    everything the prompt requires, ignoring length/style.

Terser is only a win if completeness holds: an answer that got short by dropping
required content should score WORSE on completeness, not better. This lets you
compare any two wordings of a style and see the real trade, not just word count.

Headless Claude only, no API key. Each style file's body (YAML frontmatter
stripped) becomes the full system prompt via --system-prompt, so the style is
the only variable. MCP servers are disabled for a clean, fast, deterministic run.

Usage:
  python3 benchmark/ab_style.py STYLE_A.md STYLE_B.md [STYLE_C.md ...] \
      [--labels A B ...] [--prompts prompts.txt] [--trials 3] \
      [--model sonnet] [--workers 5] [--out results.json]

Examples:
  # current style vs an experimental edit
  python3 benchmark/ab_style.py say-less.md /tmp/say-less-experiment.md

  # three wordings, 5 trials each, custom prompt set
  python3 benchmark/ab_style.py v1.md v2.md v3.md --prompts my_prompts.txt --trials 5
"""

import argparse
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))

# Default mixed prompt set: facts (verbosity floor), decisions (where a terse
# style should bite), explainers, and multi-part prompts whose completeness is
# objectively checkable (ACID = 4 items, CAP = 3) so the judge can catch any
# required content a terser style drops. Override with --prompts.
DEFAULT_PROMPTS = [
    "What's the default PostgreSQL port?",
    "Should I use REST or GraphQL for a new internal API?",
    "What's the difference between TCP and UDP?",
    "How do I undo the last git commit but keep the changes staged?",
    "Is it worth adding Redis to cache database reads?",
    "Walk me through the OAuth2 authorization code flow.",
    "Name the four ACID properties in databases and define each in one line.",
    "What are the three guarantees in the CAP theorem? Define each.",
]

# --- prose-aware word counting (shared with position_test.py) ---------------

_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WORD = re.compile(r"[0-9A-Za-z]")


def prose_words(text):
    t = _FENCED.sub(" ", text)
    t = _MD_IMAGE.sub(" ", t)
    t = _MD_LINK.sub(r"\1", t)
    t = _INLINE_CODE.sub(" ", t)
    return sum(1 for tok in t.split() if _WORD.search(tok))


# --- style loading ----------------------------------------------------------

def load_style_body(path):
    """A style file's body: contents minus leading YAML frontmatter."""
    raw = open(path, encoding="utf-8").read()
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            raw = parts[2]
    body = raw.strip()
    if not body:
        raise SystemExit(f"Style file is empty after stripping frontmatter: {path}")
    return body


# --- headless claude --------------------------------------------------------

JUDGE_SYS = (
    "You are a strict grader. You are given a QUESTION and an ANSWER. Output "
    "ONLY a single integer from 0 to 100: how completely the answer covers the "
    "content the question requires. Judge ONLY completeness of required content "
    "(all parts of a multi-part question, correct key facts). IGNORE verbosity, "
    "length, style, and politeness entirely. A terse answer that covers "
    "everything scores 100. Output the integer and nothing else."
)


def claude(prompt, system, model):
    """One headless `claude -p` call. Returns stdout text ('' on timeout/fail)."""
    cmd = [
        "claude", "-p", prompt,
        "--system-prompt", system,
        "--model", model,
        "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config",
        "--exclude-dynamic-system-prompt-sections",
    ]
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # force subscription, not API billing
    try:
        # stdin=DEVNULL guards CORRECTNESS, not speed. capture_output only
        # redirects stdout and stderr, so stdin stays inherited, and `claude -p`
        # reads whatever is there and APPENDS it to the prompt. Harmless from a
        # terminal, silently rewrites every benchmarked question from a pipe,
        # heredoc, CI or cron.
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                           stdin=subprocess.DEVNULL, env=env)
    except subprocess.TimeoutExpired:
        return ""
    return r.stdout.strip()


def judge_completeness(question, answer, model):
    if not answer:
        return 0
    # Retry on parse failure or an implausible 0 (a non-empty answer to these
    # prompts is never 0% complete; a spurious 0 is a judge misfire, so re-ask).
    last = -1
    for _ in range(3):
        out = claude(f"QUESTION:\n{question}\n\nANSWER:\n{answer}", JUDGE_SYS, model)
        m = re.findall(r"\d+", out)
        if m:
            last = max(0, min(100, int(m[0])))
            if last > 0:
                return last
    return last


def run_cell(label, system, prompt, model):
    answer = claude(prompt, system, model)
    return {
        "label": label,
        "prompt": prompt,
        "words": prose_words(answer),
        "completeness": judge_completeness(prompt, answer, model),
        "answer": answer,
    }


# --- run --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="A/B test output-style variations.")
    ap.add_argument("styles", nargs="+", help="Two or more style .md files to compare.")
    ap.add_argument("--labels", nargs="+", help="Labels per style (default: filename).")
    ap.add_argument("--prompts", help="File with one prompt per line (default: built-in set).")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--out", default=os.path.join(HERE, "ab_results.json"))
    args = ap.parse_args()

    if len(args.styles) < 2:
        ap.error("give at least two style files to compare")

    labels = args.labels or [os.path.splitext(os.path.basename(s))[0] for s in args.styles]
    if len(labels) != len(args.styles):
        ap.error("number of --labels must match number of style files")
    if len(set(labels)) != len(labels):
        ap.error("labels must be unique")

    bodies = {lab: load_style_body(s) for lab, s in zip(labels, args.styles)}

    if args.prompts:
        prompts = [ln.strip() for ln in open(args.prompts, encoding="utf-8")
                   if ln.strip()]
    else:
        prompts = DEFAULT_PROMPTS

    jobs = [(lab, bodies[lab], p)
            for lab in labels for p in prompts for _ in range(args.trials)]
    print(f"Running {len(jobs)} answer+judge pairs "
          f"({len(labels)} styles x {len(prompts)} prompts x {args.trials} trials), "
          f"model={args.model}", flush=True)
    print(f"styles: {', '.join(labels)}\n", flush=True)

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_cell, lab, sysp, p, args.model)
                for (lab, sysp, p) in jobs]
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            print(f"  {done}/{len(jobs)} done", flush=True)

    # Aggregate per style.
    summary = {}
    for lab in labels:
        r = [x for x in rows if x["label"] == lab]
        w = [x["words"] for x in r]
        c = [x["completeness"] for x in r if x["completeness"] >= 0]
        summary[lab] = {
            "avg_words": round(sum(w) / len(w), 1) if w else 0,
            "avg_completeness": round(sum(c) / len(c), 1) if c else None,
            "n": len(r),
        }

    # Per-prompt breakdown.
    per_prompt = []
    for p in prompts:
        row = {"prompt": p[:45]}
        for lab in labels:
            wl = [x["words"] for x in rows if x["label"] == lab and x["prompt"] == p]
            cl = [x["completeness"] for x in rows
                  if x["label"] == lab and x["prompt"] == p and x["completeness"] >= 0]
            row[f"{lab}__w"] = round(sum(wl) / len(wl), 1) if wl else 0
            row[f"{lab}__c"] = round(sum(cl) / len(cl), 1) if cl else 0
        per_prompt.append(row)

    with open(args.out, "w") as f:
        json.dump({"styles": dict(zip(labels, args.styles)), "summary": summary,
                   "per_prompt": per_prompt, "model": args.model,
                   "trials": args.trials, "prompts": prompts, "rows": rows},
                  f, indent=2)

    print("\n=== SUMMARY (words = prose, lower = terser; complete = 0-100, higher = better) ===")
    print(f"{'style':20} {'avg_words':>10} {'avg_complete':>13} {'n':>4}")
    for lab in labels:
        s = summary[lab]
        print(f"{lab:20} {s['avg_words']:>10} {str(s['avg_completeness']):>13} {s['n']:>4}")

    print("\n=== PER PROMPT ===")
    hdr = f"{'prompt':47}"
    for lab in labels:
        hdr += f" {lab[:8]+'_w':>10} {lab[:8]+'_c':>10}"
    print(hdr)
    for r in per_prompt:
        line = f"{r['prompt']:47}"
        for lab in labels:
            line += f" {r[f'{lab}__w']:>10} {r[f'{lab}__c']:>10}"
        print(line)
    print(f"\nFull results: {args.out}")


if __name__ == "__main__":
    main()
