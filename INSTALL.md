# Install

Two ways in: the plugin, which updates itself, or the style file on its own.

Pick the section for where you run Claude Code. If you're setting this up for a
team, or you use more than one of these, skip to
[Any surface, committed to the repo](#any-surface-committed-to-the-repo).

## Terminal

Inside a Claude Code session, run:

```
/plugin marketplace add mooch-agency/say-less
```

```
/plugin install say-less@say-less
```

Restart the session, or run `/reload-plugins` to skip the restart.

Prefer the shell, or scripting it? Same thing from a prompt, no session needed:

```bash
claude plugin marketplace add mooch-agency/say-less
claude plugin install say-less@say-less
```

## Desktop app

Same two commands as the terminal, run inside a Code session:

```
/plugin marketplace add mooch-agency/say-less
```

```
/plugin install say-less@say-less
```

If the app tells you `/plugin` isn't available in this environment, use the
plugin browser in the desktop app, or install the
[`claude` CLI](#installing-the-cli) and use the shell commands above.

> **Heads up:** the desktop app does **not** put the `claude` CLI on your PATH.
> If you paste shell instructions into a desktop session and get
> `command not found: claude`, that's this &mdash; nothing is broken. Install the
> CLI, or use `/plugin`.

## Web

On [claude.ai/code](https://claude.ai/code), `/plugin` isn't available and
user-scoped installs don't survive between cloud sessions, because each one
starts from a fresh sandbox. Commit the config to the repo instead &mdash; see
below.

## Any surface, committed to the repo

Put this in `.claude/settings.json` in your repo and commit it:

```json
{
  "extraKnownMarketplaces": {
    "say-less": {
      "source": { "source": "github", "repo": "mooch-agency/say-less" }
    }
  },
  "enabledPlugins": { "say-less@say-less": true }
}
```

Every session opened on that repo picks it up, cloud or local, and so does
everyone else on the team. This is the only route that works on the web, and
it's the most reliable one everywhere else.

If the file already exists, merge these two keys into it rather than replacing
it.

## Installing the CLI

Only needed if you want the shell commands and don't have `claude` yet. The
native installer is the recommended route and keeps itself updated:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

<details>
<summary>Windows, Homebrew, npm</summary>

```powershell
irm https://claude.ai/install.ps1 | iex          # Windows PowerShell
```

```bash
brew install --cask claude-code                  # Homebrew (manual upgrades)
npm install -g @anthropic-ai/claude-code         # npm (needs Node.js 22+)
```

</details>

## After installing

Active in new sessions, no config. The plugin applies the style itself
(`force-for-plugin: true`), so it overrides whatever output style you had
selected while it's enabled.

Turn it off:

```
/plugin disable say-less
```

Or from a shell: `claude plugin disable say-less`, or
`claude plugin uninstall say-less@say-less` to remove it outright.

## Style file only

No plugin, no auto-apply, identical style text:

```bash
git clone https://github.com/mooch-agency/say-less && cd say-less
cp output-styles/say-less.md ~/.claude/output-styles/
```

Then `/config` → Output style → **Say Less**.

## Check it's working

Replies should open with the answer and stay short. A quick smoke test:

```bash
python3 benchmark/spot.py "Say Less"
```

Prints 10 replies with word counts. Median should land around 40-60 words (code included); default Claude Code runs 3-4x longer, around 170.

## If it's not working

- `/plugin list` (or `claude plugin list`) should show `say-less@say-less` enabled.
- Plugins load at session start, so restart your session after installing.
- `command not found: claude` means you're on a surface without the CLI on PATH, most likely the desktop app. Use `/plugin` instead, or [install the CLI](#installing-the-cli).
- On the web, a user-scoped install won't persist. Use the [committed config](#any-surface-committed-to-the-repo).
- If a project sets `"outputStyle"` in its `.claude/settings.json`, that project is pinning a style; the plugin's `force-for-plugin` should still win, but check there first if output looks unchanged.
- The `claude` CLI authenticates separately from the Claude Desktop app. If `claude -p` says "Not logged in", run `claude auth login` (`/login` only works inside the `claude` REPL, not at a shell prompt).
