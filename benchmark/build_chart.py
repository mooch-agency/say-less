#!/usr/bin/env python3
"""
Say Less verbosity benchmark.

Same 6 prompts, each answered twice by a general-purpose Claude agent:
  - "default": no output style (baseline Claude verbosity)
  - "say less": the Say Less output style injected

Word counts are from a single representative run per prompt/condition.
Generates a grouped bar chart (verbosity.svg) next to this script.
"""

import os

# (short label, default words, say-less words)
DATA = [
    ("PG port",        41,   1),
    ("TCP vs UDP",     245,  90),
    ("PG vs SQLite",   330, 125),
    ("Event sourcing", 430, 200),
    ("Rate limiting",  600, 260),
    ("Rust vs Go",     370, 170),
]

default_total = sum(d for _, d, _ in DATA)
sayless_total = sum(s for _, _, s in DATA)
overall_pct = round((default_total - sayless_total) / default_total * 100)

W, H = 820, 480
ml, mr, mt, mb = 70, 20, 80, 90
plot_w = W - ml - mr
plot_h = H - mt - mb
base_y = mt + plot_h
ymax = 640
yscale = plot_h / ymax

C_DEFAULT = "#94a3b8"
C_SAYLESS = "#10b981"
C_TEXT = "#334155"
C_GRID = "#e2e8f0"

n = len(DATA)
slot = plot_w / n
bar_w = 40
gap = 8
pair_w = bar_w * 2 + gap

s = []
s.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'font-family="-apple-system, Segoe UI, Roboto, sans-serif">')
s.append(f'<text x="{ml}" y="34" font-size="20" font-weight="700" fill="{C_TEXT}">'
         f'Output length: default Claude vs Say Less</text>')
s.append(f'<text x="{ml}" y="56" font-size="13" fill="#64748b">'
         f'Words per answer, 6 prompts, one run each. '
         f'~{overall_pct}% fewer words overall ({sayless_total:,} vs {default_total:,}).</text>')

for gv in range(0, ymax + 1, 160):
    gy = base_y - gv * yscale
    s.append(f'<line x1="{ml}" y1="{gy:.1f}" x2="{W-mr}" y2="{gy:.1f}" stroke="{C_GRID}" stroke-width="1"/>')
    s.append(f'<text x="{ml-8}" y="{gy+4:.1f}" font-size="11" fill="#94a3b8" text-anchor="end">{gv}</text>')

for i, (label, dv, sv) in enumerate(DATA):
    cx = ml + slot * i + slot / 2
    x1 = cx - pair_w / 2
    x2 = x1 + bar_w + gap
    dh = dv * yscale
    sh = sv * yscale
    s.append(f'<rect x="{x1:.1f}" y="{base_y-dh:.1f}" width="{bar_w}" height="{dh:.1f}" fill="{C_DEFAULT}" rx="3"/>')
    s.append(f'<rect x="{x2:.1f}" y="{base_y-sh:.1f}" width="{bar_w}" height="{sh:.1f}" fill="{C_SAYLESS}" rx="3"/>')
    s.append(f'<text x="{x1+bar_w/2:.1f}" y="{base_y-dh-6:.1f}" font-size="11" fill="{C_TEXT}" text-anchor="middle">{dv}</text>')
    s.append(f'<text x="{x2+bar_w/2:.1f}" y="{base_y-sh-6:.1f}" font-size="11" font-weight="700" fill="{C_SAYLESS}" text-anchor="middle">{sv}</text>')
    s.append(f'<text x="{cx:.1f}" y="{base_y+18:.1f}" font-size="11.5" fill="{C_TEXT}" text-anchor="middle">{label}</text>')

s.append(f'<line x1="{ml}" y1="{base_y:.1f}" x2="{W-mr}" y2="{base_y:.1f}" stroke="{C_TEXT}" stroke-width="1.5"/>')

lx, ly = ml, H - 26
s.append(f'<rect x="{lx}" y="{ly-10}" width="13" height="13" fill="{C_DEFAULT}" rx="2"/>')
s.append(f'<text x="{lx+19}" y="{ly+1}" font-size="12.5" fill="{C_TEXT}">Default Claude</text>')
s.append(f'<rect x="{lx+150}" y="{ly-10}" width="13" height="13" fill="{C_SAYLESS}" rx="2"/>')
s.append(f'<text x="{lx+169}" y="{ly+1}" font-size="12.5" fill="{C_TEXT}">Say Less</text>')

s.append('</svg>')

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verbosity.svg")
with open(out_path, "w") as f:
    f.write("\n".join(s))

print(f"default_total={default_total}  sayless_total={sayless_total}  overall_reduction={overall_pct}%")
for label, dv, sv in DATA:
    print(f"{label:16} {dv:4} -> {sv:4}  ({round((dv-sv)/dv*100)}% less)")
