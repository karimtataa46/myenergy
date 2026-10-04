"""
Runs the eval set against the live "Frag deine Anlage" agent in n8n and prints a pass rate.

    python3 automation/evals/run_eval.py              # every case once
    python3 automation/evals/run_eval.py --reps 2     # twice, for a tighter error bar
    python3 automation/evals/run_eval.py --only scope # cases tagged "scope" (or one case id)
    python3 automation/evals/run_eval.py --pause 15   # on Gemini's free tier (per-minute limit)

Needs `docker compose up` and the chat workflow published in n8n with a model
credential. Each question makes about 2 model calls: on a free tier that counts
against the daily limit, on a paid plan it costs money.

Writes automation/evals/results/<time>/: results.jsonl (one graded row per trial),
errors.jsonl (trials that never produced an answer, kept out of the score) and summary.md.
Standard library only, so it runs without installing anything.
"""
import argparse
import json
import math
import random
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grading  # noqa: E402

WORKFLOW = HERE.parent / "workflows" / "chat-agent.json"


def default_chat_url() -> str:
    nodes = json.loads(WORKFLOW.read_text())["nodes"]
    trigger = next(n for n in nodes if n["type"].endswith("chatTrigger"))
    return f"http://localhost:5678/webhook/{trigger['webhookId']}/chat"


def http_json(url, body=None, timeout=120):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class InfraError(Exception):
    """The trial never produced an answer: not the model's fault, not scored."""


