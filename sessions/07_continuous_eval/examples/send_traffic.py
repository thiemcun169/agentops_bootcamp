"""Send the questions of examples/traffic.txt to the running API, as alice and bob, one session per question.

Each run becomes a trace in Langfuse (environment LANGFUSE_TRACING_ENVIRONMENT of the server).
    uv run python examples/send_traffic.py [--api http://localhost:8000]
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--api", default="http://localhost:8000")
args = parser.parse_args()
questions = Path(__file__).with_name("traffic.txt").read_text(encoding="utf-8").splitlines()


def ask(i_question: tuple[int, str]) -> str:
    i, question = i_question
    headers = {"Authorization": f"Bearer {'alice' if i % 2 == 0 else 'bob'}-dev-token"}
    with httpx.Client(base_url=args.api, headers=headers, timeout=180) as client:
        session_id = client.post("/v1/sessions").json()["session_id"]
        meta, done = {}, {}
        with client.stream("POST", f"/v1/sessions/{session_id}/runs", json={"message": question}) as r:
            event = None
            for line in r.iter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: ") and event in ("metadata", "done", "error"):
                    (meta if event == "metadata" else done).update(json.loads(line[6:]))
    return (f"trace {meta['trace_id'][:8]} run {meta['run_id']} {done.get('seconds', '-')} s "
            f"tools={done.get('tools', done.get('title'))} | {question[:60]}")


with ThreadPoolExecutor(max_workers=3) as pool:
    for line in pool.map(ask, enumerate(questions)):
        print(line)
