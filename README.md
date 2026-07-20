# Say Less

Claude Code outputs so much you stop reading it. Then mistakes slip past you.

Say Less is an output style: full reasoning, terse replies. The answer first, at a length you'll actually read.

![median words per reply: Default 84, Say Less 34](words-per-reply.svg)

## Before / after

Same prompt, same model. Real benchmark output, not a mock-up.

> **Q: This SQL is slow on 10M rows:** `SELECT * FROM events WHERE DATE(created_at) = '2026-07-01';`

<table>
<tr>
<td width="50%" valign="top">
<b>Default</b> (83 words)
<blockquote>
Two problems: <code>DATE(created_at)</code> wraps the column in a function, which prevents Postgres from using an index on <code>created_at</code>. And <code>SELECT *</code> pulls every column unnecessarily.
<p><b>Fix: use a range condition instead.</b> This is sargable, Postgres can use a btree index on <code>created_at</code> directly.</p>
<p><b>Add an index if you don't have one.</b></p>
<p>If you filter by other columns too (e.g. <code>user_id</code>), a composite index with <code>created_at</code> last tends to work better.</p>
<p><b>If <code>SELECT *</code> is real:</b> replace it with only the columns you need. On 10M rows this matters a lot for I/O.</p>
</blockquote>
</td>
<td width="50%" valign="top">
<b>Say Less</b> (34 words)
<blockquote>
<code>DATE()</code> wraps the column, so no index is used. Rewrite as a range:
<pre><code>SELECT * FROM events
WHERE created_at &gt;= '2026-07-01'
  AND created_at &lt;  '2026-07-02';
</code></pre>
Also add an index on <code>created_at</code> if you don't have one, and replace <code>SELECT *</code> with named columns so Postgres can use a covering index.
</blockquote>
</td>
</tr>
</table>

Same three findings. A third of the reading.

## Install

```bash
git clone https://github.com/gichigi/say-less && cd say-less
cp say-less-v3.2.md ~/.claude/output-styles/
```

Then `/config` → Output style → **Say Less v3.2** (or `"outputStyle": "Say Less v3.2"` in settings.json). Coding behaviour is untouched; only the reply style changes.

## Test it yourself

```bash
python3 benchmark/spot.py "Say Less v3.2"   # 10 prompts, prints replies + word counts
```

No judges, no scores; read the outputs and decide. Tweak the style file, rerun, compare.

## Why it's built this way

Everything in the style is there because an experiment picked it. The short version: examples set the length (rules don't), one soft length bound is load-bearing, structure prescriptions backfire, and verbosity drifts back over long Opus sessions unless you re-inject (optional hook in `benchmark/hooks/`). Full findings with data: [benchmark/RESEARCH.md](benchmark/RESEARCH.md) and [benchmark/results/](benchmark/results/).

## Status

Dogfooding v3.2. Not yet packaged as a plugin.
