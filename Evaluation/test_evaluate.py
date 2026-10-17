"""Synthetic fixtures test the calculator only. They are NOT evaluation evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evaluate as ev


class EvaluationTests(unittest.TestCase):
    def test_parser_valid_and_fenced(self):
        raw = '{"correctness":0.5,"faithfulness":1,"note":"Partial answer."}'
        for text in (raw, f"```json\n{raw}\n```", f"```\n{raw}\n```"):
            parsed, status, reason = ev.parse_judge(text)
            self.assertEqual(status, "scored")
            self.assertIsNone(reason)
            self.assertEqual(parsed["correctness"], 0.5)

    def test_parser_rejects_bad_json(self):
        for text in (None, "", "not JSON", '{"correctness":NaN}',
                     '{"correctness":1,"correctness":0}', "prefix {}"):
            self.assertEqual(ev.parse_judge(text)[1], "parse_failure")

    def test_parser_rejects_bad_schema(self):
        for data in ([], {}, {"correctness": True, "faithfulness": 1, "note": "x"},
                     {"correctness": 1, "faithfulness": None, "note": "x"},
                     {"correctness": "1", "faithfulness": 1, "note": "x"},
                     {"correctness": 1, "faithfulness": 1.1, "note": "x"},
                     {"correctness": -0.1, "faithfulness": 1, "note": "x"},
                     {"correctness": 1, "faithfulness": 1, "note": ""}):
            self.assertEqual(ev.parse_judge(json.dumps(data))[1], "invalid_score")

    def fixture(self, directory):
        ids = [r["id"] for r in ev.inputs()]
        manifest = {
            "run_kind": "synthetic_test_only",
            "files_sha256": {n: ev.digest(ev.HERE / n) for n in ("inputs.json", "judge_prompt.txt")},
            "exclusions": [{"id": ids[6], "reason": "Synthetic exclusion"}],
        }
        outputs = [
            {"id": ids[0], "finish_reason": "stop",
             "content": '{"correctness":1,"faithfulness":0.5,"note":"Test A"}'},
            {"id": ids[1], "finish_reason": "stop",
             "content": '{"correctness":0,"faithfulness":1,"note":"Test B"}'},
            {"id": ids[2], "finish_reason": "stop", "content": "bad json"},
            {"id": ids[3], "finish_reason": "stop",
             "content": '{"correctness":1,"faithfulness":null,"note":"Test C"}'},
            {"id": ids[4], "status": "request_failure", "error": "Synthetic failure"},
            {"id": ids[5], "finish_reason": "length", "content": "{}"},
        ]
        ev.save(directory / "manifest.json", manifest)
        ev.save(directory / "outputs.json", outputs)
        return manifest, outputs

    def test_all_statuses_and_paired_denominator(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.fixture(path)
            summary = ev.aggregate(path)
            self.assertEqual(summary["total_questions"], 40)
            self.assertEqual(summary["scored_successfully"], 2)
            self.assertEqual(summary["average_correctness"], 0.5)
            self.assertEqual(summary["average_faithfulness"], 0.75)
            self.assertEqual(summary["status_counts"], {
                "scored": 2, "parse_failure": 1, "invalid_score": 1,
                "request_failure": 1, "incomplete_output": 1, "missing_output": 33, "excluded": 1})
            self.assertEqual(len(summary["not_scored"]), 38)
            ev.aggregate(path, check=True)
            saved = ev.load(path / "aggregate.json")
            saved["average_correctness"] = 0.95
            ev.save(path / "aggregate.json", saved)
            with self.assertRaises(ValueError):
                ev.aggregate(path, check=True)

    def test_empty_outputs_produce_null_not_zero_or_nan(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.fixture(path)
            ev.save(path / "outputs.json", [])
            summary = ev.aggregate(path)
            self.assertEqual(summary["scored_successfully"], 0)
            self.assertIsNone(summary["average_correctness"])
            self.assertIsNone(summary["average_faithfulness"])

    def test_duplicate_unknown_ids_and_changed_inputs_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            manifest, outputs = self.fixture(path)
            for bad in (outputs + [outputs[0]], [{"id": "unknown"}]):
                ev.save(path / "outputs.json", bad)
                with self.assertRaises(ValueError):
                    ev.aggregate(path)
            ev.save(path / "outputs.json", outputs)
            manifest["files_sha256"]["inputs.json"] = "tampered"
            ev.save(path / "manifest.json", manifest)
            with self.assertRaises(ValueError):
                ev.aggregate(path)

    def test_exclusions_require_reason_and_known_unique_id(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            manifest, _ = self.fixture(path)
            item = manifest["exclusions"][0]
            for bad in ([dict(item, reason="")], [dict(item, id="unknown")], [item, item]):
                modified = copy.deepcopy(manifest)
                modified["exclusions"] = bad
                ev.save(path / "manifest.json", modified)
                with self.assertRaises(ValueError):
                    ev.aggregate(path)

    def test_missing_key_does_not_create_run_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "no-run"
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ValueError):
                    ev.new_run(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
