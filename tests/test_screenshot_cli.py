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


if __name__ == "__main__":
    unittest.main()

