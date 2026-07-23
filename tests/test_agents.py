from pathlib import Path
import tempfile
import unittest

from autonomous_paint.agents import (
    InProcessVisibleBridge,
    ScreenshotPaintAgent,
)
from autonomous_paint.session import DecisionSummary, PaintRun, VisibleAction


class AgentBoundaryTests(unittest.TestCase):
    def test_screenshot_agent_completes_under_budget_with_three_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = PaintRun(
                Path(directory),
                "a cheerful robot tending square flowers",
                41,
                "deterministic_pixel_vision",
                action_budget=100,
                review_budget=3,
            )
            run.app.set_summary(phase="SCREENSHOT-ONLY PIXEL AGENT")
            initial = run.capture("observation")
            bridge = InProcessVisibleBridge(run)

            # Avoid recording work in this focused boundary test.
            original_finish = bridge.finish
            bridge.finish = lambda: {"final_png": str(run.output_path)}  # type: ignore[method-assign]
            result = ScreenshotPaintAgent().run(
                run.prompt,
                run.seed,
                initial,
                bridge,
            )
            self.assertTrue(Path(result["final_png"]).exists())
            self.assertLessEqual(run.app.drawing_actions, 100)
            self.assertEqual(3, run.app.review_checkpoints)
            self.assertTrue(any(event["type"] == "ui_action" for event in run.events))
            bridge.finish = original_finish  # type: ignore[method-assign]

    def test_clear_cannot_bypass_exhausted_drawing_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = PaintRun(
                Path(directory),
                "a lighthouse during a storm using four colours",
                23,
                "model_vision",
                action_budget=1,
                review_budget=3,
            )
            run.app.drawing_actions = 1
            summary = DecisionSummary("Reset", "clear", "Clear canvas", "Visible art")
            with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
                run.execute(
                    VisibleAction("click", run.app._tool_rects["clear"].center),
                    summary,
                )


if __name__ == "__main__":
    unittest.main()
