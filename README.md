# Say Less

Claude Code writes too much.

Say Less is a Claude Plugin that cuts word count by up to 81% and on average 59%.

![median words per reply: Default 84, Say Less 34](words-per-reply.svg)

## Before / after

Same prompt, same model, real benchmark output.

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

Biggest cut so far, same prompt and model (Opus): **"What git command discards all uncommitted changes in the working tree?"** Default: 112 words. Say Less: 21.

> `git checkout -- .` discards changes to tracked files in the working tree.
>
> To also remove untracked files: `git clean -fd`. For a full reset including staged changes: `git reset --hard HEAD`.

Raw data: `benchmark/glance_opus_v1_v2.json`.

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
python3 benchmark/spot.py "Say Less"
```

Prints 10 replies with word counts. No judges, no scores: read them and decide. Tweak the style file, rerun, compare.

## Why it's built this way

Examples set the length; rules alone don't. One soft length bound is load-bearing (remove it and replies creep back up). Prescribing report structure backfires. On Opus, verbosity drifts back over long sessions unless re-injected (optional hook: `benchmark/hooks/`).

Full findings, with data: [benchmark/RESEARCH.md](benchmark/RESEARCH.md), [benchmark/results/](benchmark/results/).

## Status

Dogfooding. The shipped style is `output-styles/say-less.md`; earlier drafts are in `versions/` with their benchmark numbers in `benchmark/results/`.
