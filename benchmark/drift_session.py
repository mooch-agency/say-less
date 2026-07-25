#!/usr/bin/env python3
"""
drift_session.py — multi-turn PERSISTENCE test on the real output style.

Runs a fixed N-turn conversation through headless `claude -p --resume`, so the
model sees its own prior replies and the context grows turn over turn. That is
the real condition under which a terseness style DRIFTS back toward verbose:
the model's own long earlier answers become few-shot examples pulling it long.

How this differs from the other two harnesses:
  ab_style.py       single-turn; measures wording (terseness + completeness).
  position_test.py  multi-turn but API-based, and tests a COMPACT rules string
                    placed top/bottom — it isolates PLACEMENT, not the real style.
  drift_session.py  multi-turn, and exercises the ACTUAL output style exactly as
                    Claude Code delivers it: appended to the system prompt, with
                    Claude Code's own (opaque) adherence reminders firing as the
                    conversation grows. This is the only harness that measures
                    whether the shipped style holds up across a whole session.

Each condition is an output-style NAME resolved from ~/.claude/output-styles/
(the frontmatter `name:`), selected per-run with --settings '{"outputStyle":...}'.
Use "Default" for the no-style baseline. Subscription billing only: any
ANTHROPIC_API_KEY is stripped from the child env, matching ab_style.py.

The conversation is built to INDUCE drift: floor/decision/checkable/explain
prompts are interleaved with context-growers (pasted code, a stack trace, a
diff-review — the exact "wall of text" trigger). The pattern repeats so the
first and second halves hold comparable prompt types; any rise in the second
half is decay, not harder questions. Checkable turns (ACID=4, CAP=3, methods=5)
are spread early AND late so --judge can catch completeness dropping over time.

Usage:
  python3 benchmark/drift_session.py "Default" "Say Less" [NAME ...] \
      [--trials 3] [--model sonnet] [--workers 6] [--judge] [--out results.json]

Notes:
- Runs each session in an isolated empty dir so the agent isn't tempted into
  tool use. User-scope ~/.claude/CLAUDE.md still applies, but it applies EQUALLY
  to every condition, so relative comparisons (which style drifts least) hold.
- --resume is sequential within a session; independent sessions run in parallel.
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
# Source of truth for the Say Less rule text. The persona condition injects this
# same body via CLAUDE.md so the ONLY difference vs the output style is the
# delivery channel, not the words.
STYLE_FILE = os.path.join(HERE, "..", "say-less.md")

# --- the conversation -------------------------------------------------------
# kind: fact | decision | checkable | explain | grow  (grow = context-grower)
# check: expected-content note for the completeness judge (checkable turns only)
_FUNC = (
    "def dedupe(items):\n"
    "    seen = []\n"
    "    for x in items:\n"
    "        if x not in seen:\n"
    "            seen.append(x)\n"
    "    return seen\n"
)
_TRACE = (
    "Traceback (most recent call last):\n"
    '  File "app.py", line 42, in handler\n'
    "    total = sum(cart[i].price for i in ids)\n"
    "KeyError: 'price'\n"
)
_DIFF = (
    "@@ def charge(user, amount):\n"
    "-    stripe.charge(user.card, amount)\n"
    "+    if amount <= 0:\n"
    "+        raise ValueError('amount must be positive')\n"
    "+    stripe.charge(user.card, amount)\n"
    "+    log.info(f'charged {user.id} {amount}')\n"
)

# Prompts are held out from every candidate style's few-shot EXAMPLES so no style
# can win a turn by copying its own example verbatim. (Avoided: Postgres port,
# REST vs GraphQL, TCP vs UDP, OAuth flow, git-undo, "what does this PR change".)
CONVERSATION = [
    {"kind": "fact",      "prompt": "What's the default port for Redis?"},
    {"kind": "decision",  "prompt": "Should I use a monorepo or separate repos for three related services?"},
    {"kind": "checkable", "prompt": "Name the four pillars of object-oriented programming and define each in one line.",
     "check": "encapsulation, abstraction, inheritance, polymorphism"},
    {"kind": "explain",   "prompt": "Explain how a hash map handles collisions."},
    {"kind": "grow",      "prompt": "What does this function do, and is there a performance problem?\n\n" + _FUNC},
    {"kind": "fact",      "prompt": "What HTTP status code means Unauthorized?"},
    {"kind": "decision",  "prompt": "Is it worth adding a message queue just to send emails asynchronously?"},
    {"kind": "checkable", "prompt": "What are the first three database normal forms (1NF, 2NF, 3NF)? Define each.",
     "check": "1NF atomic values, 2NF no partial dependency, 3NF no transitive dependency"},
    {"kind": "explain",   "prompt": "Explain how merge sort works."},
    {"kind": "grow",      "prompt": "What's causing this error and how do I fix it?\n\n" + _TRACE},
    {"kind": "fact",      "prompt": "What does chmod 755 set?"},
    {"kind": "decision",  "prompt": "MySQL or Postgres for a new analytics-heavy application?"},
    {"kind": "checkable", "prompt": "List the five main HTTP methods and what each is for.",
     "check": "GET, POST, PUT, PATCH, DELETE"},
    {"kind": "explain",   "prompt": "Explain the difference between a process and a thread."},
    {"kind": "grow",      "prompt": "Review this change.\n\n" + _DIFF},
    {"kind": "fact",      "prompt": "What's the difference between let and const in JavaScript?"},
]

# --- a SECOND session shape: longer (28 turns) and coding/debugging-heavy -----
# The audit of the sl-v4/sl-v5 work flagged that ONE fixed 16-turn Q&A
# conversation cannot prove a fix holds across session TYPE or LENGTH. This one
# is ~75% longer and dominated by `grow` turns (pasted code, traces, diffs, a
# long omnibus review) — the exact wall-of-text triggers that pull replies long
# late in a real coding session. Kinds are balanced across the two halves so a
# second-half rise is decay, not harder questions; checkable turns are spread at
# 3/8/14/20/26 so --judge can track completeness early AND late. Prompts are
# disjoint from CONVERSATION and from every style's few-shot examples.
_BSEARCH = (
    "def bsearch(a, target):\n"
    "    lo, hi = 0, len(a)\n"
    "    while lo <= hi:\n"
    "        mid = (lo + hi) // 2\n"
    "        if a[mid] == target: return mid\n"
    "        if a[mid] < target: lo = mid + 1\n"
    "        else: hi = mid - 1\n"
    "    return -1\n"
)
_TRACE2 = (
    "TypeError: Cannot read properties of undefined (reading 'map')\n"
    "    at renderList (app.js:88:24)\n"
    "    at Object.render (app.js:120:5)\n"
    "    at commitRoot (react-dom.js:4201:3)\n"
)
_SLOWSQL = (
    "-- runs once per user in a loop over 5k users\n"
    "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC;\n"
    "-- orders has 40M rows, no index on user_id\n"
)
_DIFF2 = (
    "@@ async function sync(users):\n"
    "-    for u in users:\n"
    "-        await save(u)\n"
    "+    for u in users:\n"
    "+        save(u)   # dropped the await to 'speed it up'\n"
    "+    return 'done'\n"
)
_RACE = (
    "var counter int\n"
    "for i := 0; i < 1000; i++ {\n"
    "    go func() { counter++ }()\n"
    "}\n"
    "time.Sleep(time.Second)\n"
    "fmt.Println(counter)\n"
)
_REGEX = r"^(\d{4})-(\d{2})-(\d{2})$  # meant to validate a date like 2026-13-45"
_DOCKER = (
    "FROM node:20\n"
    "COPY . .\n"
    "RUN npm install\n"
    "CMD [\"node\", \"server.js\"]\n"
)
_MODULE = (
    "class RateLimiter:\n"
    "    def __init__(self, limit):\n"
    "        self.limit = limit\n"
    "        self.hits = {}\n"
    "    def allow(self, key):\n"
    "        now = time.time()\n"
    "        self.hits.setdefault(key, [])\n"
    "        self.hits[key] = [t for t in self.hits[key] if now - t < 60]\n"
    "        if len(self.hits[key]) < self.limit:\n"
    "            self.hits[key].append(now)\n"
    "            return True\n"
    "        return False\n"
)

CONVERSATION_CODING = [
    {"kind": "fact",      "prompt": "What port does PostgreSQL listen on by default?"},
    {"kind": "grow",      "prompt": "Is this binary search correct? If not, what's the bug?\n\n" + _BSEARCH},
    {"kind": "checkable", "prompt": "Name the five SOLID principles.",
     "check": "single responsibility, open/closed, Liskov substitution, interface segregation, dependency inversion"},
    {"kind": "explain",   "prompt": "Explain how a bloom filter works."},
    {"kind": "decision",  "prompt": "Should business logic live in database stored procedures or the application layer?"},
    {"kind": "grow",      "prompt": "What's throwing this and how do I fix it?\n\n" + _TRACE2},
    {"kind": "fact",      "prompt": "What does the SQL HAVING clause do?"},
    {"kind": "checkable", "prompt": "What are the four ACID properties? Define each in one line.",
     "check": "atomicity, consistency, isolation, durability"},
    {"kind": "grow",      "prompt": "This endpoint is slow. What's wrong and how would you fix it?\n\n" + _SLOWSQL},
    {"kind": "explain",   "prompt": "Explain how git rebase differs from git merge."},
    {"kind": "decision",  "prompt": "Is it worth introducing dependency injection in a small Flask app?"},
    {"kind": "grow",      "prompt": "Review this diff.\n\n" + _DIFF2},
    {"kind": "fact",      "prompt": "What HTTP status code means Too Many Requests?"},
    {"kind": "checkable", "prompt": "List the four standard SQL isolation levels from weakest to strongest.",
     "check": "read uncommitted, read committed, repeatable read, serializable"},
    {"kind": "explain",   "prompt": "Explain how a debounce function works and when to use it."},
    {"kind": "grow",      "prompt": "Is this Go code safe? What does it print and why?\n\n" + _RACE},
    {"kind": "fact",      "prompt": "What does git cherry-pick do?"},
    {"kind": "decision",  "prompt": "Cache this API response in Redis or in-process memory?"},
    {"kind": "grow",      "prompt": "What's wrong with this regex for date validation?\n\n" + _REGEX},
    {"kind": "checkable", "prompt": "Name the three pillars of observability.",
     "check": "logs, metrics, traces"},
    {"kind": "explain",   "prompt": "Explain the difference between optimistic and pessimistic locking."},
    {"kind": "grow",      "prompt": "What's the caching mistake in this Dockerfile?\n\n" + _DOCKER},
    {"kind": "fact",      "prompt": "What does a 502 Bad Gateway indicate?"},
    {"kind": "decision",  "prompt": "Rewrite this legacy service or apply the strangler-fig pattern incrementally?"},
    {"kind": "grow",      "prompt": "Review this module for correctness, thread-safety, and performance; give the top 3 fixes.\n\n" + _MODULE},
    {"kind": "checkable", "prompt": "List the five HTTP status code classes (1xx to 5xx) and what each class means.",
     "check": "1xx informational, 2xx success, 3xx redirection, 4xx client error, 5xx server error"},
    {"kind": "explain",   "prompt": "Explain how the TLS handshake establishes a secure connection."},
    {"kind": "fact",      "prompt": "What's the difference between == and is in Python?"},
]

# --- a THIRD session shape: report-heavy (14 turns, real tool use) -----------
# Round 3 (RESEARCH.md) found the worst real-world verbosity is task-REPORT
# turns — the model does work, then narrates it — and neither Q&A shape above
# measures that. Here 8 of 14 turns are small edit tasks in a seeded workspace
# (the session runs with Read/Write/Edit allowed); the reply we score IS the
# report. Report turns are balanced 4/4 across halves so a second-half rise is
# decay; quick Q&A turns are interleaved to mirror real sessions. Prompts say
# only what a user would say ("add X", "fix Y") — no "be brief", and no "report
# what you did" (reporting is the default behavior under test).
_WS_UTILS = (
    "import re\n\n\n"
    "def parse_date(s):\n"
    "    # expects YYYY-MM-DD\n"
    "    y, m, d = s.split(\"-\")\n"
    "    return int(y), int(m), int(d)\n\n\n"
    "def slugify(s):\n"
    "    s = s.lower().strip()\n"
    "    s = re.sub(r\"[^a-z0-9]\", \"-\", s)\n"
    "    return s.strip(\"-\")\n"
)
_WS_SERVER = (
    "import json\n"
    "import os\n\n\n"
    "def handle_request(method, path, body=None):\n"
    "    if method == \"GET\" and path == \"/health\":\n"
    "        return 200, json.dumps({\"ok\": True})\n"
    "    if method == \"POST\" and path == \"/parse\":\n"
    "        from utils import parse_date\n"
    "        y, m, d = parse_date(body)\n"
    "        return 200, json.dumps({\"y\": y, \"m\": m, \"d\": d})\n"
    "    return 404, json.dumps({\"error\": \"not found\"})\n\n\n"
    "def unused_helper():\n"
    "    pass\n"
)
WORKSPACES = {"report": {"utils.py": _WS_UTILS, "server.py": _WS_SERVER}}

CONVERSATION_REPORT = [
    {"kind": "report",    "prompt": "Add input validation to parse_date in utils.py: raise ValueError with a clear message on malformed input."},
    {"kind": "fact",      "prompt": "What does HTTP status 304 mean?"},
    {"kind": "report",    "prompt": "slugify in utils.py leaves repeated hyphens in the output (e.g. 'a  b' -> 'a--b'). Fix it."},
    {"kind": "checkable", "prompt": "Name the four git object types.",
     "check": "blob, tree, commit, tag"},
    {"kind": "report",    "prompt": "Add a chunks(lst, n) function to utils.py that yields successive n-sized chunks, with a docstring."},
    {"kind": "explain",   "prompt": "Explain what makes an HTTP API endpoint idempotent."},
    {"kind": "report",    "prompt": "Add logging to handle_request in server.py: log the method and path at INFO level."},
    {"kind": "report",    "prompt": "Rename slugify's parameter s to text, updating every use in the repo."},
    {"kind": "fact",      "prompt": "What flag makes grep case-insensitive?"},
    {"kind": "report",    "prompt": "Create a README.md describing what utils.py provides."},
    {"kind": "checkable", "prompt": "List the three main states a tracked file moves through in git (working -> repository).",
     "check": "modified, staged, committed"},
    {"kind": "report",    "prompt": "Remove the unused import and any dead code in server.py."},
    {"kind": "decision",  "prompt": "Should I pin exact dependency versions in requirements.txt for a small internal tool like this?"},
    {"kind": "report",    "prompt": "Review utils.py and fix the most important remaining issue."},
]

# --- a FOURTH shape: report2, HEAVY-RESULT tasks (16 turns, real edits) ------
# Round 1 (report) came back null because single-file micro-edits gave Opus
# nothing to over-report (~30-word replies with no fix applied). Round 2
# (results/2026-07-scope-hook-report.md) seeds a 7-file app with real,
# findable issues across security / perf / correctness / dead code / a doc
# contradiction, and asks heavy-result tasks: audits, whole-repo reviews, a
# status summary — the turns where the model chooses HOW MANY of its findings
# to narrate. Two turns are completeness GUARDS: turn 10 ("list the top 5")
# genuinely requires 5 items, so a scope budget that drops requested content
# shows as a loss there, not a win. Score BOTH prose and total words
# (analyze_drift --metric total_words): structured overhead is what prose_words
# strips and exactly what over-reporting adds.
_A_CONFIG = (
    "import os\n\n"
    "# TODO: move to env before prod\n"
    'SECRET_KEY = "dev-secret-12345"\n'
    "DEBUG = True\n"
    'DB_PATH = "app.db"\n'
    "MAX_LOGIN_ATTEMPTS = 5  # not enforced anywhere\n"
)
_A_AUTH = (
    "import sqlite3\n"
    "from config import DB_PATH\n\n\n"
    "def find_user(username):\n"
    "    conn = sqlite3.connect(DB_PATH)\n"
    "    cur = conn.cursor()\n"
    "    cur.execute(\"SELECT id, username, password FROM users \"\n"
    "                \"WHERE username = '%s'\" % username)\n"
    "    return cur.fetchone()\n\n\n"
    "def login(username, password):\n"
    "    user = find_user(username)\n"
    "    if user is None:\n"
    "        return False\n"
    "    return user[2] == password\n"
)
_A_DB = (
    "import sqlite3\n"
    "from config import DB_PATH\n\n\n"
    "def get_orders_for_users(user_ids):\n"
    "    conn = sqlite3.connect(DB_PATH)\n"
    "    cur = conn.cursor()\n"
    "    results = {}\n"
    "    for uid in user_ids:\n"
    "        cur.execute(\"SELECT * FROM orders WHERE user_id = ?\", (uid,))\n"
    "        results[uid] = cur.fetchall()\n"
    "    return results\n\n\n"
    "def total_revenue():\n"
    "    conn = sqlite3.connect(DB_PATH)\n"
    "    cur = conn.cursor()\n"
    "    cur.execute(\"SELECT amount FROM orders\")\n"
    "    total = 0\n"
    "    for r in cur.fetchall():\n"
    "        total += r[0]\n"
    "    return total\n"
)
_A_UTILS = (
    "def paginate(items, page, per_page=10):\n"
    "    start = page * per_page + 1\n"
    "    end = start + per_page\n"
    "    return items[start:end]\n\n\n"
    "def merge_configs(base, overrides={}):\n"
    "    base.update(overrides)\n"
    "    return base\n\n\n"
    "def old_format_name(first, last):\n"
    "    # superseded by format_name; kept just in case\n"
    "    return first + \" \" + last\n\n\n"
    "def format_name(first, last):\n"
    "    return f\"{first} {last}\"\n"
)
_A_API = (
    "from auth import login\n"
    "from db import get_orders_for_users\n\n\n"
    "def handle(method, path, body):\n"
    "    if path == \"/login\":\n"
    "        if login(body[\"username\"], body[\"password\"]):\n"
    "            return 200, \"ok\"\n"
    "        return 200, \"bad credentials\"\n"
    "    if path == \"/orders\":\n"
    "        try:\n"
    "            return 200, get_orders_for_users(body[\"ids\"])\n"
    "        except:\n"
    "            return 500, \"error\"\n"
    "    return 404, \"not found\"\n"
)
_A_TEST = (
    "from auth import login\n"
    "from api import handle\n\n\n"
    "def test_login_rejects_wrong_password():\n"
    "    assert login(\"alice\", \"wrong\") is False\n\n\n"
    "def test_login_bad_credentials_returns_401():\n"
    "    code, _ = handle(\"POST\", \"/login\",\n"
    "                     {\"username\": \"alice\", \"password\": \"wrong\"})\n"
    "    assert code == 401  # api.py currently returns 200\n"
)
_A_README = (
    "# OrderApp\n\n"
    "A small internal order service.\n\n"
    "## Security\n\n"
    "Passwords are hashed with bcrypt before storage.\n"
)
WORKSPACES = {
    "report": {"utils.py": _WS_UTILS, "server.py": _WS_SERVER},
    "report2": {"config.py": _A_CONFIG, "auth.py": _A_AUTH, "db.py": _A_DB,
                "utils.py": _A_UTILS, "api.py": _A_API,
                "test_auth.py": _A_TEST, "README.md": _A_README},
}

CONVERSATION_REPORT2 = [
    {"kind": "report",    "prompt": "One test in test_auth.py fails against the current code. Find it and fix the code so it passes."},
    {"kind": "fact",      "prompt": "What HTTP status code means Forbidden?"},
    {"kind": "report",    "prompt": "Is auth.py safe to ship? If not, fix the single most serious problem."},
    {"kind": "checkable", "prompt": "Name the four ACID properties and define each in one line.",
     "check": "atomicity, consistency, isolation, durability"},
    {"kind": "report",    "prompt": "Add input validation to the /login handler in api.py: reject requests missing username or password with a 400."},
    {"kind": "explain",   "prompt": "Explain why parameterised SQL queries prevent injection."},
    {"kind": "report",    "prompt": "db.py loads orders inefficiently. Fix the performance problem."},
    {"kind": "report",    "prompt": "Remove the dead code in the repo."},
    {"kind": "fact",      "prompt": "What does the SQL keyword DISTINCT do?"},
    # GUARD: genuinely needs 5 items; a scope budget that drops them loses here.
    {"kind": "report",    "prompt": "Do a full review of the repo and list the top 5 most severe issues, most severe first, one line each."},
    {"kind": "checkable", "prompt": "List the four standard SQL isolation levels from weakest to strongest.",
     "check": "read uncommitted, read committed, repeatable read, serializable"},
    {"kind": "report",    "prompt": "paginate in utils.py corrupts its output. Find and fix the bug."},
    {"kind": "decision",  "prompt": "Should config.py's settings move to environment variables for this internal tool?"},
    # GUARD: legitimately a summary, but "a few lines" caps it; over-narration shows here.
    {"kind": "report",    "prompt": "You've changed several files. Summarise the current state of the repo in a few lines."},
    {"kind": "checkable", "prompt": "Name the three pillars of observability.",
     "check": "logs, metrics, traces"},
    {"kind": "report",    "prompt": "Review api.py and fix the most important remaining correctness issue."},
]

CONVERSATIONS = {"default": CONVERSATION, "coding": CONVERSATION_CODING,
                 "report": CONVERSATION_REPORT, "report2": CONVERSATION_REPORT2}

# --- prose-aware counting + tic detectors (shared with the other harnesses) --

_FENCED = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WORD = re.compile(r"[0-9A-Za-z]")

OPENERS = [
    "let me", "sure,", "sure!", "great question", "great,", "here's", "here is",
    "so,", "well,", "certainly", "of course", "i'd be happy", "happy to",
    "absolutely", "to answer", "in order to answer",
]
CLOSERS = [
    "hope this helps", "hope that helps", "let me know", "in summary",
    "to summarize", "to sum up", "to recap", "overall,", "in conclusion",
    "feel free to", "don't hesitate", "happy to help",
]


def _count(text):
    return sum(1 for tok in text.split() if _WORD.search(tok))


def prose_words(text):
    t = _FENCED.sub(" ", text)
    t = _MD_IMAGE.sub(" ", t)
    t = _MD_LINK.sub(r"\1", t)
    t = _INLINE_CODE.sub(" ", t)
    return _count(t)


def total_words(text):
    return _count(text)


def count_em_dashes(text):
    return text.count("—") + len(re.findall(r"\s--\s", text))


def has_opener(text):
    head = text.strip().lower()[:60]
    return int(any(head.startswith(o) or head[:25].find(o) != -1 for o in OPENERS))


def has_closer(text):
    tail = text.strip().lower()[-200:]
    return int(any(c in tail for c in CLOSERS))


def score_reply(text):
    return {
        "words": prose_words(text),
        "total_words": total_words(text),
        "em_dashes": count_em_dashes(text),
        "opener": has_opener(text),
        "closer": has_closer(text),
    }


# --- headless claude --------------------------------------------------------

JUDGE_SYS = (
    "You are a strict grader. You are given a QUESTION and an ANSWER. Output "
    "ONLY a single integer from 0 to 100: how completely the answer covers the "
    "content the question requires. Judge ONLY completeness of required content "
    "(all parts of a multi-part question, correct key facts). IGNORE verbosity, "
    "length, style, and politeness entirely. A terse answer that covers "
    "everything scores 100. Output the integer and nothing else."
)


def _env():
    # Force subscription billing, never API-key billing (matches ab_style.py).
    return {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}


def ensure_style(cwd, style):
    """Materialise a named style into <cwd>/.claude/output-styles/style.md.

    Under --setting-sources project the user-scope styles dir is NOT loaded, so
    a style that isn't in the run cwd silently resolves to nothing and the turn
    runs as Default. That failure is invisible: the run still succeeds and still
    gets labelled with the style name, so it reads as a catastrophic regression
    (spot.py reported 199 words for Say Less against a true median of ~42).
    Idempotent, so callers that already seeded the dir can call it again.
    """
    if style == "Default":
        return
    src = _resolve_style_file(style)
    if src is None:
        raise ValueError(f"style {style!r} not found in repo style dirs")
    sdir = os.path.join(cwd, ".claude", "output-styles")
    os.makedirs(sdir, exist_ok=True)
    with open(src) as f, open(os.path.join(sdir, "style.md"), "w") as g:
        g.write(f.read())


def claude_turn(prompt, style, model, cwd, resume=None, hook_script=None,
                allow_edits=False):
    """One headless turn. Returns (reply_text, session_id)."""
    # Every caller gets the style guaranteed present, not just the ones that
    # remember to seed it themselves.
    ensure_style(cwd, style)
    settings = {"outputStyle": style}
    if allow_edits:
        # Report-shaped sessions do real file edits; -p mode auto-denies
        # Edit/Write without this. Bash stays denied on purpose (keeps turns
        # fast and the reply focused on the edit + report).
        settings["permissions"] = {"allow": ["Read", "Write", "Edit", "Glob", "Grep"]}
    if hook_script:
        # Recency re-injection: a UserPromptSubmit hook fires at the newest turn.
        settings["hooks"] = {"UserPromptSubmit": [{"hooks": [
            {"type": "command", "command": f'bash "{hook_script}"', "timeout": 5}]}]}
    cmd = [
        "claude", "-p", prompt,
        "--settings", json.dumps(settings),
        # HERMETIC (2026-07-25): only project-scope settings load, so the
        # operator's ~/.claude/CLAUDE.md (which carries its own verbosity
        # rules) and user-scope plugins can't contaminate either arm. A named
        # style must therefore exist in the run cwd: run_session copies it to
        # <cwd>/.claude/output-styles/. Runs before this date had user scope
        # loaded in ALL arms equally: relative comparisons hold, but absolute
        # Default word counts were understated.
        "--setting-sources", "project",
        "--model", model,
        "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config",
        "--output-format", "json",
    ]
    if resume:
        cmd += ["--resume", resume]
    try:
        # stdin=DEVNULL guards CORRECTNESS, not speed. capture_output only
        # redirects stdout and stderr, so stdin stays inherited, and `claude -p`
        # reads whatever is there and APPENDS it to the prompt. Run from a
        # terminal that is harmless (a TTY sends nothing). Run from a pipe,
        # heredoc, CI or cron, the surrounding text is silently glued onto every
        # question, and the harness measures answers to prompts nobody wrote.
        # Observed: a heredoc-launched spot.py returned median 237 words against
        # a true ~42, the replies visibly answering the wrapper script.
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=420, stdin=subprocess.DEVNULL,
                           env=_env(), cwd=cwd)
        data = json.loads(r.stdout)
        return data.get("result", ""), data.get("session_id", resume)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return "", resume


def claude_plain(prompt, system, model, cwd=None):
    """One-shot judge call with a replacement system prompt.

    HERMETIC: always runs in its own fresh temp dir (never a caller's cwd), so
    it can't inherit a project .claude/settings.json hook or CLAUDE.md, forces
    outputStyle Default so no style is appended to the judge, and reads the
    result from --output-format json (raw stdout comes back empty on any hiccup,
    which silently scored judges 0 — the glance_bench v1 bug). cwd is ignored,
    kept for call-site compatibility.
    """
    with tempfile.TemporaryDirectory(prefix="judge_") as jcwd:
        cmd = [
            "claude", "-p", prompt, "--system-prompt", system, "--model", model,
            "--settings", '{"outputStyle":"Default"}',
            "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config",
            "--output-format", "json",
        ]
        try:
            # Same trap as claude_turn: inherited stdin gets appended to the
            # prompt, which here would corrupt the judge's instructions and
            # silently skew every score.
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=180, stdin=subprocess.DEVNULL,
                               env=_env(), cwd=jcwd)
            return json.loads(r.stdout).get("result", "").strip()
        except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
            return ""


def judge_completeness(question, answer, model, cwd):
    if not answer.strip():
        return 0
    # Retry on parse failure or an implausible 0 (a non-empty answer to these
    # prompts is never 0% complete; a spurious 0 is a judge misfire, so re-ask).
    last = -1
    for _ in range(3):
        out = claude_plain(f"QUESTION:\n{question}\n\nANSWER:\n{answer}", JUDGE_SYS, model, cwd)
        m = re.findall(r"\d+", out)
        if m:
            last = max(0, min(100, int(m[0])))
            if last > 0:
                return last
    return last


def _style_body(path):
    """Return a style/persona markdown file's body with YAML frontmatter stripped."""
    with open(path) as f:
        text = f.read()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[text.find("\n", end + 1) + 1:]
    return text.lstrip("\n")


HOOKS = {"+hook": "say-less-gate.sh", "+scopehook": "say-less-scope.sh"}

# Style files shipped in this repo, resolved by frontmatter name so hermetic
# runs can copy the right file into the session cwd (see claude_turn).
_STYLE_DIRS = [os.path.join(HERE, "..", "output-styles"),
               os.path.join(HERE, "..", "versions")]


def _resolve_style_file(name):
    """Find the repo style file whose frontmatter name: matches `name`."""
    for d in _STYLE_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(d, fn)
            with open(path) as f:
                head = f.read(400)
            if f"name: {name}\n" in head:
                return path
    return None


def run_session(style, model, do_judge, conversation, workspace=None):
    """One full multi-turn conversation under a style. Returns per-turn scores.

    A style name ending in '+hook' (say-less-gate.sh: anti-anchoring nudge) or
    '+scopehook' (say-less-scope.sh: same nudge + a structural scope budget)
    runs the output style PLUS that UserPromptSubmit hook: the script is copied
    into the session's isolated temp cwd and wired in via --settings, so one
    paired batch can compare style-alone vs the hooks under identical conditions.

    The condition 'SayLess-persona' delivers the SAME Say Less rule text
    (STYLE_FILE body, frontmatter stripped) through the OTHER channel: it is
    written as CLAUDE.md in the isolated cwd and the output style is set to
    Default. So one paired batch can compare the identical words as an output
    style (system prompt + Claude Code's re-injection reminders) vs as persona
    memory (the # claudeMd block, no re-injection). Project CLAUDE.md is a
    faithful, per-run-isolated proxy for ~/.claude/PERSONA.md (both land in the
    same claudeMd context region); a global symlink would leak into every
    condition, so it can't be used for an isolated A/B.
    """
    suffix = next((s for s in HOOKS if style.endswith(s)), None)
    persona = style == "SayLess-persona"
    real_style = "Default" if persona else (style[:-len(suffix)] if suffix else style)
    # Isolated dir: empty for Q&A shapes (no tool temptation); seeded with the
    # report workspace when the conversation does real edits.
    with tempfile.TemporaryDirectory(prefix="drift_") as cwd:
        # Hermetic style delivery: claude_turn runs with --setting-sources
        # project, so a named style must live in THIS cwd to resolve. Seeded up
        # front so a missing style raises here, before any turn is billed.
        ensure_style(cwd, real_style)
        if persona:
            with open(os.path.join(cwd, "CLAUDE.md"), "w") as f:
                f.write(_style_body(STYLE_FILE))
        for name, content in (workspace or {}).items():
            path = os.path.join(cwd, name)
            os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(name) else None
            with open(path, "w") as f:
                f.write(content)
        hook_script = None
        if suffix:
            hook_script = os.path.join(cwd, HOOKS[suffix])
            with open(os.path.join(HERE, "hooks", HOOKS[suffix])) as src:
                data = src.read()
            with open(hook_script, "w") as dst:
                dst.write(data)
            os.chmod(hook_script, 0o755)
        sid = None
        turns = []
        for i, step in enumerate(conversation):
            reply, sid = claude_turn(step["prompt"], real_style, model, cwd,
                                     resume=sid if i else None, hook_script=hook_script,
                                     allow_edits=workspace is not None)
            s = score_reply(reply)
            s["kind"] = step["kind"]
            s["reply"] = reply  # kept for auditing judge scores / inspecting drift
            if do_judge and step["kind"] == "checkable":
                s["completeness"] = judge_completeness(step["prompt"], reply, model, cwd)
            turns.append(s)
    return turns


# --- aggregation ------------------------------------------------------------

def _slope(ys):
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return round(sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom, 2)


def aggregate(results, conversation):
    """results: {style: [trial][turn] -> score}. Returns per-style summary."""
    summary = {}
    n_turns = len(conversation)
    half = n_turns // 2
    for style, trials in results.items():
        words, ems, opens, closes = [], [], [], []
        first, second = [], []
        per_turn = [[] for _ in range(n_turns)]
        per_kind = {}
        comps = []
        for trial in trials:
            for i, t in enumerate(trial):
                words.append(t["words"])
                ems.append(t["em_dashes"])
                opens.append(t["opener"])
                closes.append(t["closer"])
                per_turn[i].append(t["words"])
                (first if i < half else second).append(t["words"])
                per_kind.setdefault(t["kind"], []).append(t["words"])
                if "completeness" in t and t["completeness"] >= 0:
                    comps.append(t["completeness"])
        n = len(words) or 1
        f_avg = sum(first) / (len(first) or 1)
        s_avg = sum(second) / (len(second) or 1)
        summary[style] = {
            "avg_words": round(sum(words) / n, 1),
            "em_dashes_total": sum(ems),
            "opener_rate": round(sum(opens) / n, 3),
            "closer_rate": round(sum(closes) / n, 3),
            "first_half_avg": round(f_avg, 1),
            "second_half_avg": round(s_avg, 1),
            "drift_pct": round((s_avg - f_avg) / f_avg * 100, 1) if f_avg else 0.0,
            "slope_words_per_turn": _slope([sum(w) / (len(w) or 1) for w in per_turn]),
            "per_turn_avg_words": [round(sum(w) / (len(w) or 1), 1) for w in per_turn],
            "per_kind_avg_words": {k: round(sum(v) / len(v), 1) for k, v in per_kind.items()},
            "avg_completeness": round(sum(comps) / len(comps), 1) if comps else None,
            "sessions": len(trials),
        }
    return summary


def main():
    ap = argparse.ArgumentParser(description="Multi-turn persistence/drift test on real output styles.")
    ap.add_argument("styles", nargs="+", help='Output-style names (frontmatter name:). "Default" = baseline.')
    ap.add_argument("--trials", type=int, default=3, help="Sessions per style.")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--workers", type=int, default=6, help="Parallel sessions.")
    ap.add_argument("--judge", action="store_true", help="Score completeness on checkable turns.")
    ap.add_argument("--conversation", choices=list(CONVERSATIONS), default="default",
                    help="Which session shape: 'default' (16-turn mixed Q&A), "
                         "'coding' (28-turn coding/debugging-heavy), or "
                         "'report' (14-turn task-report-heavy, single-file edits), or "
                         "'report2' (16-turn heavy-result: 7-file app, audits/reviews).")
    ap.add_argument("--out", default=os.path.join(HERE, "drift_session_results.json"))
    args = ap.parse_args()

    conversation = CONVERSATIONS[args.conversation]
    jobs = [(st, t) for st in args.styles for t in range(args.trials)]
    raw = {st: [None] * args.trials for st in args.styles}
    print(f"Running {len(jobs)} sessions "
          f"({len(args.styles)} styles x {args.trials} trials x {len(conversation)} turns), "
          f"model={args.model}, judge={args.judge}, conversation={args.conversation}", flush=True)
    print(f"styles: {', '.join(args.styles)}\n", flush=True)

    workspace = WORKSPACES.get(args.conversation)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_session, st, args.model, args.judge, conversation,
                          workspace): (st, t)
                for st, t in jobs}
        done = 0
        for fut in as_completed(futs):
            st, t = futs[fut]
            raw[st][t] = fut.result()
            done += 1
            print(f"  {done}/{len(jobs)} done: {st} trial {t + 1}", flush=True)

    summary = aggregate(raw, conversation)
    with open(args.out, "w") as f:
        json.dump({"model": args.model, "trials": args.trials,
                   "conversation_name": args.conversation,
                   "conversation": [c["prompt"][:50] for c in conversation],
                   "summary": summary, "raw": raw}, f, indent=2)

    print("\n=== SUMMARY (words = prose per reply; lower = terser) ===")
    hdr = (f"{'style':16} {'avg':>6} {'1st_h':>6} {'2nd_h':>6} {'drift%':>7} "
           f"{'slope':>6} {'em':>4} {'open':>5} {'close':>5} {'compl':>6}")
    print(hdr)
    for st in args.styles:
        s = summary[st]
        print(f"{st:16} {s['avg_words']:>6} {s['first_half_avg']:>6} {s['second_half_avg']:>6} "
              f"{s['drift_pct']:>7} {s['slope_words_per_turn']:>6} {s['em_dashes_total']:>4} "
              f"{s['opener_rate']:>5} {s['closer_rate']:>5} {str(s['avg_completeness']):>6}")

    print("\n=== per-kind avg prose words ===")
    kinds = ["fact", "decision", "checkable", "explain", "grow", "report"]
    print(f"{'style':16} " + " ".join(f"{k:>10}" for k in kinds))
    for st in args.styles:
        pk = summary[st]["per_kind_avg_words"]
        print(f"{st:16} " + " ".join(f"{pk.get(k, 0):>10}" for k in kinds))

    print(f"\nFull results: {args.out}")


if __name__ == "__main__":
    main()
