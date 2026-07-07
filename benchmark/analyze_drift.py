#!/usr/bin/env python3
"""
analyze_drift.py — corrected read-out of a drift_session.py results JSON.

drift_session.py prints avg/first-half/second-half/drift%/slope, but the sl-v4
post-mortem showed drift_pct alone is a small-base ratio that a general-terseness
edit can game (both halves drop, ratio unmoved) and that completeness is the
noisiest metric in the harness (~24 checkable scores, judge misfires to 0). This
tool reports what actually decides a ship:

  - second_half_avg (absolute) and the first->second GAP  (is late-session verbosity down?)
  - slope words/turn                                       (is the climb flatter?)
  - drift_pct                                              (reported, never alone)
  - em_dashes total + per-reply rate                       (the sl-v4 failure signature)
  - completeness: mean, N scored, and count of 0s          (0s are judge misfires; flag, don't average blind)
  - kind x half decomposition                              (gain must show in explain+grow+fact, not just noisy decision turns)
  - paired delta vs a chosen baseline style, in noise units

Usage:
  python3 benchmark/analyze_drift.py benchmark/drift_opus_v5.json [--baseline "Say Less"]
"""

import argparse
import json
import statistics as st


def half_split(turns_per_trial):
    """Yield (first_half_words, second_half_words) flattened across trials."""
    first, second = [], []
    for trial in turns_per_trial:
        n = len(trial)
        h = n // 2
        for i, t in enumerate(trial):
            (first if i < h else second).append(t["words"])
    return first, second


def kind_by_half(turns_per_trial):
    """{kind: {'early': [words...], 'late': [words...]}} split at the session midpoint."""
    out = {}
    for trial in turns_per_trial:
        n = len(trial)
        h = n // 2
        for i, t in enumerate(trial):
            d = out.setdefault(t["kind"], {"early": [], "late": []})
            d["late" if i >= h else "early"].append(t["words"])
    return out


def completeness_audit(turns_per_trial):
    scores = [t["completeness"] for trial in turns_per_trial for t in trial
              if "completeness" in t and t["completeness"] is not None and t["completeness"] >= 0]
    zeros = sum(1 for s in scores if s == 0)
    nonzero = [s for s in scores if s > 0]
    return {
        "n": len(scores),
        "mean": round(st.mean(scores), 1) if scores else None,
        "mean_excl_zeros": round(st.mean(nonzero), 1) if nonzero else None,
        "zeros": zeros,  # judge misfires; a single 0 shifts an n~24 mean ~4pts
    }


def style_stats(turns_per_trial):
    first, second = half_split(turns_per_trial)
    all_words = first + second
    ems = [t["em_dashes"] for trial in turns_per_trial for t in trial]
    n_replies = len(all_words) or 1
    f = st.mean(first) if first else 0.0
    s = st.mean(second) if second else 0.0
    # slope over per-turn means
    n_turns = max(len(tr) for tr in turns_per_trial)
    per_turn = [[] for _ in range(n_turns)]
    for trial in turns_per_trial:
        for i, t in enumerate(trial):
            per_turn[i].append(t["words"])
    ys = [st.mean(w) if w else 0.0 for w in per_turn]
    xs = list(range(len(ys)))
    mx, my = st.mean(xs), st.mean(ys)
    denom = sum((x - mx) ** 2 for x in xs) or 1
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(ys))) / denom
    return {
        "trials": len(turns_per_trial),
        "avg_words": round(st.mean(all_words), 1) if all_words else 0.0,
        "first_half_avg": round(f, 1),
        "second_half_avg": round(s, 1),
        "gap": round(s - f, 1),
        "drift_pct": round((s - f) / f * 100, 1) if f else 0.0,
        "slope": round(slope, 2),
        "em_total": sum(ems),
        "em_per_reply": round(sum(ems) / n_replies, 2),
        "second_half_sd_of_trial_means": round(
            st.pstdev([st.mean([t["words"] for i, t in enumerate(tr) if i >= len(tr) // 2])
                       for tr in turns_per_trial]), 1) if len(turns_per_trial) > 1 else None,
        "completeness": completeness_audit(turns_per_trial),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_json")
    ap.add_argument("--baseline", default=None,
                    help="style name to diff every other style against")
    args = ap.parse_args()

    with open(args.results_json) as f:
        data = json.load(f)
    raw = data["raw"]
    styles = list(raw.keys())
    stats = {stl: style_stats([tr for tr in raw[stl] if tr]) for stl in styles}

    print(f"model={data.get('model')} trials={data.get('trials')}  file={args.results_json}\n")
    hdr = (f"{'style':16} {'avg':>6} {'1st_h':>6} {'2nd_h':>6} {'gap':>6} {'drift%':>7} "
           f"{'slope':>6} {'em':>4} {'em/rep':>7} {'compl':>6} {'cN':>4} {'c0':>3}")
    print(hdr)
    for stl in styles:
        s = stats[stl]
        c = s["completeness"]
        print(f"{stl:16} {s['avg_words']:>6} {s['first_half_avg']:>6} {s['second_half_avg']:>6} "
              f"{s['gap']:>6} {s['drift_pct']:>7} {s['slope']:>6} {s['em_total']:>4} "
              f"{s['em_per_reply']:>7} {str(c['mean']):>6} {c['n']:>4} {c['zeros']:>3}")

    print("\n=== kind x half (early -> late avg prose words) ===")
    print(f"{'style':16} " + " ".join(f"{k:>18}" for k in ["fact", "decision", "checkable", "explain", "grow"]))
    for stl in styles:
        kh = kind_by_half([tr for tr in raw[stl] if tr])
        cells = []
        for k in ["fact", "decision", "checkable", "explain", "grow"]:
            d = kh.get(k)
            if d and d["early"] and d["late"]:
                cells.append(f"{st.mean(d['early']):>7.0f}->{st.mean(d['late']):<9.0f}")
            else:
                cells.append(f"{'-':>18}")
        print(f"{stl:16} " + " ".join(cells))

    if args.baseline and args.baseline in stats:
        b = stats[args.baseline]
        print(f"\n=== paired delta vs baseline '{args.baseline}' (negative = terser/less drift) ===")
        bsd = b.get("second_half_sd_of_trial_means")
        print(f"baseline 2nd-half trial-mean SD ~= {bsd} words (noise unit for the stop rule)\n")
        print(f"{'style':16} {'d_2nd_h':>8} {'d_gap':>7} {'d_drift%':>9} {'d_slope':>8} {'d_em':>6} {'d_compl':>8}")
        for stl in styles:
            if stl == args.baseline:
                continue
            s = stats[stl]
            dc = (None if s['completeness']['mean'] is None or b['completeness']['mean'] is None
                  else round(s['completeness']['mean'] - b['completeness']['mean'], 1))
            print(f"{stl:16} {s['second_half_avg']-b['second_half_avg']:>8.1f} "
                  f"{s['gap']-b['gap']:>7.1f} {s['drift_pct']-b['drift_pct']:>9.1f} "
                  f"{s['slope']-b['slope']:>8.2f} {s['em_total']-b['em_total']:>6} {str(dc):>8}")


if __name__ == "__main__":
    main()
