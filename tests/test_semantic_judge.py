import json
from pathlib import Path
import tempfile
import unittest

from autonomous_paint.app import PaintApplication
from autonomous_paint.recording import save_png
from autonomous_paint.semantic_judge import apply_semantic_judgments
from autonomous_paint.tournament import build_rubric


class SemanticTournamentJudgeTests(unittest.TestCase):
    def test_recognizability_gate_and_similarity_penalty_change_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            app = PaintApplication(prompt="a cute guinea pig in a cuddle cup")
            screenshot = save_png(app.render(), run_dir / "app.png")
            final = app.model.save(run_dir / "final.png")
            manifest = {
                "prompt": app.prompt,
                "evaluations": [
                    {
                        "candidate_id": "A",
                        "screenshot": screenshot.name,
                        "final_png": final.name,
                        "total_score": 50,
                        "criteria": [],
                    },
                    {
                        "candidate_id": "B",
                        "screenshot": screenshot.name,
                        "final_png": final.name,
                        "total_score": 90,
                        "criteria": [],
                    },
                ],
            }
            (run_dir / "tournament.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            rubric = build_rubric(app.prompt)

            def criteria(score: float) -> list[dict[str, object]]:
                return [
                    {
                        "key": item.key,
                        "score": score,
                        "evidence": f"Visible evidence for {item.label.lower()}.",
                    }
                    for item in rubric
                ]

            judgments = {
                "recognizability_threshold": 7,
                "evaluations": [
                    {
                        "candidate_id": "A",
                        "recognizable_without_prompt": True,
                        "recognizability_score": 8,
                        "semantic_summary": "The requested animal and bed are recognizable.",
                        "criteria": criteria(7),
                        "findings": [],
                    },
                    {
                        "candidate_id": "B",
                        "recognizable_without_prompt": False,
                        "recognizability_score": 5,
                        "semantic_summary": "The subject is ambiguous without the prompt.",
                        "criteria": criteria(10),
                        "findings": [],
                    },
                ],
                "pairwise_diversity": [
                    {
                        "candidate_a": "A",
                        "candidate_b": "B",
                        "visual_similarity": 0.8,
                        "shared_features": ["same central silhouette", "same crop"],
                    }
                ],
            }
            judgment_path = run_dir / "judgments.json"
            judgment_path.write_text(json.dumps(judgments), encoding="utf-8")
            result = apply_semantic_judgments(run_dir, judgment_path)
            updated = json.loads(
                (run_dir / "tournament.json").read_text(encoding="utf-8")
            )
            self.assertEqual("A", result["winner"])
            self.assertEqual("model_vision_semantic_judge", updated["decision_source"])
            records = {
                item["candidate_id"]: item
                for item in updated["semantic_evaluations"]
            }
            self.assertLessEqual(records["B"]["total_score"], 49.9)
            self.assertGreater(records["A"]["diversity_penalty"], 0)


if __name__ == "__main__":
    unittest.main()
