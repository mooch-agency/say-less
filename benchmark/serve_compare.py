#!/usr/bin/env python3
"""
serve_compare.py — type a prompt, watch stock Claude Code and Say Less answer
side by side, live.

The published comparison artifact can't do this: a hosted page has no model
access and its CSP blocks network calls. This runs on your machine instead, so
it can shell out to `claude` and stream both replies token by token.

Both arms run hermetically (--setting-sources project): no user CLAUDE.md, no
user settings, no user-scope plugins. Without that the Say Less plugin, being
installed user-scope with force-for-plugin, would apply to the "Default" arm
too and the comparison would be meaningless.

Usage:
  python3 benchmark/serve_compare.py            # http://localhost:8787
  python3 benchmark/serve_compare.py --port 9000 --model opus
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
MODEL = "sonnet"


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
                   "words": prose_words(text), "total": total_words(text)})
    except Exception as exc:  # surfaced in the UI rather than dying silently
        out_q.put({"arm": arm, "error": str(exc)})
    finally:
        import shutil
        shutil.rmtree(cwd, ignore_errors=True)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Say Less: run your own</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--paper:#fff;--surface:#fbfbfd;--ink:#1d1d1f;--black:#000;--muted:#6e6e73;--hairline:#d2d2d7;
--sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,monospace;}
@media (prefers-color-scheme:dark){:root{--paper:#000;--surface:#0a0a0b;--ink:#fff;--black:#fff;
--muted:#8e8e93;--hairline:#2a2a2c;}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:16px;
line-height:1.5;padding:clamp(24px,5vw,56px);font-feature-settings:"tnum"}
.wrap{max-width:1320px;margin:0 auto}
.eyebrow{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.18em;
color:var(--muted);margin:0 0 14px}
h1{font-size:clamp(24px,3vw,34px);margin:0 0 22px;letter-spacing:-.02em;font-weight:600}
form{display:flex;gap:8px;margin-bottom:8px}
input{flex:1;min-width:0;padding:13px 15px;border:1px solid var(--hairline);border-radius:12px;
background:var(--paper);color:var(--ink);font:inherit}
input:focus{outline:none;border-color:var(--ink)}
button{padding:0 22px;border-radius:980px;border:1px solid var(--black);background:var(--black);
color:var(--paper);font:inherit;font-weight:500;cursor:pointer}
button:disabled{opacity:.45;cursor:default}
.note{font-size:13px;color:var(--muted);margin:0 0 24px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--hairline);
border:1px solid var(--hairline)}
@media (max-width:760px){.cols{grid-template-columns:1fr}}
.col{background:var(--paper);padding:20px;min-width:0}
.col.d{background:var(--surface)}
.head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}
.name{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.18em;color:var(--muted)}
.n{font-size:26px;font-variant-numeric:tabular-nums}
.n small{font-size:12px;color:var(--muted);margin-left:5px}
pre{white-space:pre-wrap;word-wrap:break-word;font-family:var(--sans);font-size:15px;margin:0}
.delta{border:1px solid var(--hairline);border-top:none;padding:14px 20px;font-size:15px}
.delta b{font-size:22px;font-variant-numeric:tabular-nums;margin-right:8px}
.err{color:#b00020}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--muted);
margin-left:8px;animation:p 1s ease-in-out infinite}
@keyframes p{0%,100%{opacity:.25}50%{opacity:1}}
@media (prefers-reduced-motion:reduce){.dot{animation:none}}
</style></head><body><div class="wrap">
<p class="eyebrow">Say Less</p>
<h1>Run your own prompt</h1>
<form id="f"><input id="q" placeholder="Ask anything, e.g. should I use UUIDs or integers for primary keys?" autocomplete="off" autofocus>
<button id="go">Run both</button></form>
<p class="note">Runs on your machine, hermetically: no user CLAUDE.md, settings or plugins reach either side. Model: <span id="m"></span></p>
<div class="cols">
  <div class="col d"><div class="head"><span class="name">Default</span><span class="n" id="nA">0<small>words</small></span></div><pre id="a"></pre></div>
  <div class="col"><div class="head"><span class="name">Say Less</span><span class="n" id="nB">0<small>words</small></span></div><pre id="b"></pre></div>
</div>
<div class="delta" id="delta">Type a question and hit Run both.</div>
</div>
<script>
const f=document.getElementById("f"),q=document.getElementById("q"),go=document.getElementById("go");
const A=document.getElementById("a"),B=document.getElementById("b");
const nA=document.getElementById("nA"),nB=document.getElementById("nB"),delta=document.getElementById("delta");
fetch("/model").then(r=>r.text()).then(t=>document.getElementById("m").textContent=t);

// same rule as benchmark/drift_session.py prose_words
function proseWords(t){t=String(t||"");t=t.replace(/```[\s\S]*?```/g," ");
 t=t.replace(/!\[[^\]]*\]\([^)]*\)/g," ");t=t.replace(/\[([^\]]*)\]\([^)]*\)/g,"$1");
 t=t.replace(/`[^`]*`/g," ");return t.split(/\s+/).filter(x=>/[0-9A-Za-z]/.test(x)).length;}
const buf={default:"",sayless:""};
function paint(){nA.innerHTML=proseWords(buf.default)+"<small>words</small>";
 nB.innerHTML=proseWords(buf.sayless)+"<small>words</small>";}

f.addEventListener("submit",ev=>{
  ev.preventDefault();
  const prompt=q.value.trim(); if(!prompt) return;
  buf.default="";buf.sayless="";A.textContent="";B.textContent="";paint();
  go.disabled=true; delta.innerHTML='Running both<span class="dot"></span>';
  const es=new EventSource("/run?q="+encodeURIComponent(prompt));
  let finished=0,res={};
  es.onmessage=e=>{
    const d=JSON.parse(e.data);
    if(d.error){delta.innerHTML='<span class="err">'+d.arm+': '+d.error+'</span>';go.disabled=false;es.close();return;}
    if(d.delta){buf[d.arm]+=d.delta;(d.arm==="default"?A:B).textContent=buf[d.arm];paint();return;}
    if(d.done){
      res[d.arm]=d.words; finished++;
      if(finished===2){
        es.close(); go.disabled=false;
        const a=res.default,b=res.sayless;
        const p=a>0?Math.round((1-b/a)*100):0;
        delta.innerHTML= p>0 ? "<b>"+p+"%</b> shorter with Say Less, "+a+" words down to "+b+"."
          : p===0 ? "<b>0%</b> same length, both "+a+" words."
          : "<b>"+Math.abs(p)+"%</b> longer with Say Less, "+a+" words up to "+b+".";
      }
    }
  };
  es.onerror=()=>{go.disabled=false;es.close();};
});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    model = MODEL

    def log_message(self, *a):
        pass  # keep the console clean; the page is the interface

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            body = PAGE.encode()
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
    ap = argparse.ArgumentParser(description="Local live Default vs Say Less comparison.")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    Handler.model = args.model
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"\n  Say Less compare  ->  http://localhost:{args.port}   (model: {args.model})")
    print("  ctrl-c to stop\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
