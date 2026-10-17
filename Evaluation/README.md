# Reproducible evaluation evidence

## Evidence status: awaiting judge output

The historical evaluation report states **95% correctness and 95% faithfulness**.
Those figures remain **reported, not independently recomputed**. The public
workflow contains 40 saved input records, an embedded rubric and scoring code,
but no saved judge responses (`pinData` is empty). Its only historical revision
also contains no saved judge output. No results were found in repository
branches, releases or GitHub Actions artifacts when checked on 2026-10-17.
This search does not establish whether the author has private n8n execution data.

**No completed judge run is included here yet.** Test fixtures are synthetic,
temporary calculator tests, never evidence for the reported scores. An absent
result is not a zero, a pass, or a reason to assume all 40 records were scored.

## Files and privacy

- `inputs.json`: the 40 public synthetic question/expected-answer/saved-answer/
  citation records, in original order, with stable `q01`–`q40` IDs. No user
  identifiers, sessions, account details, n8n credentials or webhook IDs.
- `judge_prompt.txt`: the exact system prompt embedded in the public workflow.
- `source.json`: pinned source revision, input mapping and SHA-256 hashes.
- `evaluate.py`: Python 3.10+ standard-library runner and offline calculator.
- `test_evaluate.py`: synthetic tests, including bad JSON, missing outputs,
  zero scored rows, invalid scores, explicit exclusions and changed hashes.

The public inputs contain generic first-person scenarios, not real user records.
No answer text has been corrected or normalized, including the original
character-encoding artifacts. Author `FLAG` comments are not judge output.
Review any imported judge notes for personal data before committing. Do not
commit the full workflow or an unfiltered execution export as evaluation evidence;
execution exports can contain credentials, headers and unrelated session data.

## Preserve a NEW run

The runner uses the original Nebius endpoint and requested Qwen model. It sets
temperature to zero, a token cap of 8192 and sequential rate limiting explicitly;
these settings were not explicit in the historical workflow. Consequently this
is a **new judge run over saved answers**, never recovery of the original run.
It does not call the live bot, re-ingest sources, or test citation mitigations.

Set `NEBIUS_API_KEY` through your environment's secret manager; never put it in
the repository or a command argument. Then, from the repository root:

```sh
python Evaluation/evaluate.py run Evaluation/runs/new-YYYY-MM-DD
python Evaluation/evaluate.py check Evaluation/runs/new-YYYY-MM-DD
python -m unittest discover -s Evaluation -p 'test_*.py' -v
```

The run directory must not already exist. The runner saves `manifest.json`
(timestamps, model/configuration, hashes, limitations and exclusions),
`outputs.json` (raw judge content, returned model, finish reason, usage and
attempt outcomes), `records.json` (per-question scores, notes and status), and
`aggregate.json` (sums, denominators, averages, percentages and every unscored ID).
Outputs are checkpointed after each question. If interrupted, recompute the
partial run offline; do not overwrite it or silently rejudge selected questions.
Start a separate, clearly labelled new run if needed. HTTP/transport failures are
recorded; only transient failures are retried, at most three attempts. Invalid
judge JSON is preserved and not retried to obtain a more convenient score.

## Import ORIGINAL output without inventing metadata

Create a distinct run directory containing:

1. `manifest.json` with `run_kind: "original_export"`, the actual model/provider/
   configuration and original execution date if known, `files_sha256` for
   `inputs.json` and `judge_prompt.txt`, and `exclusions: []`. Record unknown
   historical settings as `null`, not inferred defaults. Record the import date,
   source export checksum and mapping method separately from the execution date.
   The new runner's settings are NOT evidence of the historical configuration.
2. `outputs.json`, an array of `{id, content, finish_reason, ...}` records,
   mapped by original question/item pairing to stable input IDs. `content` must
   be the untouched judge response string. Preserve request failures as
   `{id, status: "request_failure", error: "redacted reason"}`.
   Record `finish_reason` from the original API response; a missing or non-`stop`
   reason is conservatively unscored pending confirmation, never assumed complete.
   Do not map by output position if failed requests may have removed rows.
3. Any intentional exclusions as `{id, reason}` in the manifest. Retain original
   output even for excluded records, rather than deleting failed cases.

If only parsed per-question scores survive, preserve those with provenance and
document that raw judge content/parse failures cannot be reconstructed. Do not
manufacture an apparent raw model response from the parsed values.

From the repository root:

```sh
python Evaluation/evaluate.py aggregate Evaluation/runs/original-export
python Evaluation/evaluate.py check Evaluation/runs/original-export
```

Aggregation and checking use **no network and no credentials**. `check` verifies
both saved derived files against recalculation, including the raw-output hash.

## Denominator and limitations

Both averages use the same denominator: records with finite numeric correctness
AND faithfulness in `[0,1]`, a nonempty judge note, normal completion and no
explicit exclusion. For each metric, `average = score_sum / scored_successfully`;
the percentage is that average multiplied by 100. Valid zero scores are included.
No valid scores gives `null` averages. Missing outputs, request failures, parse
failures, invalid scores, incomplete responses and explicit exclusions are listed
by ID and reason. Unknown or duplicate IDs and changed input/prompt hashes fail
instead of producing an apparently valid report.

This is deliberately stricter than the old n8n aggregate, which filtered only
`correctness !== null`, potentially discarding parse failures silently or including
malformed faithfulness values. If an original export has malformed rows, document
the difference instead of claiming identical denominators or a historical 40/40.

The original judge receives expected answers and cited URLs, **not retrieved
chunks or source-page text**, and the runner provides no browsing tool. Its
faithfulness score is therefore a rubric-based proxy, not independent evidence
that a URL exists, is in the ingested corpus, or supports each claim. A new score
cannot establish the historical 95%, retrieval accuracy, or a before/after fix.
Recomputation from saved responses is deterministic; rerunning the LLM is not.
