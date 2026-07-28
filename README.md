# Say Less

Claude Code writes too much. Say Less is a Claude Code plugin that cuts word
count by a median 71%, up to 80%. Reasoning and coding behavior are unchanged;
only the reply gets shorter.

![median words per reply: Claude Code 171, Claude Code with Say Less 50](words-per-reply.svg)

**Status: beta.** It works and it's measured, but the style is still moving.
Try it on real work and tell me where it falls short.

## See the difference

Same question, same model. Both arms run hermetically, so no personal
`CLAUDE.md` or installed plugin can shorten either side. The style is the only
variable.

> **Q: What's the difference between Git and GitHub?**

<table>
<tr>
<th align="left" width="50%">Claude Code &middot; 122 words</th>
<th align="left" width="50%">Claude Code with Say Less &middot; 56 words</th>
</tr>
<tr>
<td valign="top">

Git and GitHub serve different purposes:

**Git** is a version control system &mdash; a command-line tool (or library) that tracks changes to files over time, lets you branch, merge, and revert code. It runs locally on your machine and doesn't require the internet or any company's servers.

**GitHub** is a cloud hosting platform built around Git. It stores your Git repositories remotely and adds collaboration features on top: pull requests, issue tracking, code review, CI/CD, project boards, etc.

Analogy: Git is like the concept of "saving drafts and tracking edits" of a document; GitHub is like Google Drive &mdash; a place to host those files online and collaborate with others. Alternatives to GitHub include GitLab and Bitbucket, which also use Git under the hood.

</td>
<td valign="top">

Git is a version control tool: it tracks changes to files locally on your machine (commits, branches, history).

GitHub is a hosting service built around Git: it stores your Git repos in the cloud and adds collaboration features (pull requests, issues, code review, CI). You could use Git without ever touching GitHub (or use GitLab/Bitbucket instead).

</td>
</tr>
</table>

Same answer, 54% less to read. Ask it your own question and watch both stream:
`python3 benchmark/serve_compare.py`.

## Install

Paste this into any Claude Code session:

```
Install the Say Less plugin: run `claude plugin marketplace add mooch-agency/say-less` then `claude plugin install say-less@say-less`, then verify with `claude plugin list`. Finish by telling me to restart my session and ask any question to see the style.
```

Or run it yourself:

```bash
claude plugin marketplace add mooch-agency/say-less
claude plugin install say-less@say-less
```

Active immediately, no config. To turn it off: `claude plugin disable say-less`.
Verification and troubleshooting: [INSTALL.md](INSTALL.md). Prefer a
plain output style with no plugin? INSTALL.md has the copy-file version too.

## Test it yourself

```bash
python3 benchmark/serve_compare.py     # localhost:8787, ask anything, watch both stream
python3 benchmark/compare.py "..."     # same thing, one prompt, in the terminal
python3 benchmark/spot.py "Say Less"   # 10 fixed prompts with word counts
```

Both arms run hermetically, so your own `CLAUDE.md` and plugins can't shorten either side. No judges, no scores: read them and decide.

## Why it's built this way

Examples set the length; rules alone don't. One soft length bound is load-bearing (remove it and replies creep back up). Prescribing report structure backfires. On Opus, verbosity drifts back over long sessions unless re-injected (optional hook: `benchmark/hooks/`).

Numbers come from 10 prompts run 3 times per arm, all hermetic (`--setting-sources project`), so a personal `CLAUDE.md` or an installed plugin can't quietly shorten either side. Say Less was shorter on all 10, by 61% to 80%. Counts include code, because code is still reading: stripping it scored Say Less as *longer* on the Docker prompt while it actually produced half the reading. Computed by `total_words`, never by a model.

Full findings, with data: [benchmark/RESEARCH.md](benchmark/RESEARCH.md), [benchmark/results/](benchmark/results/). Reproduce the headline number: `python3 benchmark/paired.py`.

## Feedback

Hit a reply that stayed too long, or worse, dropped something it should have
kept? Open an issue with the prompt that caused it. Both failure modes are
useful to hear about; that's what the beta is for.

## Status

The shipped style is `output-styles/say-less.md`; earlier drafts are in
`versions/` with their benchmark numbers in `benchmark/results/`.
