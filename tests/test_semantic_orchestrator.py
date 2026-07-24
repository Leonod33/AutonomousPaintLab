import json
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

from autonomous_paint.app import PaintApplication
from autonomous_paint.recording import save_png
from autonomous_paint.semantic_orchestrator import (
    prepare_blind_judge_request,
    run_semantic_judge_command,
)
from autonomous_paint.tournament import build_rubric


class SemanticOrchestratorTests(unittest.TestCase):
    def _make_tournament(self, run_dir: Path) -> None:
        evaluations = []
        for label in ("A", "B"):
            app = PaintApplication(prompt="a cute guinea pig in a cuddle cup")
            screenshot = save_png(app.render(), run_dir / f"source-{label}.png")
            final = app.model.save(run_dir / f"final-{label}.png")
            evaluations.append(
                {
                    "candidate_id": label,
                    "screenshot": screenshot.name,
                    "final_png": final.name,
                    "total_score": 50,
                    "criteria": [],
                }
            )
        manifest = {
            "prompt": "a cute guinea pig in a cuddle cup",
            "base_seed": 57,
            "candidate_seeds": {"A": 57, "B": 1066},
            "evaluations": evaluations,
        }
        (run_dir / "tournament.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

    def test_request_is_blind_and_copies_only_neutral_screenshots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self._make_tournament(run_dir)
            request_path = prepare_blind_judge_request(run_dir)
            request = json.loads(request_path.read_text(encoding="utf-8"))
            serialized = json.dumps(request)
            self.assertNotIn("base_seed", serialized)
            self.assertNotIn("candidate_seeds", serialized)
            self.assertNotIn("final_png", serialized)
            self.assertEqual(["A", "B"], [item["candidate_id"] for item in request["candidates"]])
            self.assertTrue(
                all(Path(item["screenshot"]).is_file() for item in request["candidates"])
            )

    def test_command_output_is_applied_without_manual_json_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self._make_tournament(run_dir)
            rubric_keys = [item.key for item in build_rubric("guinea pig")]
            judge = run_dir / "fake_judge.py"
            judge.write_text(
                textwrap.dedent(
                    f"""
                    import argparse, json
                    parser = argparse.ArgumentParser()
                    parser.add_argument("--request")
                    parser.add_argument("--output")
                    args = parser.parse_args()
                    request = json.load(open(args.request, encoding="utf-8"))
                    keys = {rubric_keys!r}
                    evaluations = []
                    for index, candidate in enumerate(request["candidates"]):
                        score = 8 - index
                        evaluations.append({{
                            "candidate_id": candidate["candidate_id"],
                            "recognizable_without_prompt": True,
                            "recognizability_score": score,
                            "semantic_summary": "The subject and cuddle cup are visible.",
                            "criteria": [
                                {{"key": key, "score": score, "evidence": "Visible evidence."}}
                                for key in keys
                            ],
                            "findings": [],
                        }})
                    result = {{
                        "recognizability_threshold": 7,
                        "evaluations": evaluations,
                        "pairwise_diversity": [{{
                            "candidate_a": "A",
                            "candidate_b": "B",
                            "visual_similarity": 0.2,
                            "shared_features": ["Both contain a central subject."],
                        }}],
                    }}
                    json.dump(result, open(args.output, "w", encoding="utf-8"))
                    """
                ),
                encoding="utf-8",
            )
            result = run_semantic_judge_command(
                run_dir,
                [
                    sys.executable,
                    str(judge),
                    "--request",
                    "{request}",
                    "--output",
                    "{output}",
                ],
            )
            updated = json.loads(
                (run_dir / "tournament.json").read_text(encoding="utf-8")
            )
            self.assertEqual("A", result["winner"])
            self.assertEqual("model_vision_semantic_judge", updated["decision_source"])
            self.assertTrue((run_dir / "semantic_judge_invocation.json").is_file())

    def test_command_requires_request_and_output_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            self._make_tournament(run_dir)
            with self.assertRaisesRegex(ValueError, r"\{request\}"):
                run_semantic_judge_command(run_dir, [sys.executable, "-V"])


if __name__ == "__main__":
    unittest.main()