def ask(chat_url, session, question, timeout):
    """One chat turn, retried with jittered backoff on network and server errors."""
    for attempt in range(1, 4):
        try:
            start = time.monotonic()
            body = http_json(chat_url, {"action": "sendMessage", "sessionId": session,
                                        "chatInput": question}, timeout)
            return body, time.monotonic() - start, attempt
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code < 500 or attempt == 3:
                raise InfraError(f"HTTP {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == 3:
                raise InfraError(f"{type(e).__name__}: {e}")
        time.sleep(2 ** attempt + random.random())


def snapshot(api_url):
    """What the plant really says right now: the expected answers come from here."""
    return {name: http_json(f"{api_url}/api/{name}") for name in ("live", "plan", "savings", "site")}


def preflight(args):
    """Stop at once, with the fix, when nothing could be answered (instead of an error per case)."""
    try:
        http_json(f"{args.api_url}/api/site", timeout=10)
    except Exception as e:
        sys.exit(f"Can't reach myEnergy at {args.api_url} ({e}). Start it: docker compose up -d")
    try:
        urllib.request.urlopen(args.chat_url, timeout=10)    # GET serves the chat page, no model call
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.exit("The chat workflow isn't published in n8n. Open 'Frag deine Anlage', connect "
                     "the model credential, and click Publish.")
    except urllib.error.URLError as e:
        sys.exit(f"Can't reach n8n at {args.chat_url} ({e.reason}). Start it: docker compose up -d")


def append(path, record):
    with open(path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def wilson(passed, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = passed / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def run_trial(case, rep, args, run_id):
    session = f"eval-{run_id}-{case['id']}-{rep}"
    for turn in case.get("turns", []):                 # earlier turns of a conversation
        ask(args.chat_url, session, turn, args.timeout)
        time.sleep(args.pause)
    truth = snapshot(args.api_url)
    body, latency, attempts = ask(args.chat_url, session, case["question"], args.timeout)
    answer, tools, observations = grading.parse_agent_reply(body)
    checks = grading.grade(case, answer, tools, observations, truth)
    return {"case": case["id"], "rep": rep, "tags": case.get("tags", []), "question": case["question"],
            "answer": answer, "tools_called": tools, "checks": checks, "passed": all(checks.values()),
            "latency_s": round(latency, 2), "attempts": attempts}


def summarize(rows, errors, cases_total):
    n, passed = len(rows), sum(r["passed"] for r in rows)
    lo, hi = wilson(passed, n)
    out = [f"# Eval summary\n",
           f"**Pass rate: {passed}/{n} = {passed / n:.0%}** (95% interval {lo:.0%} to {hi:.0%})" if n
           else "**No graded trials.**",
           f"\n{len(errors)} trial(s) never produced an answer (see errors.jsonl, not scored). "
           f"{cases_total} case(s) in the set.\n"]

    by_check = defaultdict(lambda: [0, 0])
    for r in rows:
        for name, ok in r["checks"].items():
            key = name.split(":")[0]
            by_check[key][0] += ok
            by_check[key][1] += 1
    out.append("| Check | Passed |\n|---|---|")
    out += [f"| {k} | {p}/{t} |" for k, (p, t) in sorted(by_check.items())]

    by_tag = defaultdict(lambda: [0, 0])
    for r in rows:
        for tag in r["tags"]:
            by_tag[tag][0] += r["passed"]
            by_tag[tag][1] += 1
    out.append("\n| Tag | Passed |\n|---|---|")
    out += [f"| {k} | {p}/{t} |" for k, (p, t) in sorted(by_tag.items())]

    failed = [r for r in rows if not r["passed"]]
    if failed:
        out.append("\n## Failed trials\n")
        for r in failed:
            bad = ", ".join(k for k, ok in r["checks"].items() if not ok)
            out.append(f"- **{r['case']}** (rep {r['rep']}): {bad}\n  - Q: {r['question']}\n"
                       f"  - A: {r['answer'][:300]}\n  - tools: {r['tools_called']}")
    latencies = sorted(r["latency_s"] for r in rows)
    if latencies:
        out.append(f"\nMedian answer time: {latencies[len(latencies) // 2]:.1f} s")
    return "\n".join(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--only", help="a case id or a tag")
    p.add_argument("--chat-url", default=default_chat_url())
    p.add_argument("--api-url", default="http://localhost:8000")
    p.add_argument("--timeout", type=int, default=120, help="seconds per question")
    p.add_argument("--pause", type=float, default=0,
                   help="seconds to wait between questions (stay under a free tier's per-minute limit)")
    p.add_argument("--min-pass-rate", type=float, help="exit 1 below this (0 to 1), for CI")
    args = p.parse_args()

    preflight(args)
    cases = json.loads((HERE / "cases.json").read_text())
    if args.only:
        cases = [c for c in cases if c["id"] == args.only or args.only in c.get("tags", [])]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = HERE / "results" / run_id
    out_dir.mkdir(parents=True)

    rows, errors = [], []
    results, failures = out_dir / "results.jsonl", out_dir / "errors.jsonl"
    results.touch(), failures.touch()
    in_a_row = 0
    for rep in range(1, args.reps + 1):
        for case in cases:
            try:
                row = run_trial(case, rep, args, run_id)
                rows.append(row)
                append(results, row)                   # saved as it comes: Ctrl+C loses nothing
                in_a_row = 0
                print(f"{'PASS' if row['passed'] else 'FAIL'}  {case['id']}  (rep {rep}, {row['latency_s']} s)")
            except InfraError as e:
                errors.append({"case": case["id"], "rep": rep, "error": str(e)})
                append(failures, errors[-1])
                in_a_row += 1
                print(f"ERROR {case['id']}  (rep {rep}): {e}")
                if in_a_row == 3:                      # e.g. a used-up daily quota: the rest would fail too
                    print("\nStopped: 3 errors in a row. Check the n8n execution log (or the model's quota).")
                    break
            time.sleep(args.pause)
        if in_a_row == 3:
            break

    summary = summarize(rows, errors, len(cases))
    (out_dir / "summary.md").write_text(summary + "\n")
    print("\n" + summary + f"\n\nSaved to {out_dir.relative_to(HERE.parent.parent)}")

    rate = sum(r["passed"] for r in rows) / len(rows) if rows else 0.0
    if args.min_pass_rate is not None and (rate < args.min_pass_rate or errors):
        sys.exit(1)


if __name__ == "__main__":
    main()
