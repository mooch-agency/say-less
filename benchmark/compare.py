#!/usr/bin/env python3
"""
compare.py — run ONE prompt through stock Claude Code and through Say Less.

The comparison artifact can't generate replies itself (a published page has no
model access), so this is the local half: give it a prompt, paste the two
replies back into the artifact's "Your own" tab.

Both arms run hermetically (--setting-sources project, see claude_turn), so the
Default arm is genuinely stock: no user CLAUDE.md, no user-scope plugins, no
user settings. Without that flag a personal CLAUDE.md saying "be concise"
silently shortens the baseline and understates the difference.

Usage:
  python3 benchmark/compare.py "Should I use UUIDs or integers for primary keys?"
  python3 benchmark/compare.py --model opus "..."      # default: sonnet
  python3 benchmark/compare.py --json "..."            # machine-readable
"""

import argparse
import json
import os
import tempfile

from drift_session import claude_turn, prose_words, total_words, _resolve_style_file

STYLE = "Say Less"


def run(prompt, style, model):
    with tempfile.TemporaryDirectory(prefix="compare_") as cwd:
        if style != "Default":
            src = _resolve_style_file(style)
            if src is None:
                raise SystemExit(f"style {style!r} not found in output-styles/ or versions/")
            sdir = os.path.join(cwd, ".claude", "output-styles")
            os.makedirs(sdir, exist_ok=True)
            with open(src) as f, open(os.path.join(sdir, "style.md"), "w") as g:
                g.write(f.read())
        reply, _ = claude_turn(prompt, style, model, cwd)
    return reply


def main():
    ap = argparse.ArgumentParser(description="One prompt, both arms, word counts.")
    ap.add_argument("prompt")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = ap.parse_args()

    default = run(args.prompt, "Default", args.model)
    sayless = run(args.prompt, STYLE, args.model)
    # Total words is the headline: it is the real reading load. Code is
    # content the reader still has to get through, and stripping it can
    # score a reply that explains in prose as LONGER than one that dumps a
    # code block. Prose is kept alongside as a diagnostic.
    dw, sw = total_words(default), total_words(sayless)
    dp, sp = prose_words(default), prose_words(sayless)

    if args.json:
        print(json.dumps({"prompt": args.prompt, "model": args.model,
                          "default": default, "sayless": sayless,
                          "default_words": dw, "sayless_words": sw}, indent=1))
        return

    cut = round((1 - sw / dw) * 100) if dw else 0
    bar = "=" * 72
    print(f"\n{bar}\nDEFAULT  ({dw} words, {dp} excl. code)\n{bar}\n{default.strip()}")
    print(f"\n{bar}\nSAY LESS  ({sw} words, {sp} excl. code)\n{bar}\n{sayless.strip()}")
    print(f"\n{bar}")
    if dw and sw:
        word = "shorter" if cut >= 0 else "longer"
        print(f"{abs(cut)}% {word} with Say Less: {dw} words -> {sw}.")
    print(f"{bar}\nPaste each reply into the artifact's \"Your own\" tab to see them side by side.\n")


if __name__ == "__main__":
    main()
