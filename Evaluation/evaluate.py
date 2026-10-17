#!/usr/bin/env python3
"""Preserve a new judge run, or recompute scores offline. Python 3.10+, stdlib only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
MODEL = "Qwen/Qwen3-235B-A22B-Instruct-2507"
ENDPOINT = "https://api.tokenfactory.nebius.com/v1/chat/completions"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def inputs():
    rows = load(HERE / "inputs.json")
    ids = [r["id"] for r in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError("Inputs must be nonempty with unique IDs")
    for row in rows:
        for key in ("question", "expected_answer", "actual_answer"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"{row['id']}: missing {key}")
        if row.get("cited_source") is not None and not isinstance(row["cited_source"], str):
            raise ValueError(f"{row['id']}: invalid cited_source")
    return rows


def parse_judge(raw):
    """Allow only JSON or a single enclosing Markdown JSON fence; never coerce scores."""
    if not isinstance(raw, str):
        return None, "parse_failure", "Judge content is not a string"
    text = raw.strip()
    if text.startswith("```json\n") and text.endswith("\n```"):
        text = text[8:-4].strip()
    elif text.startswith("```\n") and text.endswith("\n```"):
        text = text[4:-4].strip()
    try:
        def reject_constant(value):
            raise ValueError(f"Non-JSON constant: {value}")

        def unique_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"Duplicate JSON key: {key}")
                result[key] = value
            return result

        result = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_keys)
    except (ValueError, TypeError) as exc:
        return None, "parse_failure", str(exc)
    if not isinstance(result, dict):
        return None, "invalid_score", "Expected a JSON object"
    for metric in ("correctness", "faithfulness"):
        value = result.get(metric)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            return None, "invalid_score", f"{metric} must be a finite number in [0, 1]"
    if not isinstance(result.get("note"), str) or not result["note"].strip():
        return None, "invalid_score", "A nonempty judge note is required"
    return {k: result[k] for k in ("correctness", "faithfulness", "note")}, "scored", None


def recompute(run):
    run = Path(run)
    rows = inputs()
    manifest = load(run / "manifest.json")
    for filename in ("inputs.json", "judge_prompt.txt"):
        if manifest["files_sha256"][filename] != digest(HERE / filename):
            raise ValueError(f"{filename} differs from the run's recorded input hash")
    outputs = load(run / "outputs.json")
    by_id = {}
    allowed = {r["id"] for r in rows}
    for output in outputs:
        rid = output["id"]
        if rid not in allowed or rid in by_id:
            raise ValueError(f"Unknown or duplicate output ID: {rid}")
        by_id[rid] = output
    exclusions = manifest.get("exclusions", [])
    excluded = {}
    for item in exclusions:
        rid = item["id"]
        if rid not in allowed or rid in excluded or not str(item.get("reason", "")).strip():
            raise ValueError("Exclusions require unique known IDs and a reason")
        excluded[rid] = item["reason"]
    records = []
    for row in rows:
        rid = row["id"]
        output = by_id.get(rid)
        parsed = None
        if rid in excluded:
            status, reason = "excluded", excluded[rid]
        elif output is None:
            status, reason = "missing_output", "No saved judge output for this input"
        elif output.get("status") == "request_failure":
            status, reason = "request_failure", output.get("error", "Request failed")
        elif output.get("finish_reason") != "stop":
            status, reason = "incomplete_output", "Judge did not finish normally"
        else:
            parsed, status, reason = parse_judge(output.get("content"))
        record = dict(row, status=status, exclusion_reason=reason,
                      correctness=None, faithfulness=None, note=None)
        if parsed is not None:
            record.update(parsed)
        records.append(record)
    scored = [r for r in records if r["status"] == "scored"]
    count = len(scored)
    sums = {m: math.fsum(r[m] for r in scored) for m in ("correctness", "faithfulness")}
    averages = {m: sums[m] / count if count else None for m in sums}
    summary = {
        "run_kind": manifest["run_kind"],
        "total_questions": len(rows),
        "saved_output_count": len(outputs),
        "scored_successfully": count,
        "status_counts": {s: sum(r["status"] == s for r in records) for s in (
            "scored", "parse_failure", "invalid_score", "request_failure",
            "incomplete_output", "missing_output", "excluded")},
        "score_sums": sums,
        "average_correctness": averages["correctness"],
        "average_faithfulness": averages["faithfulness"],
        "percentages": {m: round(v * 100, 6) if v is not None else None
                        for m, v in averages.items()},
        "not_scored": [{"id": r["id"], "status": r["status"], "reason": r["exclusion_reason"]}
                       for r in records if r["status"] != "scored"],
        "denominator_policy": "Paired valid correctness AND faithfulness plus nonempty note; "
                              "missing/failed/excluded outputs are never zero-filled.",
        "outputs_sha256": digest(run / "outputs.json"),
    }
    return records, summary


def aggregate(run, check=False):
    records, summary = recompute(run)
    run = Path(run)
    for filename, value in (("records.json", records), ("aggregate.json", summary)):
        if check:
            if load(run / filename) != value:
                raise ValueError(f"{filename} does not match recomputation")
        else:
            save(run / filename, value)
    return summary


def request_judge(payload, key):
    """Sequential rate limiting in caller; retry only transient failures, no hidden rejudging."""
    attempts = []
    for number in range(1, 4):
        request = urllib.request.Request(
            ENDPOINT, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.load(response)
            attempts.append({"attempt": number, "status": "received"})
            choice = body["choices"][0]
            return {
                "status": "received", "returned_model": body.get("model"),
                "content": choice["message"].get("content"),
                "finish_reason": choice.get("finish_reason"), "usage": body.get("usage"),
                "attempts": attempts,
            }
        except urllib.error.HTTPError as exc:
            # Never persist response headers/bodies, which may expose credentials or account data.
            attempts.append({"attempt": number, "status": "http_error", "http_status": exc.code})
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError):
            attempts.append({"attempt": number, "status": "transport_failure"})
        except (ValueError, KeyError, IndexError, TypeError):
            attempts.append({"attempt": number, "status": "invalid_api_response"})
            break
        if number < 3:
            time.sleep(2 ** number)
    return {"status": "request_failure", "error": "No usable API response; see attempts",
            "attempts": attempts}


def new_run(run):
    key = os.environ.get("NEBIUS_API_KEY")
    if not key:
        raise ValueError("NEBIUS_API_KEY is required for a NEW run; offline aggregation needs no key")
    run = Path(run)
    rows = inputs()
    prompt = (HERE / "judge_prompt.txt").read_text(encoding="utf-8")
    # mkdir without exist_ok deliberately prevents overwriting a previous run.
    run.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "run_kind": "new_judge_run_on_saved_answers",
        "started_at_utc": now(),
        "completed_at_utc": None,
        "source": load(HERE / "source.json"),
        "judge": {"provider": "Nebius Token Factory", "endpoint": ENDPOINT,
                  "requested_model": MODEL, "temperature": 0, "max_tokens": 8192,
                  "stream": False, "seed": None, "tools": None},
        "request_policy": {"concurrency": 1, "minimum_delay_seconds": 1,
                           "maximum_attempts": 3, "retry_delay_seconds": [2, 4],
                           "timeout_seconds": 120, "parse_retries": 0},
        "files_sha256": {name: digest(HERE / name) for name in ("inputs.json", "judge_prompt.txt")},
        "exclusions": [],
        "limitations": [
            "New scoring of historical saved answers, not the original reported run.",
            "Not a new retrieval/generation run or post-mitigation test.",
            "No retrieved chunks, source documents or browsing tools supplied to the judge.",
            "Faithfulness is a rubric-based proxy, not independent citation verification.",
            "Temperature zero does not guarantee identical scores on a future model call.",
        ],
    }
    save(run / "manifest.json", manifest)
    outputs = []
    save(run / "outputs.json", outputs)
    for index, row in enumerate(rows):
        user = (f"Question: {row['question']}\nExpected answer: {row['expected_answer']}\n"
                f"Actual answer: {row['actual_answer']}\n"
                f"Cited source: {row['cited_source'] if row['cited_source'] is not None else 'null'}")
        payload = {"model": MODEL, "temperature": 0, "max_tokens": 8192, "stream": False,
                   "messages": [{"role": "system", "content": prompt},
                                {"role": "user", "content": user}]}
        output = request_judge(payload, key)
        outputs.append(dict(output, id=row["id"], recorded_at_utc=now()))
        save(run / "outputs.json", outputs)
        aggregate(run)
        print(f"{index + 1}/{len(rows)} {row['id']}: {output['status']}", flush=True)
        time.sleep(1)
    manifest["completed_at_utc"] = now()
    save(run / "manifest.json", manifest)
    return aggregate(run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "aggregate", "check"):
        sub = commands.add_parser(name)
        sub.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "run":
            summary = new_run(args.directory)
        else:
            summary = aggregate(args.directory, check=args.command == "check")
        print(json.dumps(summary, indent=2))
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(1, f"Evaluation error: {exc}\n")


if __name__ == "__main__":
    main()
