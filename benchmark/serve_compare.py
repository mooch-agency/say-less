#!/usr/bin/env python3
"""
serve_compare.py — ask Claude Code anything, watch it answer twice, live.

Serves web/say-less.html and streams both arms into it: the left column is
stock Claude Code, the right is the same model with the Say Less style. Word
counts update as the text arrives.

This is the only comparison UI, and it runs locally on purpose. The left arm
has to be real Claude Code, and Claude Code's system prompt lives inside the
CLI, so it cannot be reproduced from an API key. Nothing here needs one: it
shells out to your logged-in `claude` session.

Both arms run hermetically (--setting-sources project): no user CLAUDE.md, no
user settings, no user-scope plugins. Without that the Say Less plugin, being
installed user-scope with force-for-plugin, would apply to the "Default" arm
too and the comparison would be meaningless.

Usage:
  python3 benchmark/serve_compare.py            # http://localhost:8787
  python3 benchmark/serve_compare.py --port 9000 --model claude-opus-4-8
"""

import argparse
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from drift_session import prose_words, total_words, _resolve_style_file, _env

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE = "Say Less"
MODEL = "claude-sonnet-5"
PAGE_FILE = os.path.join(HERE, "..", "web", "say-less.html")

# A wedged CLI would otherwise leave the page spinning forever with no way back
# except a reload, so every arm gets a hard ceiling.
ARM_TIMEOUT = 180
# Silence on the wire also means we never notice the browser has gone. Ping on
# every idle beat so a closed tab surfaces as BrokenPipe within a couple of
# seconds instead of at the next delta, which may be 8 seconds of startup away.
PING_EVERY = 2


def load_page():
    """The UI is web/say-less.html, re-read per request so edits show on refresh."""
    with open(PAGE_FILE) as f:
        return f.read()


def _tail(path, limit=400):
    try:
        with open(path) as f:
            return f.read().strip()[-limit:]
    except OSError:
        return ""


def stream_arm(prompt, style, model, out_q, arm, registry):
    """Run one arm, pushing {'arm','delta'|'done'|'error'} onto out_q as text arrives.

    Registers its Popen in `registry` so the request thread can kill it if the
    browser goes away; an answer nobody will read still costs real usage.
    """
    cwd = tempfile.mkdtemp(prefix=f"srv_{arm}_")
    err_path = os.path.join(cwd, "stderr.log")
    try:
        if style != "Default":
            src = _resolve_style_file(style)
            if src is None:
                out_q.put({"arm": arm, "error": f"style {style!r} not found"})
                return
            sdir = os.path.join(cwd, ".claude", "output-styles")
            os.makedirs(sdir, exist_ok=True)
            with open(src) as f, open(os.path.join(sdir, "style.md"), "w") as g:
                g.write(f.read())
        cmd = [
            "claude", "-p", prompt,
            "--settings", json.dumps({"outputStyle": style}),
            "--setting-sources", "project",
            "--model", model,
            "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config",
            "--output-format", "stream-json", "--include-partial-messages", "--verbose",
        ]
        # stderr goes to a file, not a pipe: nothing reads it during the run, and
        # a full pipe buffer would deadlock the CLI mid-answer.
        # stdin=DEVNULL is not cosmetic. Left inherited, the CLI spends 3s
        # waiting to see if anything is being piped in, which measured as ~2.3s
        # of extra dead air before the first word (4.75s -> 2.45s median).
        with open(err_path, "w") as errf:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf,
                                    stdin=subprocess.DEVNULL,
                                    text=True, env=_env(), cwd=cwd)
        registry[arm] = proc
        watchdog = threading.Timer(ARM_TIMEOUT, proc.kill)
        watchdog.daemon = True
        watchdog.start()
        full = []
        try:
            for line in proc.stdout:
                try:
                    evt = json.loads(line)
                except ValueError:
                    continue
                if evt.get("type") == "stream_event":
                    e = evt.get("event", {})
                    if e.get("type") == "content_block_delta":
                        piece = e.get("delta", {}).get("text", "")
                        if piece:
                            full.append(piece)
                            out_q.put({"arm": arm, "delta": piece})
            proc.wait()
        finally:
            watchdog.cancel()
        text = "".join(full)
        # A non-zero exit with nothing to show is a failure, not a short answer.
        # Reporting it as "0 words" would read as a win for whichever arm broke.
        if proc.returncode != 0 and not text.strip():
            out_q.put({"arm": arm, "error": _tail(err_path)
                       or f"claude exited {proc.returncode}"})
            return
        out_q.put({"arm": arm, "done": True, "text": text,
                   "words": total_words(text), "prose": prose_words(text)})
    except Exception as exc:  # surfaced in the UI rather than dying silently
        out_q.put({"arm": arm, "error": str(exc)})
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    model = MODEL

    def log_message(self, *a):
        pass  # keep the console clean; the page is the interface

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/say-less", "/say-less.html"):
            try:
                body = load_page().encode()
            except OSError:
                self.send_error(500, "web/say-less.html not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/model":
            body = self.model.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/run":
            prompt = (parse_qs(u.query).get("q") or [""])[0]
            if not prompt:
                self.send_error(400, "missing q")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            out_q = queue.Queue()
            procs = {}
            # Both arms start here, in their own threads, and their deltas
            # interleave on one queue. They really do run at the same time; the
            # page shows each arm's own clock so that stays visible.
            for style, arm in (("Default", "default"), (STYLE, "sayless")):
                threading.Thread(target=stream_arm, daemon=True,
                                 args=(prompt, style, self.model, out_q, arm, procs)).start()
            done = 0
            try:
                while done < 2:
                    try:
                        msg = out_q.get(timeout=PING_EVERY)
                    except queue.Empty:
                        msg = None  # idle beat: a comment line the client ignores
                    payload = (f"data: {json.dumps(msg)}\n\n" if msg else ": ping\n\n")
                    if msg and (msg.get("done") or msg.get("error")):
                        done += 1
                    try:
                        self.wfile.write(payload.encode())
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return  # browser navigated away mid-run
            finally:
                # However this ended (both finished, tab closed, arm failed),
                # never leave a `claude` running for an answer nobody will read.
                for p in list(procs.values()):
                    if p.poll() is None:
                        p.kill()
            return
        self.send_error(404)


def main():
    ap = argparse.ArgumentParser(description="Ask Claude Code anything, twice, side by side.")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    Handler.model = args.model
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"\n  Say Less  ->  http://localhost:{args.port}   (model: {args.model})")
    print("  ctrl-c to stop\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
