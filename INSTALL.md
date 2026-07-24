# Install

The repo is private, so you need read access first. Current access: `gichigi` (admin), `nataliegent` (read).

## Plugin (recommended)

```bash
gh auth login          # once, if you haven't
claude plugin marketplace add gichigi/say-less
claude plugin install say-less@say-less
```

Active immediately in new sessions, no config. The plugin applies the style itself (`force-for-plugin: true`), so it overrides whatever output style you had selected while it's enabled.

Turn it off:

```bash
claude plugin disable say-less     # or: claude plugin uninstall say-less@say-less
```

## Style file only

No plugin, no auto-apply, identical style text:

```bash
git clone https://github.com/gichigi/say-less && cd say-less
cp output-styles/say-less.md ~/.claude/output-styles/
```

Then `/config` → Output style → **Say Less**.

## Check it's working

Replies should open with the answer and stay short. A quick smoke test:

```bash
python3 benchmark/spot.py "Say Less"
```

Prints 10 replies with word counts. Median should land around 34 prose words; default Claude Code is around 84.

### Verified on install (2026-07-24, Sonnet)

The plugin path is confirmed working, not just assumed:

- `spot.py "Say Less"`: median 35 prose words, range 1-86.
- With `outputStyle` explicitly set to `"Default"` in a clean directory, replies still came back at 30-37 words leading with the answer, so `force-for-plugin: true` does override a selected style.
- No output style file on disk (`~/.claude/output-styles/` empty); the plugin is the only source.

## If it's not working

- `claude plugin list` should show `say-less@say-less` enabled.
- Plugins load at session start, so restart your session after installing.
- If a project sets `"outputStyle"` in its `.claude/settings.json`, that project is pinning a style; the plugin's `force-for-plugin` should still win, but check there first if output looks unchanged.
- The `claude` CLI authenticates separately from the Claude Desktop app. If `claude -p` says "Not logged in", run `claude auth login` (`/login` only works inside the `claude` REPL, not at a shell prompt).
