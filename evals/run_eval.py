"""Eval runner using execution accuracy.

Reads evals/eval_set.jsonl, calls the agent at AGENT_URL on each question,
then compares the agent's SQL output to the gold SQL by *executed rows*
(canonicalized: sorted, stringified, None-coerced to empty).

Helpers (run_sql / canonicalize / matches) are provided. You implement
eval_one() and summarize().

Run:
    uv run python evals/run_eval.py --out results/eval_baseline.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_FILE = ROOT / "evals" / "eval_set.jsonl"
DEFAULT_OUT_FILE = ROOT / "results" / "eval_baseline.json"
DB_DIR = ROOT / "data" / "bird"
AGENT_URL_DEFAULT = "http://localhost:8001/answer"


# ---------- Helpers (provided) -----------------------------------------

def run_sql(db_id: str, sql: str, timeout: float = 5.0) -> tuple[bool, list[tuple] | None, str | None]:
    """Run sql against db_id in read-only mode. Returns (ok, rows, error)."""
    path = DB_DIR / f"{db_id}.sqlite"
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout) as conn:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            return True, rows, None
    except Exception as e:  # noqa: BLE001
        return False, None, f"{type(e).__name__}: {e}"


def canonicalize(rows: list[tuple] | None) -> list[tuple] | None:
    """Sort rows; coerce cells to str; None -> ''; normalize floats and case."""
    if rows is None:
        return None
    
    def _norm(cell: Any) -> str:
        if cell is None:
            return ""
        if isinstance(cell, float):
            return f"{cell:.4f}"
        return str(cell).strip().lower()

    return sorted(tuple(_norm(c) for c in row) for row in rows)


def matches(gold_rows: list[tuple] | None, pred_rows: list[tuple] | None) -> bool:
    if gold_rows is None or pred_rows is None:
        return False
    return canonicalize(gold_rows) == canonicalize(pred_rows)


# ---------- Implement these (Phase 5) ----------------------------------

def eval_one(question: dict, agent_url: str) -> dict:
    """Score one question. Return a dict capturing per-iteration correctness."""
    db_id = question["db_id"]
    # In eval_set.jsonl produced by scripts/load_data.py, the key is 'gold_sql'
    gold_sql = question.get("gold_sql") or question.get("SQL") or question.get("sql") or question.get("evidence")

    if not gold_sql:
        return {
            "question": question["question"],
            "db_id": db_id,
            "error": "Missing gold_sql in eval set",
            "iterations": [],
        }

    _, gold_rows, _ = run_sql(db_id, gold_sql)

    try:
        resp = httpx.post(agent_url, json={
            "question": question["question"],
            "db": db_id,
        }, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {
            "question": question["question"],
            "db_id": db_id,
            "error": str(e),
            "iterations": [],
        }

    # The agent server returns history: list[dict[str, Any]]
    # Each entry in history looks like {"node": "generate_sql" or "revise", "sql": "..."}
    # We need to score each SQL attempt found in the history.
    attempts = [h["sql"] for h in data.get("history", []) if h.get("sql")]

    # If the agent crashed or returned early without history but has a final sql
    if not attempts and data.get("sql"):
        attempts = [data["sql"]]

    iteration_results = []
    for sql in attempts:
        ok, pred_rows, err = run_sql(db_id, sql)
        is_correct = matches(gold_rows, pred_rows) if ok else False
        iteration_results.append({
            "sql": sql,
            "ok": ok,
            "correct": is_correct,
            "error": err,
        })

    return {
        "question": question["question"],
        "db_id": db_id,
        "gold_sql": gold_sql,
        "iterations": iteration_results,
    }


def summarize(results: list[dict]) -> dict:
    """Aggregate per-question results."""
    if not results:
        return {"count": 0, "accuracy": 0.0}

    # We want to know accuracy at iteration 1, 2, ..., MAX_ITERATIONS
    # Max iterations in graph.py is 3.
    max_k = 0
    for r in results:
        max_k = max(max_k, len(r.get("iterations", [])))

    if max_k == 0:
        return {"count": len(results), "error": "No iterations found"}

    stats = {}
    for k in range(1, max_k + 1):
        correct_count = 0
        for r in results:
            iters = r.get("iterations", [])
            if not iters:
                continue
            # "Carry forward": if agent stopped at j < k, use result at j.
            idx = min(k - 1, len(iters) - 1)
            if iters[idx]["correct"]:
                correct_count += 1
        stats[f"acc_at_iter_{k}"] = correct_count / len(results)

    stats["count"] = len(results)
    return stats


# ---------- Main (provided) --------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_FILE)
    parser.add_argument("--agent-url", default=AGENT_URL_DEFAULT)
    args = parser.parse_args()

    questions = [json.loads(line) for line in args.eval_set.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(questions)} eval questions from {args.eval_set}")

    results: list[dict] = []
    t0 = time.monotonic()
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['db_id']}: {q['question'][:60]}...", flush=True)
        results.append(eval_one(q, args.agent_url))
    elapsed = time.monotonic() - t0

    summary = summarize(results)
    out = {
        "summary": summary,
        "wall_clock_seconds": elapsed,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
