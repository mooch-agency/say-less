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


def load_page():
    """The UI is web/say-less.html, re-read per request so edits show on refresh."""
    with open(PAGE_FILE) as f:
        return f.read()


def stream_arm(prompt, style, model, out_q, arm):
    """Run one arm, pushing {'arm','delta'|'done'} onto out_q as text arrives."""
    cwd = tempfile.mkdtemp(prefix=f"srv_{arm}_")
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
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, env=_env(), cwd=cwd)
        full = []
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
        text = "".join(full)
        out_q.put({"arm": arm, "done": True, "text": text,
                   "words": total_words(text), "prose": prose_words(text)})
    except Exception as exc:  # surfaced in the UI rather than dying silently
        out_q.put({"arm": arm, "error": str(exc)})
    finally:
        import shutil
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
            threads = [
                threading.Thread(target=stream_arm, args=(prompt, "Default", self.model, out_q, "default"), daemon=True),
                threading.Thread(target=stream_arm, args=(prompt, STYLE, self.model, out_q, "sayless"), daemon=True),
            ]
            for t in threads:
                t.start()
            done = 0
            while done < 2:
                msg = out_q.get()
                if msg.get("done") or msg.get("error"):
                    done += 1
                try:
                    self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return  # browser navigated away mid-run
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
