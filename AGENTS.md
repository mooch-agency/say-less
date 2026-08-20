# AGENTS.md

Instructions for an AI agent installing this plugin on a user's behalf. If
you're a human, see [README.md](README.md) or [INSTALL.md](INSTALL.md)
instead.

## Install (for agents)

1. Try the CLI first:

   ```bash
   claude plugin marketplace add mooch-agency/say-less && claude plugin install say-less@say-less
   ```

2. If `claude` isn't on PATH (this is the desktop app, not the terminal),
   fetch [`install.json`](install.json) from this repo
   (`https://raw.githubusercontent.com/mooch-agency/say-less/master/install.json`)
   and merge its two keys into `~/.claude/settings.json`. Merge, don't
   overwrite — keep every key already in that file.

3. Verify: `claude plugin list` should show `say-less@say-less` enabled, or
   read `~/.claude/settings.json` back and confirm both keys landed.

4. Tell the user to start a new session, then test by asking "What's the
   default Postgres port?" A one-line answer means it worked; a normal-length
   answer means the install didn't take.

No other steps. The output style and the drift-persistence hook (see
[`hooks/`](hooks/)) both ship inside the plugin and register automatically —
don't ask the user to configure either one separately.

## Do not

- Don't type `/plugin` yourself — it's a human-only terminal command, not
  something an agent can invoke.
- Don't invent the settings.json schema from memory. Use the JSON in
  `install.json` verbatim.
- Don't overwrite `~/.claude/settings.json`. Read it, merge, write it back.
