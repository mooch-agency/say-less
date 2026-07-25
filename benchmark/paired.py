#!/usr/bin/env python3
"""
paired.py — the number behind the README's "63% average, 86% best" claim.

N held-out prompts x K trials, two arms (baseline vs a named style), all
hermetic, total_words. Per-prompt paired comparison (same prompt, same
trial count, both arms), not two separate unpaired batches: Default's
per-prompt spread is large enough that unpaired runs have produced wrong
conclusions before (see benchmark/results/2026-07-hermetic-baseline.md).

Reuses spot.py's held-out prompt set so this number and spot.py's day-to-day
numbers stay comparable.

Usage:
  python3 benchmark/paired.py                                # Default vs Say Less, 10 prompts, 3 trials, sonnet
  python3 benchmark/paired.py --style "Say Less v3" --trials 5 --model claude-opus-4-8
  python3 benchmark/paired.py --out /tmp/paired.json          # keep the raw per-call counts
"""

import argparse
import json
import statistics
import tempfile
from concurrent.futures import ThreadPoolExecutor

from drift_session import claude_turn, total_words
from spot import PROMPTS


def gen(style, prompt, model):
    with tempfile.TemporaryDirectory(prefix="paired_") as cwd:
        reply, _ = claude_turn(prompt, style, model, cwd)
    return total_words(reply)


def main():
    ap = argparse.ArgumentParser(description="Paired N-prompt x K-trial benchmark, hermetic, total_words.")
    ap.add_argument("--style", default="Say Less", help='Output-style name (frontmatter name:).')
    ap.add_argument("--baseline", default="Default")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("-n", type=int, default=len(PROMPTS), help="How many prompts (default all 10).")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", help="Write raw per-prompt, per-trial word counts to this JSON path.")
    args = ap.parse_args()

    prompts = PROMPTS[: args.n]
    n, k = len(prompts), args.trials
    # baseline block first, then style block; each block is prompts-major,
    # trials-minor, so counts[:n*k] / counts[n*k:] splits cleanly below.
    jobs = [(args.baseline, p) for p in prompts for _ in range(k)] + \
           [(args.style, p) for p in prompts for _ in range(k)]

    print(f"Paired benchmark: {args.baseline!r} vs {args.style!r}, {n} prompts x {k} trials, "
          f"{args.model}, {len(jobs)} calls total.\n")

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        counts = list(ex.map(lambda j: gen(j[0], j[1], args.model), jobs))

    baseline_counts, style_counts = counts[: n * k], counts[n * k:]

    raw = {"baseline": {}, "style": {}, "meta": {
        "baseline_label": args.baseline, "style_label": args.style,
        "trials": k, "model": args.model}}
    per_prompt_pct, baseline_medians, style_medians = [], [], []
    for i, p in enumerate(prompts):
        b = baseline_counts[i * k:(i + 1) * k]
        s = style_counts[i * k:(i + 1) * k]
        bm, sm = statistics.median(b), statistics.median(s)
        baseline_medians.append(bm)
        style_medians.append(sm)
        raw["baseline"][p], raw["style"][p] = b, s
        pct = (1 - sm / bm) * 100 if bm else 0.0
        per_prompt_pct.append(pct)
        label = p.splitlines()[0][:58]
        print(f"{label:<60} {bm:>4.0f} -> {sm:>4.0f}  {pct:+.0f}%")

    wins = sum(1 for pct in per_prompt_pct if pct > 0)
    b_med, s_med = statistics.median(baseline_medians), statistics.median(style_medians)
    overall = (1 - s_med / b_med) * 100 if b_med else 0.0
    print(f"\n{args.baseline}: median {b_med:.0f}, mean {statistics.mean(baseline_medians):.1f}")
    print(f"{args.style}: median {s_med:.0f}, mean {statistics.mean(style_medians):.1f}")
    print(f"Shorter on {wins}/{n} prompts. Per-prompt cut range "
          f"{min(per_prompt_pct):+.0f}% to {max(per_prompt_pct):+.0f}%.")
    print(f"Overall (median of medians): {overall:.0f}% shorter.")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(raw, f, indent=2)
        print(f"\nRaw counts written to {args.out}")


if __name__ == "__main__":
    main()
