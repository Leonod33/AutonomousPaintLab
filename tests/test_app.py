from pathlib import Path
import tempfile
import unittest

from autonomous_paint.app import PaintApplication
from autonomous_paint.constants import CANVAS_ORIGIN, PALETTE


class PaintApplicationTests(unittest.TestCase):
    def test_visible_tool_palette_drag_and_save_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "final.png"
            app = PaintApplication(output_path=output)
            line_control = app._tool_rects["line"].center
            coral_control = app._palette_rects["coral"].center
            self.assertEqual("line", app.click(line_control).control)
            self.assertEqual("palette:coral", app.click(coral_control).control)
            start = (CANVAS_ORIGIN[0] + 10, CANVAS_ORIGIN[1] + 10)
            end = (CANVAS_ORIGIN[0] + 100, CANVAS_ORIGIN[1] + 100)
            self.assertTrue(app.drag(start, end).drawing_applied)
            colours = {colour for _, colour in app.model.image.getcolors(maxcolors=5000) or []}
            self.assertIn(PALETTE["coral"], colours)
            result = app.click(app._tool_rects["save"].center)
            self.assertEqual(str(output), result.saved_path)
            self.assertTrue(output.exists())

    def test_clear_and_undo_are_visible_controls(self) -> None:
        app = PaintApplication()
        app.model.line((0, 0), (50, 50), (0, 0, 0), 4)
        changed = app.model.image.tobytes()
        result = app.click(app._tool_rects["clear"].center)
        self.assertTrue(result.drawing_applied)
        self.assertNotEqual(changed, app.model.image.tobytes())
        self.assertTrue(app.click(app._tool_rects["undo"].center).applied)
        self.assertEqual(changed, app.model.image.tobytes())

    def test_budget_configuration_round_trips_with_counters(self) -> None:
        app = PaintApplication(
            action_budget=180,
            review_budget=5,
            revision_budget=8,
        )
        app.drawing_actions = 72
        app.review_checkpoints = 4
        app.revision_actions = 6
        restored = PaintApplication.from_payload(app.to_payload())
        self.assertEqual(180, restored.action_budget)
        self.assertEqual(5, restored.review_budget)
        self.assertEqual(8, restored.revision_budget)
        self.assertEqual(72, restored.drawing_actions)
        self.assertEqual(4, restored.review_checkpoints)
        self.assertEqual(6, restored.revision_actions)


if __name__ == "__main__":
    unittest.main()
