from pathlib import Path
import tempfile
import unittest

from autonomous_paint.screenshot_cli import build_parser, run


class ScreenshotCliTests(unittest.TestCase):
    def test_reset_returns_only_visible_observation_and_budget_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            args = build_parser().parse_args(
                [
                    "--state-file",
                    str(base / "private.json"),
                    "reset",
                    "--run-dir",
                    str(base / "run"),
                    "--prompt",
                    "a lighthouse during a storm using four colours",
                    "--seed",
                    "23",
                    "--actions",
                    "180",
                    "--revisions",
                    "5",
                    "--revision-actions",
                    "8",
                ]
            )
            result = run(args)
            self.assertEqual("model_vision", result["decision_source"])
            self.assertEqual(
                "complete_application_screenshot_only",
                result["decision_input"],
            )
            self.assertTrue(Path(result["screenshot_path"]).exists())
            self.assertNotIn("canvas", result)
            self.assertNotIn("model", result)
            self.assertNotIn("history", result)
            self.assertEqual(180, result["drawing_action_budget"])
            self.assertEqual(5, result["review_budget"])
            self.assertEqual(8, result["revision_action_budget"])
            self.assertEqual(0, result["revision_actions"])

            review_args = build_parser().parse_args(
                [
                    "--state-file",
                    str(base / "private.json"),
                    "review",
                    "--assessment",
                    "The face needs a clearer expression.",
                    "--recognizability-score",
                    "8.0",
                    "--recognizable-without-prompt",
                    "--prompt-fidelity-score",
                    "8.5",
                    "--semantic-summary",
                    "The requested subject is recognizable, with one weak focal detail.",
                    "--finding",
                    (
                        '{"area":"Robot face","region":[200,100,180,150],'
                        '"issue":"The smile is faint.",'
                        '"suggestion":"Add a warm smile highlight.",'
                        '"priority":"high","confidence":0.9}'
                    ),
                ]
            )
            reviewed = run(review_args)
            self.assertEqual(1, reviewed["visible_review_findings"])
            self.assertTrue(Path(reviewed["screenshot_path"]).exists())


if __name__ == "__main__":
    unittest.main()
