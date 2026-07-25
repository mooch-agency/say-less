# Say Less

Claude Code writes too much.

Say Less is a Claude Plugin that cuts word count by up to 86% and on average 63%.

![median words per reply: Default 129, Say Less 42](words-per-reply.svg)

## Before / after

Same prompt, same model, real benchmark output. The Default side is stock Claude Code with no user settings or memory files loaded.

> **Q: This SQL is slow on 10M rows:** `SELECT * FROM events WHERE DATE(created_at) = '2026-07-01';`

<table>
<tr>
<td width="50%" valign="top">
<b>Default</b> (98 words)
<blockquote>
The problem is <code>DATE(created_at)</code>, wrapping a column in a function prevents the database from using an index on <code>created_at</code>.
<p><b>Fix: use a range instead</b></p>
<pre><code>SELECT * FROM events
WHERE created_at &gt;= '2026-07-01'
  AND created_at &lt;  '2026-07-02';
</code></pre>
<p>This is <b>sargable</b>, the index on <code>created_at</code> can be used directly.</p>
<p><b>Why it's faster:</b></p>
<ul>
<li>Original: evaluates <code>DATE()</code> on every row (full table scan even with an index)</li>
<li>Fixed: the optimizer can do an index range scan and skip irrelevant rows entirely</li>
</ul>
<p><b>Also make sure you have the index:</b></p>
<pre><code>CREATE INDEX idx_events_created_at ON events (created_at);
</code></pre>
<p>If you're selecting all columns (<code>SELECT *</code>) on 10M rows, also consider whether you need all columns, projecting only the columns you need reduces I/O significantly, especially if the table is wide.</p>
</blockquote>
</td>
<td width="50%" valign="top">
<b>Say Less</b> (41 words)
<blockquote>
<code>DATE(created_at)</code> wraps the column in a function, making any index on <code>created_at</code> unusable. Use a range instead:
<pre><code>SELECT * FROM events
WHERE created_at &gt;= '2026-07-01' AND created_at &lt; '2026-07-02';
</code></pre>
<p>Then ensure you have an index on <code>created_at</code>. Also drop the <code>*</code> and select only the columns you need, returning 10M-row-wide results is expensive regardless of the scan.</p>
</blockquote>
</td>
</tr>
</table>

Same findings, 58% less to read.

See all 10 side by side, and paste your own: **[the comparison page](https://claude.ai/code/artifact/43a96ba4-2434-40ea-8b8c-dfab09852fd1)**.

## Install

```bash
claude plugin marketplace add gichigi/say-less
claude plugin install say-less@say-less
```

Active immediately, no config. To turn it off: `claude plugin disable say-less`.

Prefer a plain output style? Copy the one file instead:

```bash
git clone https://github.com/gichigi/say-less && cd say-less
cp output-styles/say-less.md ~/.claude/output-styles/
```

Then `/config` → Output style → **Say Less**. Coding behavior is unchanged either way; only the reply style changes.

## Test it yourself

```bash
python3 benchmark/serve_compare.py     # localhost:8787, type a prompt, watch both stream
python3 benchmark/compare.py "..."     # same thing, one prompt, in the terminal
python3 benchmark/spot.py "Say Less"   # 10 fixed prompts with word counts
```

Both arms run hermetically, so your own `CLAUDE.md` and plugins can't shorten either side. No judges, no scores: read them and decide.

## Why it's built this way

Examples set the length; rules alone don't. One soft length bound is load-bearing (remove it and replies creep back up). Prescribing report structure backfires. On Opus, verbosity drifts back over long sessions unless re-injected (optional hook: `benchmark/hooks/`).

Numbers come from 10 prompts run 3 times per arm, all hermetic (`--setting-sources project`), so a personal `CLAUDE.md` or an installed plugin can't quietly shorten either side. Say Less was shorter on all 10, by 41% to 86%. Counts include code, because code is still reading: stripping it scored Say Less as *longer* on the Docker prompt while it actually produced half the reading. Computed by `total_words`, never by a model.

Full findings, with data: [benchmark/RESEARCH.md](benchmark/RESEARCH.md), [benchmark/results/](benchmark/results/).

## Status

Dogfooding. The shipped style is `output-styles/say-less.md`; earlier drafts are in `versions/` with their benchmark numbers in `benchmark/results/`.
